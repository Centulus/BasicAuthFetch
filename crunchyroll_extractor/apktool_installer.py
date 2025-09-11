import os
import re
import platform
import stat
import zipfile
from bs4 import BeautifulSoup
import cloudscraper

from .config import APKTOOL_DIR


class APKToolInstaller:
    """Downloads and installs Apktool locally (wrapper + jar)."""

    def __init__(self):
        self.apktool_dir = APKTOOL_DIR
        self.scraper = cloudscraper.create_scraper()
        self.is_windows = platform.system().lower() == "windows"
        self.is_linux = platform.system().lower() == "linux"

    def get_apktool_path(self) -> str:
        if self.is_windows:
            return os.path.join(self.apktool_dir, "apktool.bat")
        return os.path.join(self.apktool_dir, "apktool")

    def is_apktool_installed(self) -> bool:
        exe = self.get_apktool_path()
        jar = os.path.join(self.apktool_dir, "apktool.jar")
        return os.path.exists(exe) and os.path.exists(jar) and os.path.getsize(jar) > 1_000_000

    def install_apktool(self) -> bool:
        print("=== INSTALLING APKTOOL ===")
        if not (self.is_windows or self.is_linux):
            print(f"Unsupported operating system: {platform.system()}")
            return False

        os.makedirs(self.apktool_dir, exist_ok=True)
        try:
            # 1) Wrapper script
            print(f"Downloading wrapper script for {platform.system()}...")
            if self.is_windows:
                wrapper_url = "https://raw.githubusercontent.com/iBotPeaches/Apktool/master/scripts/windows/apktool.bat"
                wrapper_filename = "apktool.bat"
            else:
                wrapper_url = "https://raw.githubusercontent.com/iBotPeaches/Apktool/master/scripts/linux/apktool"
                wrapper_filename = "apktool"

            wrapper_path = os.path.join(self.apktool_dir, wrapper_filename)
            w_resp = self.scraper.get(wrapper_url, headers={"Accept": "text/plain"})
            if w_resp.status_code != 200 or not w_resp.content:
                print(f"Failed to download wrapper (status {w_resp.status_code}).")
                return False
            with open(wrapper_path, "wb") as f:
                f.write(w_resp.content)
            if self.is_linux:
                os.chmod(wrapper_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
            print(f"Wrapper script saved to: {wrapper_path}")

            # 2) Latest jar from GitHub releases
            print("Fetching latest APKTool version...")
            latest_jar_link = None
            jar_filename = None
            selected_version = None
            try:
                api_url = "https://api.github.com/repos/iBotPeaches/Apktool/releases/latest"
                api_headers = {"Accept": "application/vnd.github+json"}
                api_resp = self.scraper.get(api_url, headers=api_headers)
                if api_resp.status_code == 200:
                    data = api_resp.json()
                    tag = (data.get("tag_name") or "").lstrip("v")
                    if tag:
                        selected_version = tag
                    for asset in (data.get("assets") or []):
                        name = asset.get("name") or ""
                        dl = asset.get("browser_download_url") or ""
                        if re.match(r"apktool_\d+\.\d+\.\d+\.jar$", name):
                            latest_jar_link = dl
                            jar_filename = name
                            break
                    if not latest_jar_link and selected_version:
                        jar_filename = f"apktool_{selected_version}.jar"
                        latest_jar_link = f"https://github.com/iBotPeaches/Apktool/releases/download/v{selected_version}/{jar_filename}"
            except Exception as e:
                print(f"GitHub API error: {e}")

            if not latest_jar_link:
                try:
                    rel_url = "https://github.com/iBotPeaches/Apktool/releases"
                    rel_resp = self.scraper.get(rel_url)
                    if rel_resp.status_code == 200:
                        soup = BeautifulSoup(rel_resp.text, "html.parser")
                        anchors = soup.find_all(
                            "a",
                            href=re.compile(r"/iBotPeaches/Apktool/releases/download/v[0-9.]+/apktool_\d+\.\d+\.\d+\.jar"),
                        )
                        items = []
                        for a in anchors:
                            href = a.get("href") or ""
                            m = re.search(r"apktool_(\d+\.\d+\.\d+)\.jar", href)
                            ver = m.group(1) if m else None
                            if href and ver:
                                items.append({"href": "https://github.com" + href, "version": ver})
                        def _v(v):
                            try:
                                return tuple(int(x) for x in (v or "0.0.0").split("."))
                            except Exception:
                                return (0, 0, 0)
                        items.sort(key=lambda c: _v(c["version"]), reverse=True)
                        if items:
                            latest_jar_link = items[0]["href"]
                            selected_version = items[0]["version"]
                            jar_filename = latest_jar_link.split("/")[-1]
                except Exception as e:
                    print(f"GitHub releases parse error: {e}")

            if not latest_jar_link:
                print("Could not find APKTool jar download links")
                return False

            if not jar_filename:
                jar_filename = latest_jar_link.split("/")[-1]
            vm = re.search(r"apktool_(\d+\.\d+\.\d+)", jar_filename)
            version = vm.group(1) if vm else (selected_version or "unknown")
            print(f"Found APKTool version: {version}")

            # 3) Download jar
            print(f"Downloading {jar_filename}...")
            jar_path = os.path.join(self.apktool_dir, "apktool.jar")
            jr = self.scraper.get(latest_jar_link, stream=True)
            if jr.status_code != 200:
                print(f"Failed to download APKTool jar. Status code: {jr.status_code}")
                return False
            total_size = int(jr.headers.get("content-length", 0))
            with open(jar_path, "wb") as f:
                downloaded = 0
                for chunk in jr.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        percent = (downloaded / total_size) * 100
                        print(f"\rDownload progress: {percent:.1f}% ({downloaded/(1024*1024):.2f} MB / {total_size/(1024*1024):.2f} MB)", end="")
            print(f"\nAPKTool jar saved to: {jar_path}")

            # 4) Verify sizes
            print("Verifying APKTool installation...")
            if not os.path.exists(wrapper_path) or os.path.getsize(wrapper_path) == 0:
                print("Wrapper script validation failed")
                return False
            if not os.path.exists(jar_path):
                print("APKTool jar is missing")
                return False
            jar_size = os.path.getsize(jar_path)
            if total_size and jar_size < total_size * 0.90:
                print("APKTool jar size mismatch")
                return False
            if not total_size and jar_size < 10 * 1024 * 1024:
                print("APKTool jar seems too small")
                return False
            print("APKTool installation successful!")
            print(f"Wrapper script: {os.path.getsize(wrapper_path)} bytes")
            print(f"APKTool jar: {jar_size/(1024*1024):.2f} MB")
            return True
        except Exception as e:
            print(f"Error installing APKTool: {e}")
            return False
