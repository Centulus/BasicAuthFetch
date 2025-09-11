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
    USER_AGENT_TEMPLATE,
)
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

    def _generate_latest_json(self, client_id: str, secret_id: str, app_version: str) -> str:
        print("\n=== PHASE 5: GENERATING LATEST.JSON ===")
        auth_string = f"{client_id}:{secret_id}"
        base64_auth = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
        user_agent = USER_AGENT_TEMPLATE.format(app_version)
        latest_data = {
            "auth": base64_auth,
            "user-agent": user_agent,
            "app-version": app_version,
        }
        output_path = os.path.join(self.base_dir, OUTPUT_JSON_FILENAME)
        with open(output_path, 'w') as f:
            import json
            json.dump(latest_data, f, indent=2)
        print(f"Generated latest.json at: {output_path}")
        print(f"Basic Auth: {base64_auth}")
        print(f"User-Agent: {user_agent}")
        print(f"App Version: {app_version}")
        return output_path

    def run(self, manual_package_path: str | None = None):
        print("=== CRUNCHYROLL CREDENTIAL EXTRACTOR ===")
        print("This tool will download, decompile, and extract credentials from Crunchyroll APK")
        print("=" * 50)

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

            if not self.decompiler.decompile_apk(apk_info['path']):
                print("Failed to decompile the APK. Aborting.")
                return

            searcher = CredentialSearcher(self.decompiled_dir)
            secret_id, client_id = searcher.find_credentials()

            if secret_id and client_id:
                auth_string = f"{client_id}:{secret_id}"
                base64_auth = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
                user_agent = USER_AGENT_TEMPLATE.format(apk_info['version'])

                validation_result = self.validator.validate_credentials(base64_auth, user_agent)
                latest_json_path = self._generate_latest_json(client_id, secret_id, apk_info['version'])

                print("\n" + "=" * 50)
                if validation_result['valid']:
                    print("=== EXTRACTION AND VALIDATION SUCCESSFUL ===")
                else:
                    print("=== EXTRACTION COMPLETE - VALIDATION FAILED ===")

                print(f"Crunchyroll Version: {apk_info['version']}")
                print(f"File Size: {apk_info['file_size']}")
                print(f"Client ID: {client_id}")
                print(f"Secret ID: {secret_id}")
                print(f"latest.json: {latest_json_path}")
                print("=" * 50)

                creds_file = os.path.join(self.base_dir, f"crunchyroll_credentials_v{apk_info['version']}.txt")
                with open(creds_file, 'w') as f:
                    f.write(f"Crunchyroll Version: {apk_info['version']}\n")
                    f.write(f"File Size: {apk_info['file_size']}\n")
                    f.write(f"Client ID: {client_id}\n")
                    f.write(f"Secret ID: {secret_id}\n")
                    f.write(f"Basic Auth: {base64_auth}\n")
                    f.write(f"User-Agent: {user_agent}\n")
                    f.write(f"Validation Status: {'VALID' if validation_result['valid'] else 'INVALID'}\n")
                    f.write(f"Tested At: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n")
                print(f"Credentials saved to: {creds_file}")

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


def main():
    manual = False
    manual_path = None

    # Parse CLI flags (simple)
    args = [a for a in sys.argv[1:] if a]
    if '--manual' in args:
        manual = True
        # Optional path argument after --manual
        try:
            idx = args.index('--manual')
            if idx + 1 < len(args) and not args[idx + 1].startswith('-'):
                manual_path = args[idx + 1]
        except Exception:
            pass

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
    analyzer.run(manual_path)


if __name__ == "__main__":
    main()
