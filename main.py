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
from crunchyroll_extractor.tv_version_fetcher import get_latest_android_tv_version
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

    def run(self, manual_package_path: str | None = None, *, mode: str | None = None, clean: bool = True):
        print("=== CRUNCHYROLL CREDENTIAL EXTRACTOR ===")
        print("This tool will download, decompile, and extract credentials from Crunchyroll APK")
        print("=" * 50)
        apk_output_dir = None
        try:
            if not self.setup_apktool():
                print("APKTool setup failed. Aborting.")
                return

            self.decompiler = APKDecompiler(self.apktool_path)

            if manual_package_path:
                print("Manual mode enabled: using a local APK/XAPK/APKM package.")
                apk_info = self.downloader.use_local_package(manual_package_path)
            else:
                apk_info = self.downloader.download_crunchyroll_apk()
            if not apk_info:
                print("Failed to download the APK. Aborting.")
                return
            # remember output dir for cleanup
            apk_output_dir = os.path.dirname(os.path.abspath(apk_info['path'])) if apk_info and apk_info.get('path') else None

            if not self.decompiler.decompile_apk(apk_info['path']):
                print("Failed to decompile the APK. Aborting.")
                return

            searcher = CredentialSearcher(self.decompiled_dir)
            secret_id, client_id = searcher.find_credentials()

            if secret_id and client_id:
                auth_string = f"{client_id}:{secret_id}"
                base64_auth = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
                user_agent_mobile = USER_AGENT_TEMPLATE.format(apk_info['version'])

                # Validate using mobile UA by default (back-compat)
                validation_result = self.validator.validate_credentials(base64_auth, user_agent_mobile)

                # Determine operation mode
                mode_normalized = (mode or "").lower() if mode else None
                generate_both = not mode_normalized  # when no flag provided

                latest_paths = []
                creds_paths = []

                # Always produce requested outputs
                if generate_both or mode_normalized == "mobile":
                    latest_json_path_mobile = self._generate_latest_json(
                        client_id, secret_id, apk_info['version'],
                        user_agent_template=USER_AGENT_TEMPLATE,
                        output_filename=(OUTPUT_JSON_FILENAME_MOBILE if generate_both else OUTPUT_JSON_FILENAME),
                    )
                    latest_paths.append(latest_json_path_mobile)
                    creds_file_mobile = os.path.join(
                        self.base_dir,
                        (f"crunchyroll_credentials_mobile_v{apk_info['version']}.txt" if generate_both else f"crunchyroll_credentials_v{apk_info['version']}.txt")
                    )
                    with open(creds_file_mobile, 'w') as f:
                        f.write(f"Crunchyroll Version: {apk_info['version']}\n")
                        f.write(f"File Size: {apk_info['file_size']}\n")
                        f.write(f"Client ID: {client_id}\n")
                        f.write(f"Secret ID: {secret_id}\n")
                        f.write(f"Basic Auth: {base64_auth}\n")
                        f.write(f"User-Agent: {user_agent_mobile}\n")
                        f.write(f"Validation Status: {'VALID' if validation_result['valid'] else 'INVALID'}\n")
                        f.write(f"Tested At: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n")
                    creds_paths.append(creds_file_mobile)

                if generate_both or mode_normalized == "tv":
                    tv_version = None
                    try:
                        tv_version = get_latest_android_tv_version()
                    except Exception as e:
                        print(f"TV version fetch failed: {e}")
                    tv_version = tv_version or apk_info['version']
                    user_agent_tv = TV_USER_AGENT_TEMPLATE.format(tv_version)
                    latest_json_path_tv = self._generate_latest_json(
                        client_id, secret_id, tv_version,
                        user_agent_template=TV_USER_AGENT_TEMPLATE,
                        output_filename=(OUTPUT_JSON_FILENAME_TV if generate_both else OUTPUT_JSON_FILENAME_TV),
                    )
                    latest_paths.append(latest_json_path_tv)
                    creds_file_tv = os.path.join(
                        self.base_dir,
                        f"crunchyroll_credentials_tv_v{tv_version}.txt"
                    )
                    with open(creds_file_tv, 'w') as f:
                        f.write(f"Crunchyroll TV Version: {tv_version}\n")
                        f.write(f"Client ID: {client_id}\n")
                        f.write(f"Secret ID: {secret_id}\n")
                        f.write(f"Basic Auth: {base64_auth}\n")
                        f.write(f"User-Agent: {user_agent_tv}\n")
                        f.write(f"Validation Status: {'VALID' if validation_result['valid'] else 'INVALID'}\n")
                        f.write(f"Tested At: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n")
                    creds_paths.append(creds_file_tv)

                print("\n" + "=" * 50)
                if validation_result['valid']:
                    print("=== EXTRACTION AND VALIDATION SUCCESSFUL ===")
                else:
                    print("=== EXTRACTION COMPLETE - VALIDATION FAILED ===")

                print(f"Crunchyroll Version: {apk_info['version']}")
                print(f"File Size: {apk_info['file_size']}")
                print(f"Client ID: {client_id}")
                print(f"Secret ID: {secret_id}")
                for p in latest_paths:
                    print(f"Output: {p}")
                print("=" * 50)

                for cp in creds_paths:
                    print(f"Credentials saved to: {cp}")

                if validation_result['valid']:
                    print("\n🎉 SUCCESS: Credentials extracted and validated successfully!")
                    print("The authentication tokens are working and can be used.")
                else:
                    print("\n⚠️  WARNING: Credentials extracted but validation failed!")
                    print("The tokens may be outdated or there might be a network issue.")
                    print("You can still try using them, but they might not work.")
            else:
                print("\nFailed to extract credentials. Try again or check the code.")
        except Exception as e:
            print(f"An error occurred during the process: {e}")
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
    mode = None  # None -> both, 'tv' -> only tv, 'mobile' -> only mobile
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

    if '--tv' in args and '--mobile' in args:
        mode = None  # both
    elif '--tv' in args:
        mode = 'tv'
    elif '--mobile' in args:
        mode = 'mobile'

    if show_help:
        print("Usage: python main.py [--tv|--mobile] [--manual [path]] [--no-clean] [-h|--help]")
        print("")
        print("Options:")
        print("  --tv           Generate only Android TV outputs (latest-tv.json + tv credentials)")
        print("  --mobile       Generate only mobile outputs (latest.json + mobile credentials)")
        print("  --manual [p]   Use a local APK/XAPK/APKM file (optional path). If omitted, a file dialog opens.")
        print("  --no-clean     Keep decompiled files and downloaded APK folder after run (default is to clean)")
        print("  -h, --help     Show this help and exit")
        print("")
        print("Behavior:")
        print("  No flags => generates both latest-mobile.json and latest-tv.json, and both credential files.")
        sys.exit(0)

    if manual and not manual_path:
        print("--manual specified: please select an APK/XAPK/APKM file in the file dialog...")
        # Open a file picker on Windows if available
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

    analyzer = CrunchyrollAnalyzer()
    analyzer.run(manual_path, mode=mode, clean=clean)


if __name__ == "__main__":
    main()
