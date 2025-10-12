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
from crunchyroll_extractor.apk_manager import APKManager
from crunchyroll_extractor.credential_searcher import CredentialSearcher
from crunchyroll_extractor.credential_validator import CredentialValidator


class CrunchyrollAnalyzer:
    """Coordinates download, decompile, credential search, validation, and output."""

    def __init__(self):
        self.base_dir = PROJECT_ROOT
        self.decompiled_dir = DECOMPILED_DIR
        self.apktool_installer = APKToolInstaller()
        self.downloader = APKManager()
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
        print("Decompiles a provided package and extracts credentials from the Crunchyroll Android app.")
        print("=" * 50)
        apk_output_dir = None
        try:
            if not self.setup_apktool():
                print("APKTool setup failed. Aborting.")
                return

            self.decompiler = APKDecompiler(self.apktool_path)

            mode_normalized = (mode or '').lower() if mode else None

            if not manual_package_path:
                msg = "You must provide a local APK/XAPK/APKM (or ZIP) path or select one via the file dialog."
                print(msg)
                return
            if mode_normalized == 'tv':
                print("TV MODE: Using provided local package (ensure it is the Android TV build).")
            else:
                print("Using provided local APK/XAPK/APKM package.")
            # Generate a short session id for temporary naming
            import random, string
            session_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
            apk_info = self.downloader.use_local_package(manual_package_path, session_id=session_id)
            if not apk_info:
                print("Failed to process the provided package. Aborting.")
                return
            # remember paths for cleanup/rename
            apk_output_dir = apk_info.get('output_dir') if apk_info else None
            session_root = apk_info.get('session_root') if apk_info else None

            # Always keep manifest: we rely on it for accurate version detection
            keep_manifest = True
            # Set decompiled directory under session root
            original_decompiled_dir = self.decompiled_dir
            if session_root:
                self.decompiled_dir = os.path.join(session_root, "decompiled")
                self.decompiler.decompiled_dir = self.decompiled_dir
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

            # Extract versions once
            from crunchyroll_extractor.manifest_utils import extract_version_name_and_code
            vn, vc = extract_version_name_and_code(self.decompiled_dir)
            tv_version = f"{vn}_{vc}" if vn and vc else (vn or "unknown")
            mobile_version = vn or "unknown"

            searcher = CredentialSearcher(self.decompiled_dir)
            if resolved_mode == 'tv':
                secret_id, client_id = searcher.find_tv_credentials()
            else:
                # Try mobile first
                secret_id, client_id = searcher.find_credentials()
                # If nothing found, attempt TV fallback when manifest indicates a TV build
                if not (secret_id and client_id):
                    try:
                        from crunchyroll_extractor.manifest_utils import is_android_tv_manifest
                        if is_android_tv_manifest(self.decompiled_dir):
                            print("\n[Fallback] Mobile scan found nothing; manifest indicates Android TV. Trying TV-specific search...")
                            secret_id, client_id = searcher.find_tv_credentials()
                            if secret_id and client_id:
                                resolved_mode = 'tv'
                    except Exception as _e:
                        pass

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
                    user_agent_mobile = USER_AGENT_TEMPLATE.format(mobile_version)
                    validation_result = self.validator.validate_credentials(base64_auth, user_agent_mobile)
                    final_valid = validation_result['valid']

                    latest_json_path_mobile = self._generate_latest_json(
                        client_id, secret_id, mobile_version,
                        user_agent_template=USER_AGENT_TEMPLATE,
                        output_filename=OUTPUT_JSON_FILENAME_MOBILE,
                    )
                    latest_paths.append(latest_json_path_mobile)
                    creds_file_mobile = os.path.join(self.base_dir, f"crunchyroll_credentials_mobile_v{mobile_version}.txt")
                    with open(creds_file_mobile, 'w') as f:
                        f.write(f"Crunchyroll Version: {mobile_version}\n")
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

                # Report resolved app version
                reported_version = tv_version if resolved_mode == 'tv' else mobile_version
                print(f"Crunchyroll Version: {reported_version}")
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
                    if session_root and os.path.isdir(session_root):
                        import shutil
                        shutil.rmtree(session_root, ignore_errors=True)
                        print(f"Removed session folder: {session_root}")
                except Exception as ce:
                    print(f"Cleanup warning (apk): {ce}")
            else:
                # Rename folders and APK using detected mode and version
                try:
                    profile = 'tv' if resolved_mode == 'tv' else 'mobile'
                    ver_label = tv_version if resolved_mode == 'tv' else mobile_version
                    # Build target names
                    base = f"{profile}_v{ver_label}"
                    if session_root and os.path.isdir(session_root):
                        new_session = os.path.join(self.base_dir, f"crunchyroll_{base}")
                        # Compare absolute normalized paths to decide rename without requiring target existence
                        cur_abs = os.path.normcase(os.path.abspath(session_root))
                        new_abs = os.path.normcase(os.path.abspath(new_session))
                        if cur_abs != new_abs:
                            os.rename(session_root, new_session)
                            print(f"Renamed session folder to: {new_session}")
                            session_root = new_session
                        # Inside session: decompiled and extracted paths remain the same names
                        # Rename APK file
                        extracted_dir = os.path.join(session_root, "extracted")
                        try:
                            if os.path.isdir(extracted_dir):
                                for f in os.listdir(extracted_dir):
                                    if f.lower().endswith('.apk'):
                                        old_apk = os.path.join(extracted_dir, f)
                                        new_apk = os.path.join(extracted_dir, f"Crunchyroll_{base}.apk")
                                        if os.path.normcase(os.path.abspath(old_apk)) != os.path.normcase(os.path.abspath(new_apk)):
                                            os.rename(old_apk, new_apk)
                                            print(f"Renamed APK to: {new_apk}")
                                        break
                        except Exception:
                            pass
                except Exception as ce:
                    print(f"Post-run rename warning: {ce}")


