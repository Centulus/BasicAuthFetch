import os
import re
import zipfile
import shutil
from pathlib import Path

from .config import PROJECT_ROOT


class APKManager:
    """Handles local APK/XAPK/APKM packages provided by the user (no web fetching)."""

    def __init__(self):
        self.base_dir = PROJECT_ROOT

    # ---------- common helpers ----------
    def _human_size(self, n):
        try:
            n = float(n)
        except Exception:
            return "Unknown size"
        units = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while n >= 1024 and i < len(units) - 1:
            n /= 1024.0
            i += 1
        return f"{n:.2f} {units[i]}"

    def _normalize_version(self, v: str) -> str:
        """Deprecated: version is now always read from manifest; keep for backward compatibility."""
        return "unknown"

    # ---------- public API (local only) ----------

    # Classification helpers
    def _classify_input(self, package_path: str | os.PathLike) -> str:
        """Classify the provided path into one of:
        - 'single_apk'      : A single APK file (ZIP with AndroidManifest at root)
        - 'container'       : A packaged bundle containing one or more APKs (xapk/apkm/apks/zip-of-apks)
        - 'dir_with_apks'   : A directory containing at least one .apk file
        - 'invalid'         : Anything else

        Uses fast ZIP central directory heuristics and doesn't extract contents.
        """
        p = Path(package_path)
        if p.is_dir():
            # If the user extracted an XAPK/APKM and provided the folder
            try:
                for _ in p.rglob("*.apk"):
                    return "dir_with_apks"
            except Exception:
                pass
            return "invalid"

        if not p.is_file():
            return "invalid"

        lower_ext = p.suffix.lower()

        # Early hint based on extension
        if lower_ext in {".apkm", ".xapk", ".apks"}:
            # Still verify it's a zip below if needed by extraction step
            return "container"
        if lower_ext == ".apk":
            # Most APKs are valid ZIPs. Validate quickly.
            return "single_apk" if zipfile.is_zipfile(p) else "invalid"

        # Generic ZIP or files with wrong extension but ZIP content
        if lower_ext == ".zip" or zipfile.is_zipfile(p):
            try:
                with zipfile.ZipFile(p) as z:
                    names = [i.filename for i in z.infolist() if not i.is_dir()]
                    root_names = [n for n in names if "/" not in n.rstrip("/")]
                    root_has_manifest = ("AndroidManifest.xml" in root_names) or ("classes.dex" in root_names)
                    contains_apks = any(n.lower().endswith(".apk") for n in names)
                    container_hints = {"manifest.json", "info.json", "apkm-meta.json"}
                    has_container_hints = any(n in root_names for n in container_hints)

                    if contains_apks and not root_has_manifest:
                        return "container"
                    if root_has_manifest:
                        return "single_apk"
                    if has_container_hints or contains_apks:
                        return "container"
                    return "invalid"
            except zipfile.BadZipFile:
                return "invalid"

        return "invalid"

    def _find_largest_apk_in_dir(self, directory: str) -> str | None:
        """Return path to largest .apk within a directory tree, or None if not found."""
        largest_apk = None
        largest_size = 0
        for root, _dirs, files in os.walk(directory):
            for f in files:
                if f.lower().endswith('.apk'):
                    fp = os.path.join(root, f)
                    try:
                        sz = os.path.getsize(fp)
                    except OSError:
                        continue
                    if sz > largest_size:
                        largest_size = sz
                        largest_apk = fp
        return largest_apk

    def _extract_container_file(self, package_path: str, extract_dir: str) -> str | None:
        """Extract a container (xapk/apkm/apks/zip with apks) into extract_dir and return largest APK path."""
        os.makedirs(extract_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(package_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
        except zipfile.BadZipFile:
            print("Package is not a valid ZIP/XAPK/APKM/APKS file.")
            return None
        return self._find_largest_apk_in_dir(extract_dir)

    def use_local_package(self, package_path: str, *, session_id: str | None = None, output_root: str | None = None):
        """Process a local package selected by the user and return APK info.

        Behavior:
        - If classified as single APK: skip extraction; copy directly and return.
        - If classified as container (xapk/apkm/apks/zip of apks): extract, find largest .apk, copy and return.
        - If directory with apks: find largest .apk and copy.
        Version is best-effort from filename/folder name when possible; otherwise 'unknown'.
        """
        print("=== PHASE 1: USING LOCAL PACKAGE ===")
        if not package_path or not os.path.exists(package_path):
            print("Local package path is invalid or does not exist.")
            return None

        version = "unknown"

        classification = self._classify_input(package_path)
        filename = os.path.basename(package_path)
        sid = session_id or "sess"
        session_root = output_root or os.path.join(self.base_dir, f"crunchyroll_{sid}")
        output_dir = os.path.join(session_root, "extracted")
        os.makedirs(session_root, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        def _finalize(apk_src_path: str):
            size_bytes = os.path.getsize(apk_src_path)
            size_str = self._human_size(size_bytes)
            apk_filename = f"Crunchyroll_{sid}.apk"
            apk_destination = os.path.join(output_dir, apk_filename)
            shutil.copy2(apk_src_path, apk_destination)
            print(f"Main APK saved as: {os.path.abspath(apk_destination)}")
            return {
                'path': apk_destination,
                'version': version,
                'file_size': size_str,
                'output_dir': output_dir,
                'session_root': session_root,
                'session_id': sid,
            }

        if classification == 'single_apk':
            print(f"Using provided APK: {filename}")
            return _finalize(package_path)

        if classification == 'container':
            ext = os.path.splitext(filename)[1].upper() or '.ZIP'
            print(f"Extracting {ext} package...")
            extract_dir = os.path.join(output_dir, "package_extracted")
            largest_apk = self._extract_container_file(package_path, extract_dir)
            if not largest_apk:
                print("Error: Could not find any APK file in the package")
                return None
            try:
                sz_mb = os.path.getsize(largest_apk) / (1024 * 1024)
                print(f"Found main APK: {os.path.basename(largest_apk)} ({sz_mb:.2f} MB)")
            except OSError:
                print(f"Found main APK: {os.path.basename(largest_apk)}")
            result = _finalize(largest_apk)
            print("Cleaning up extracted package...")
            shutil.rmtree(extract_dir, ignore_errors=True)
            return result

        if classification == 'dir_with_apks':
            print("Scanning provided directory for APKs...")
            largest_apk = self._find_largest_apk_in_dir(package_path)
            if not largest_apk:
                print("Error: No .apk files found in the provided directory")
                return None
            try:
                sz_mb = os.path.getsize(largest_apk) / (1024 * 1024)
                print(f"Found main APK: {os.path.basename(largest_apk)} ({sz_mb:.2f} MB)")
            except OSError:
                print(f"Found main APK: {os.path.basename(largest_apk)}")
            return _finalize(largest_apk)

        print("Unsupported package format. Provide APK/XAPK/APKM/APKS or a directory containing APKs.")
        return None