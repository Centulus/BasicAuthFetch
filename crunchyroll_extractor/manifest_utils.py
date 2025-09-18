import os
import re
from .config import DECOMPILED_DIR

def enforce_tv_version_format(version: str) -> str:
    """Ensure version string uses underscore between name and numeric build if pattern matches.

    Accepts already-correct pattern (name_code). If pattern is name.code (dot) at end with 5+ digits, convert last dot to underscore.
    Example: 3.45.2.22274 -> 3.45.2_22274
    """
    if not version:
        return version
    if '_' in version:
        return version
    # detect pattern with final .digits
    m = re.match(r'^([0-9][0-9A-Za-z._-]*?)\.([0-9]{4,})$', version)
    if m:
        return f"{m.group(1)}_{m.group(2)}"
    return version

def is_android_tv_manifest(decompiled_dir: str = DECOMPILED_DIR) -> bool:
    """Return True if manifest indicates Android TV (LEANBACK launcher category)."""
    manifest_path = os.path.join(decompiled_dir, 'AndroidManifest.xml')
    if not os.path.isfile(manifest_path):
        return False
    try:
        with open(manifest_path, 'r', encoding='utf-8', errors='ignore') as f:
            data = f.read()
        return 'android.intent.category.LEANBACK_LAUNCHER' in data
    except Exception:
        return False

def extract_version_from_manifest(decompiled_dir: str = DECOMPILED_DIR) -> str | None:
    """Parse AndroidManifest.xml to build version string 'versionName_versionCode'.
    Returns None if file not found or parsing fails.
    """
    manifest_path = os.path.join(decompiled_dir, 'AndroidManifest.xml')
    if not os.path.isfile(manifest_path):
        return None
    try:
        with open(manifest_path, 'r', encoding='utf-8', errors='ignore') as f:
            data = f.read()
    # Extract versionName/versionCode attributes (e.g. android:versionName="3.45.2" android:versionCode="22274")
        name_match = re.search(r'android:versionName="([0-9A-Za-z._-]+)"', data)
        code_match = re.search(r'android:versionCode="([0-9]+)"', data)
        if name_match and code_match:
            return f"{name_match.group(1)}_{code_match.group(1)}"
    except Exception:
        return None
    return None