def main():
    package_path = None
    mode = None  # 'tv' or 'mobile'; default is mobile
    clean = True
    show_help = False

    # Parse CLI flags (simple)
    args = [a for a in sys.argv[1:] if a]
    if ('-h' in args) or ('--help' in args):
        show_help = True
    if '--no-clean' in args:
        clean = False

    explicit_tv = '--tv' in args
    explicit_mobile = '--mobile' in args
    # Extract positional path (first arg not starting with '-') if any
    try:
        for i, a in enumerate(args):
            if a.startswith('-'):
                # Handle optional path after --tv/--mobile
                if a in ('--tv', '--mobile') and i + 1 < len(args) and not args[i + 1].startswith('-') and not package_path:
                    package_path = args[i + 1]
                continue
            if not package_path:
                package_path = a
    except Exception:
        pass
    if explicit_tv and explicit_mobile:
        mode = 'tv'
    elif explicit_tv:
        mode = 'tv'
    elif explicit_mobile:
        mode = 'mobile'
    else:
        # No explicit mode flag: default to auto-detect after decompile
        mode = 'auto'

    if show_help:
        print("Usage: python main.py [--tv|--mobile] [path] [--no-clean] [-h|--help]")
        print("")
        print("Options:")
        print("  --tv [path]    Force Android TV mode. Optional path immediately after flag.")
        print("  --mobile       Force Android Mobile mode.")
        print("  path           Optional positional path to APK/XAPK/APKM/APKS/ZIP. If omitted, a file dialog opens.")
        print("  --no-clean     Keep decompiled and downloaded folders (default: remove).")
        print("  -h, --help     Show this help and exit.")
        print("")
        print("Behavior:")
        print("  No web fetching. A local package is mandatory.")
        print("  Default (no --tv/--mobile) => auto-detect via manifest: TV if LEANBACK (or leanback feature), else Mobile.")
        print("  Mobile => outputs latest-mobile.json + credentials (version inferred from filename).")
        print("  TV mode => credentials from Constants.smali + version from AndroidManifest (versionName_versionCode).")
        return

    # If a package path is not provided, open file dialog to select one
    if not package_path:
        print("Select the APK/XAPK/APKM package...")
        chosen = None
        try:
            if tk is not None:
                root = tk.Tk()
                root.withdraw()
                chosen = filedialog.askopenfilename(
                    title="Select APK/XAPK/APKM/APKS package",
                    filetypes=[
                        ("APK or Bundles", "*.apk *.xapk *.apkm *.apks *.zip"),
                        ("All files", "*.*"),
                    ],
                )
                root.destroy()
        except Exception as e:
            print(f"File dialog failed: {e}")
        package_path = chosen or None

    analyzer = CrunchyrollAnalyzer()
    analyzer.run(package_path, mode=mode, clean=clean)


if __name__ == "__main__":
    main()