import os
import time
import subprocess
import platform
import shutil

from .config import DECOMPILED_DIR


class APKDecompiler:
    """Decompiles APK to smali using Apktool, then keeps smali-only output."""

    def __init__(self, apktool_path: str):
        self.decompiled_dir = DECOMPILED_DIR
        self.apktool_path = apktool_path

    def decompile_apk(self, apk_path: str, *, keep_manifest: bool = False) -> bool:
        print("\n=== PHASE 2: DECOMPILING APK ===")
        os.makedirs(self.decompiled_dir, exist_ok=True)
        if not os.path.exists(apk_path):
            print(f"APK file not found at {apk_path}")
            return False

        apk_filename = os.path.basename(apk_path)
        print(f"Decompiling {apk_filename}...")

        try:
            if platform.system().lower() == "windows":
                cmd = f'"{self.apktool_path}" d "{apk_path}" -o "{self.decompiled_dir}" -f'
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=True)
            else:
                process = subprocess.Popen([self.apktool_path, 'd', apk_path, '-o', self.decompiled_dir, '-f'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                print(line)
                if "Copying unknown files..." in line:
                    print("Detected completion message. Continuing without waiting for user input...")
                    time.sleep(2)
                    try:
                        if platform.system().lower() == "windows":
                            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        else:
                            process.terminate()
                    except Exception:
                        process.terminate()
                    break

            if os.path.exists(self.decompiled_dir) and any(d.startswith("smali") for d in os.listdir(self.decompiled_dir) if os.path.isdir(os.path.join(self.decompiled_dir, d))):
                self.cleanup_decompiled_dir(keep_manifest=keep_manifest)
                return True
            print("Decompilation may not have completed successfully. Check the output directory.")
            return False
        except Exception as e:
            print(f"Error decompiling {apk_filename}: {e}")
            return False

    def cleanup_decompiled_dir(self, *, keep_manifest: bool = False):
        """Remove everything except smali directories from the decompiled output.

        If keep_manifest=True, conserve AndroidManifest.xml at root for later parsing (e.g., TV version extraction).
        """
        print("Cleaning up decompiled directory...")
        items = os.listdir(self.decompiled_dir)
        smali_dirs = []
        for item in items:
            item_path = os.path.join(self.decompiled_dir, item)
            if os.path.isdir(item_path) and item.startswith("smali"):
                smali_dirs.append(item)
                continue
            if keep_manifest and item == "AndroidManifest.xml":
                # Preserve manifest if requested
                continue
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
            except Exception as e:
                print(f"Error removing {item}: {e}")
        if smali_dirs:
            print(f"Kept only smali directories: {', '.join(smali_dirs)}")
        else:
            print("No smali directories found to keep.")
