import os
import re
from .config import DECOMPILED_DIR

"""Utilities for manifest and apktool.yml inspection."""

def is_android_tv_manifest(decompiled_dir: str = DECOMPILED_DIR) -> bool:
    """Return True if manifest indicates Android TV.

    Robust rules (to avoid false positives on mobile builds):
    - TRUE if the manifest declares a launcher activity with
      category android.intent.category.LEANBACK_LAUNCHER.
    - ELSE TRUE if uses-feature android.software.leanback is present with android:required="true".
    - Otherwise FALSE (even if leanback feature exists with required="false").
    """
    manifest_path = os.path.join(decompiled_dir, 'AndroidManifest.xml')
    if not os.path.isfile(manifest_path):
        return False
    try:
        with open(manifest_path, 'r', encoding='utf-8', errors='ignore') as f:
            data = f.read()
        # Primary signal: Leanback launcher category present on a launcher activity
        if 'android.intent.category.LEANBACK_LAUNCHER' in data:
            return True
        # Secondary signal: leanback feature explicitly required
        if re.search(r'<uses-feature\s+[^>]*android:name="android\.software\.leanback"[^>]*android:required="true"', data):
            return True
        return False
    except Exception:
        return False

# Note: version extraction is handled by extract_version_name_and_code with apktool.yml only for now

def extract_version_name_and_code(decompiled_dir: str = DECOMPILED_DIR) -> tuple[str | None, str | None]:
    """Return (versionName, versionCode) by parsing apktool.yml only.

    This is the most reliable source produced by apktool. If apktool.yml is
    missing or parsing fails, returns (None, None).
    """
    apktool_yml = os.path.join(decompiled_dir, 'apktool.yml')
    try:
        if os.path.isfile(apktool_yml):
            with open(apktool_yml, 'r', encoding='utf-8', errors='ignore') as f:
                yml = f.read()
            m_vn = re.search(r'(?mi)^\s*versionName:\s*([^\r\n#]+)', yml)
            m_vc = re.search(r'(?mi)^\s*versionCode:\s*([^\r\n#]+)', yml)
            vn = m_vn.group(1).strip().strip('\'"') if m_vn else None
            vc = m_vc.group(1).strip().strip('\'"') if m_vc else None
            if vn or vc:
                return (vn, vc)
    except Exception:
        pass
    return (None, None)