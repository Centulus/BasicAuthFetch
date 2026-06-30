"""Read APK/APKM/XAPK/APKS packages into memory without filesystem extraction."""
import io
import os
import zipfile
from dataclasses import dataclass


@dataclass
class ApkContents:
    manifest_data: bytes
    dex_files: list[bytes]          # classes.dex, classes2.dex, …
    file_size_str: str
    apk_name: str


def _human_size(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} TB"


def _read_apk_contents(apk_bytes: bytes, apk_name: str, total_size: int) -> ApkContents | None:
    """Parse an APK (ZIP) from in-memory bytes and extract manifest + DEX files."""
    try:
        with zipfile.ZipFile(io.BytesIO(apk_bytes)) as apk:
            names = apk.namelist()
            manifest_data = apk.read('AndroidManifest.xml')
            dex_names = sorted(
                (n for n in names if n.startswith('classes') and n.endswith('.dex')),
                key=lambda x: (0 if x == 'classes.dex' else int(x[7:-4] or 1)),
            )
            if not dex_names:
                return None
            dex_files = [apk.read(n) for n in dex_names]
        return ApkContents(
            manifest_data=manifest_data,
            dex_files=dex_files,
            file_size_str=_human_size(total_size),
            apk_name=apk_name,
        )
    except Exception as e:
        print(f"[apk_reader] Failed to read APK contents: {e}")
        return None


def _largest_apk_in_zip(container: zipfile.ZipFile) -> str | None:
    """Return the name of the largest .apk member inside a container ZIP."""
    best_name: str | None = None
    best_size = 0
    for info in container.infolist():
        if info.filename.lower().endswith('.apk') and info.file_size > best_size:
            best_size = info.file_size
            best_name = info.filename
    return best_name


def load_package(package_path: str) -> ApkContents | None:
    """Load an APK/APKM/XAPK/APKS/ZIP/directory and return its contents in memory."""
    if not os.path.exists(package_path):
        print(f"[apk_reader] Path not found: {package_path}")
        return None

    # ── directory of APKs ────────────────────────────────────────────────────
    if os.path.isdir(package_path):
        best_path: str | None = None
        best_size = 0
        for root, _dirs, files in os.walk(package_path):
            for f in files:
                if f.lower().endswith('.apk'):
                    fp = os.path.join(root, f)
                    sz = os.path.getsize(fp)
                    if sz > best_size:
                        best_size = sz
                        best_path = fp
        if not best_path:
            print("[apk_reader] No APK found in directory.")
            return None
        print(f"[apk_reader] Using largest APK in directory: {os.path.basename(best_path)}")
        with open(best_path, 'rb') as fh:
            data = fh.read()
        return _read_apk_contents(data, os.path.basename(best_path), best_size)

    total_size = os.path.getsize(package_path)
    ext = os.path.splitext(package_path)[1].lower()

    # ── single APK ───────────────────────────────────────────────────────────
    if ext == '.apk':
        print(f"[apk_reader] Reading APK: {os.path.basename(package_path)}")
        with open(package_path, 'rb') as fh:
            data = fh.read()
        return _read_apk_contents(data, os.path.basename(package_path), total_size)

    # ── container (APKM / XAPK / APKS / ZIP-of-APKs) ────────────────────────
    if ext in ('.apkm', '.xapk', '.apks', '.zip') or zipfile.is_zipfile(package_path):
        ext_upper = ext.upper() or '.ZIP'
        print(f"[apk_reader] Reading {ext_upper} container: {os.path.basename(package_path)}")
        try:
            with zipfile.ZipFile(package_path) as container:
                # Try base.apk first (standard APKM layout)
                if 'base.apk' in container.namelist():
                    apk_name = 'base.apk'
                else:
                    apk_name = _largest_apk_in_zip(container)
                if not apk_name:
                    print("[apk_reader] No APK found inside container.")
                    return None
                print(f"[apk_reader] Extracting {apk_name} ({_human_size(container.getinfo(apk_name).file_size)}) …")
                apk_bytes = container.read(apk_name)
        except zipfile.BadZipFile:
            print("[apk_reader] File is not a valid ZIP/APKM/XAPK.")
            return None
        return _read_apk_contents(apk_bytes, apk_name, len(apk_bytes))

    print(f"[apk_reader] Unsupported file type: {ext}")
    return None
