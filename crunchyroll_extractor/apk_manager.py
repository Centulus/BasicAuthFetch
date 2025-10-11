import os
import re
import zipfile
import shutil

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
        if not v:
            return "unknown"
        v = re.sub(r"[\-_]", ".", v)
        v = re.sub(r"\.{2,}", ".", v).strip(".")
        parts = [p for p in v.split('.') if p.isdigit()]
        return '.'.join(parts[:4]) if parts else "unknown"

    # ---------- public API (local only) ----------

    def use_local_package(self, package_path: str):
        """Process a local XAPK/APKM/APKS/APK package selected by the user and return APK info.

        - If APK: copy to output dir and return.
        - If XAPK/APKM/APKS/ZIP: extract, find largest .apk, copy and return.
        Version is best-effort from filename when possible; otherwise 'unknown'.
        """
        print("=== PHASE 1: USING LOCAL PACKAGE ===")
        if not package_path or not os.path.exists(package_path):
            print("Local package path is invalid or does not exist.")
            return None

        filename = os.path.basename(package_path)
        lower = filename.lower()
        version = "unknown"
        m = re.search(r"(\d+(?:[._-]\d+){1,3})", filename)
        if m:
            # local normalize similar to downloader
            v = m.group(1)
            v = re.sub(r"[\-_]", ".", v)
            v = re.sub(r"\.{2,}", ".", v).strip('.')
            parts = [p for p in v.split('.') if p.isdigit()]
            version = '.'.join(parts[:4]) if parts else "unknown"

        output_dir = os.path.join(self.base_dir, f"extracted_crunchyroll_v{version}")
        os.makedirs(output_dir, exist_ok=True)

        def _finalize(apk_src_path: str):
            size_bytes = os.path.getsize(apk_src_path)
            size_str = self._human_size(size_bytes)
            apk_filename = f"Crunchyroll_v{version}.apk"
            apk_destination = os.path.join(output_dir, apk_filename)
            shutil.copy2(apk_src_path, apk_destination)
            print(f"Main APK saved as: {os.path.abspath(apk_destination)}")
            return {
                'path': apk_destination,
                'version': version,
                'file_size': size_str
            }

        if lower.endswith('.apk'):
            print(f"Using provided APK: {filename}")
            return _finalize(package_path)

        if lower.endswith('.xapk') or lower.endswith('.apkm') or lower.endswith('.apks') or lower.endswith('.zip'):
            ext = os.path.splitext(lower)[1]
            print(f"Extracting {ext.upper()} package...")
            extract_dir = os.path.join(output_dir, "package_extracted")
            os.makedirs(extract_dir, exist_ok=True)
            try:
                with zipfile.ZipFile(package_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
            except zipfile.BadZipFile:
                print("Package is not a valid ZIP/XAPK/APKM/APKS file.")
                return None

            print("Finding main APK file...")
            largest_apk = None
            largest_size = 0
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    if f.endswith('.apk'):
                        fp = os.path.join(root, f)
                        sz = os.path.getsize(fp)
                        if sz > largest_size:
                            largest_size = sz
                            largest_apk = fp
            if not largest_apk:
                print("Error: Could not find any APK file in the package")
                return None

            print(f"Found main APK: {os.path.basename(largest_apk)} ({largest_size/(1024*1024):.2f} MB)")
            result = _finalize(largest_apk)
            print("Cleaning up extracted package...")
            shutil.rmtree(extract_dir, ignore_errors=True)
            return result

        print("Unsupported package format. Provide APK/XAPK/APKM/APKS.")
        return None