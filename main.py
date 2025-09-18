import os
import time
import base64
import sys

try:
    import tkinter as tk
    from tkinter import filedialog
except Exception:
    tk = None
    filedialog = None

from crunchyroll_extractor.config import (
    PROJECT_ROOT,
    DECOMPILED_DIR,
    OUTPUT_JSON_FILENAME,
    OUTPUT_JSON_FILENAME_TV,
    OUTPUT_JSON_FILENAME_MOBILE,
    USER_AGENT_TEMPLATE,
    TV_USER_AGENT_TEMPLATE,
)
 # TV version fetcher removed: TV version extracted from manifest
from crunchyroll_extractor.apktool_installer import APKToolInstaller
from crunchyroll_extractor.apk_decompiler import APKDecompiler
from crunchyroll_extractor.apk_downloader import APKDownloader
from crunchyroll_extractor.credential_searcher import CredentialSearcher
from crunchyroll_extractor.credential_validator import CredentialValidator


class CrunchyrollAnalyzer:
    """Coordinates download, decompile, credential search, validation, and output."""

    def __init__(self):
        self.base_dir = PROJECT_ROOT
        self.decompiled_dir = DECOMPILED_DIR
        self.apktool_installer = APKToolInstaller()
        self.downloader = APKDownloader()
        self.decompiler = None
        self.validator = CredentialValidator()
        self.apktool_path = None

    def setup_apktool(self) -> bool:
        print("=== APKTOOL SETUP ===")
        if self.apktool_installer.is_apktool_installed():
            print("APKTool is already installed locally.")
            self.apktool_path = self.apktool_installer.get_apktool_path()
            print(f"Using APKTool at: {self.apktool_path}")
            return True
        print("APKTool not found. Installing automatically...")
        if self.apktool_installer.install_apktool():
            self.apktool_path = self.apktool_installer.get_apktool_path()
            print(f"APKTool installed successfully at: {self.apktool_path}")
            return True
        print("Failed to install APKTool automatically.")
        return False

    def _generate_latest_json(self, client_id: str, secret_id: str, app_version: str, *,
                               user_agent_template: str | None = None,
                               output_filename: str | None = None) -> str:
        print("\n=== PHASE 5: GENERATING LATEST.JSON ===")
        auth_string = f"{client_id}:{secret_id}"
        base64_auth = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
        ua_tmpl = user_agent_template or USER_AGENT_TEMPLATE
        user_agent = ua_tmpl.format(app_version)
        latest_data = {
            "auth": base64_auth,
            "user-agent": user_agent,
            "app-version": app_version,
        }
        ofn = output_filename or OUTPUT_JSON_FILENAME
        output_path = os.path.join(self.base_dir, ofn)
        with open(output_path, 'w') as f:
            import json
            json.dump(latest_data, f, indent=2)
        print(f"Generated {ofn} at: {output_path}")
        print(f"Basic Auth: {base64_auth}")
        print(f"User-Agent: {user_agent}")
        print(f"App Version: {app_version}")
        return output_path

    def _short_mobile_version(self, version: str) -> str:
        """Return version without last numeric build segment for mobile (e.g. 3.91.1.960 -> 3.91.1)."""
        if not version:
            return version
        parts = version.split('.')
        if len(parts) > 3 and all(p.isdigit() for p in parts):
            return '.'.join(parts[:-1])
        return version

    def run(self, manual_package_path: str | None = None, *, mode: str | None = None, clean: bool = True):
        print("=== CRUNCHYROLL CREDENTIAL EXTRACTOR ===")
        print("Downloads (if needed), decompiles and extracts credentials from the Crunchyroll Android app.")
        print("=" * 50)
        apk_output_dir = None
        try:
            if not self.setup_apktool():
                print("APKTool setup failed. Aborting.")
                return

            self.decompiler = APKDecompiler(self.apktool_path)

            mode_normalized = (mode or '').lower() if mode else None
            if mode_normalized == 'tv':
                if not manual_package_path:
                    print("TV MODE: You must provide an Android TV APK/XAPK/APKM path (use --manual). Aborting.")
                    return
                print("TV MODE: Using provided local package (ensure it is the Android TV build).")
                apk_info = self.downloader.use_local_package(manual_package_path)
            else:
                if manual_package_path:
                    print("Manual mode: using local APK/XAPK/APKM package.")
                    apk_info = self.downloader.use_local_package(manual_package_path)
                else:
                    apk_info = self.downloader.download_crunchyroll_apk()
            if not apk_info:
                print("Failed to download the APK. Aborting.")
                return
            # remember output dir for cleanup
            apk_output_dir = os.path.dirname(os.path.abspath(apk_info['path'])) if apk_info and apk_info.get('path') else None

            # Keep manifest for TV or auto mode
            keep_manifest = (mode_normalized in ('tv', 'auto'))
            if not self.decompiler.decompile_apk(apk_info['path'], keep_manifest=keep_manifest):
                print("Failed to decompile the APK. Aborting.")
                return

            # Auto-detect if needed
            resolved_mode = mode_normalized
            if mode_normalized == 'auto':
                from crunchyroll_extractor.manifest_utils import is_android_tv_manifest
                if is_android_tv_manifest(self.decompiled_dir):
                    print("[AUTO] Android TV detected (LEANBACK). Using TV mode.")
                    resolved_mode = 'tv'
                else:
                    print("[AUTO] No LEANBACK category found. Using mobile mode.")
                    resolved_mode = 'mobile'

            searcher = CredentialSearcher(self.decompiled_dir)
            if resolved_mode == 'tv':
                secret_id, client_id = searcher.find_tv_credentials()
            else:
                secret_id, client_id = searcher.find_credentials()

            if secret_id and client_id:
                latest_paths = []
                creds_paths = []
                final_valid = False
                base64_auth = None
                tv_validation = None
                validation_result = None

                if resolved_mode == 'tv':
                    # TV mode: skip mobile validation entirely
                    auth_string = f"{client_id}:{secret_id}"
                    base64_auth = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
                    from crunchyroll_extractor.manifest_utils import extract_version_from_manifest, enforce_tv_version_format
                    manifest_version = extract_version_from_manifest(self.decompiled_dir)
                    tv_version = enforce_tv_version_format(manifest_version or apk_info['version'])
                    user_agent_tv = TV_USER_AGENT_TEMPLATE.format(tv_version)
                    tv_validation = self.validator.validate_tv_credentials(client_id, secret_id, user_agent_tv)
                    final_valid = tv_validation.get('valid', False)

                    latest_json_path_tv = self._generate_latest_json(
                        client_id, secret_id, tv_version,
                        user_agent_template=TV_USER_AGENT_TEMPLATE,
                        output_filename=OUTPUT_JSON_FILENAME_TV,
                    )
                    latest_paths.append(latest_json_path_tv)
                    creds_file_tv = os.path.join(self.base_dir, f"crunchyroll_credentials_tv_v{tv_version}.txt")
                    with open(creds_file_tv, 'w') as f:
                        f.write(f"Crunchyroll TV Version: {tv_version}\n")
                        f.write(f"Client ID: {client_id}\n")
                        f.write(f"Secret ID: {secret_id}\n")
                        f.write(f"Basic Auth: {base64_auth}\n")
                        f.write(f"User-Agent: {user_agent_tv}\n")
                        f.write(f"CF_BM Cookie: {tv_validation.get('cf_bm') or 'None'}\n")
                        f.write(f"Anonymous Access Token Present: {tv_validation.get('anonymous_access_token_present')}\n")
                        f.write(f"User Code: {tv_validation.get('user_code') or 'None'}\n")
                        f.write(f"Device Code: {tv_validation.get('device_code') or 'None'}\n")
                        f.write(f"Validation Status: {'VALID' if final_valid else 'INVALID'}\n")
                        f.write(f"Tested At: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n")
                    creds_paths.append(creds_file_tv)
                else:
                    # Mobile mode
                    auth_string = f"{client_id}:{secret_id}"
                    base64_auth = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
                    short_version = self._short_mobile_version(apk_info['version'])
                    user_agent_mobile = USER_AGENT_TEMPLATE.format(short_version)
                    validation_result = self.validator.validate_credentials(base64_auth, user_agent_mobile)
                    final_valid = validation_result['valid']

                    latest_json_path_mobile = self._generate_latest_json(
                        client_id, secret_id, short_version,
                        user_agent_template=USER_AGENT_TEMPLATE,
                        output_filename=OUTPUT_JSON_FILENAME_MOBILE,
                    )
                    latest_paths.append(latest_json_path_mobile)
                    creds_file_mobile = os.path.join(self.base_dir, f"crunchyroll_credentials_mobile_v{short_version}.txt")
                    with open(creds_file_mobile, 'w') as f:
                        f.write(f"Crunchyroll Version: {short_version}\n")
                        f.write(f"File Size: {apk_info['file_size']}\n")
                        f.write(f"Client ID: {client_id}\n")
                        f.write(f"Secret ID: {secret_id}\n")
                        f.write(f"Basic Auth: {base64_auth}\n")
                        f.write(f"User-Agent: {user_agent_mobile}\n")
                        f.write(f"Validation Status: {'VALID' if final_valid else 'INVALID'}\n")
                        f.write(f"Tested At: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n")
                    creds_paths.append(creds_file_mobile)

                print("\n" + "=" * 50)
                if final_valid:
                    print("=== EXTRACTION AND VALIDATION SUCCESSFUL ===")
                else:
                    print("=== EXTRACTION COMPLETE - VALIDATION FAILED ===")

                print(f"Crunchyroll Version (raw package): {apk_info['version']}")
                print(f"File Size: {apk_info['file_size']}")
                print(f"Client ID: {client_id}")
                print(f"Secret ID: {secret_id}")
                for p in latest_paths:
                    print(f"Output: {p}")
                print("=" * 50)

                for cp in creds_paths:
                    print(f"Credentials saved to: {cp}")

                if final_valid:
                    print("\n🎉 SUCCESS: Credentials extracted and validated successfully!")
                    if resolved_mode == 'tv':
                        print("TV device-code validation succeeded.")
                else:
                    print("\n⚠️  WARNING: Credentials extracted but validation failed!")
                    if resolved_mode == 'tv':
                        print("Device-code flow failed or incomplete.")
                    else:
                        print("The tokens may be outdated or there might be a network issue.")
                    print("You can still try using them, but they might not work.")
            else:
                print("\nFailed to extract credentials.")
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            if clean:
                print("\n=== CLEANUP ===")
                # Remove decompiled directory
                try:
                    if os.path.isdir(self.decompiled_dir):
                        import shutil
                        shutil.rmtree(self.decompiled_dir, ignore_errors=True)
                        print(f"Removed decompiled folder: {self.decompiled_dir}")
                except Exception as ce:
                    print(f"Cleanup warning (decompiled): {ce}")
                # Remove downloaded APK directory (versioned folder)
                try:
                    if apk_output_dir and os.path.isdir(apk_output_dir):
                        import shutil
                        shutil.rmtree(apk_output_dir, ignore_errors=True)
                        print(f"Removed APK folder: {apk_output_dir}")
                except Exception as ce:
                    print(f"Cleanup warning (apk): {ce}")


def main():
    manual = False
    manual_path = None
    mode = None  # 'tv' or 'mobile'; default is mobile
    clean = True
    show_help = False

    # Parse CLI flags (simple)
    args = [a for a in sys.argv[1:] if a]
    if ('-h' in args) or ('--help' in args):
        show_help = True
    if '--no-clean' in args:
        clean = False
    if '--manual' in args:
        manual = True
        # Optional path argument after --manual
        try:
            idx = args.index('--manual')
            if idx + 1 < len(args) and not args[idx + 1].startswith('-'):
                manual_path = args[idx + 1]
        except Exception:
            pass

    explicit_tv = '--tv' in args
    explicit_mobile = '--mobile' in args
    if explicit_tv and explicit_mobile:
        mode = 'tv'
    elif explicit_tv:
        mode = 'tv'
        try:
            tv_idx = args.index('--tv')
            if tv_idx + 1 < len(args):
                nxt = args[tv_idx + 1]
                if not nxt.startswith('-') and not manual_path:
                    manual = True
                    manual_path = nxt
        except Exception:
            pass
    elif explicit_mobile:
        mode = 'mobile'
    else:
        # No explicit flag: if --manual => auto-detect, else mobile download
        mode = 'auto' if manual else 'mobile'

    if show_help:
        print("Usage: python main.py [--tv|--mobile] [--manual [path]] [--no-clean] [-h|--help]")
        print("")
        print("Options:")
        print("  --tv [path]    Force Android TV mode. Optional path immediately after flag.")
        print("  --mobile       Force Android Mobile mode (default when no mode flag).")
        print("  --manual [p]   Use a local APK/XAPK/APKM; if path omitted a file dialog is opened.")
        print("                 With --manual only (no mode flag) the manifest is inspected to auto-detect TV.")
        print("  --no-clean     Keep decompiled and downloaded folders (default: remove).")
        print("  -h, --help     Show this help and exit.")
        print("")
        print("Behavior:")
        print("  Default => mobile artifacts only (latest-mobile.json + credentials).")
        print("  TV mode => credentials from Constants.smali + version from AndroidManifest (versionName_versionCode).")
        return

    if manual and not manual_path:
        print("--manual specified: please select an APK/XAPK/APKM file in the file dialog...")
        chosen = None
        try:
            if tk is not None:
                root = tk.Tk()
                root.withdraw()
                chosen = filedialog.askopenfilename(
                    title="Select APK/XAPK/APKM package",
                    filetypes=[
                        ("APK or Bundles", "*.apk *.xapk *.apkm *.zip"),
                        ("All files", "*.*"),
                    ],
                )
                root.destroy()
        except Exception as e:
            print(f"File dialog failed: {e}")
        manual_path = chosen or None

    # If TV mode and no path yet, open file dialog
    if mode == 'tv' and not manual_path:
        print("TV mode: select the Android TV APK/XAPK/APKM package...")
        chosen = None
        try:
            if tk is not None:
                root = tk.Tk()
                root.withdraw()
                chosen = filedialog.askopenfilename(
                    title="Select Android TV APK/XAPK/APKM package",
                    filetypes=[
                        ("APK or Bundles", "*.apk *.xapk *.apkm *.zip"),
                        ("All files", "*.*"),
                    ],
                )
                root.destroy()
        except Exception as e:
            print(f"File dialog failed: {e}")
        manual_path = chosen or None

    analyzer = CrunchyrollAnalyzer()
    analyzer.run(manual_path, mode=mode, clean=clean)


if __name__ == "__main__":
    main()