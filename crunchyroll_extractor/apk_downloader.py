import os
import re
import zipfile
import shutil
from bs4 import BeautifulSoup
import cloudscraper

from .config import PROJECT_ROOT


class APKDownloader:
    """Downloads the latest Crunchyroll APK: APKCombo first, APKPremier as fallback."""

    def __init__(self):
        self.base_dir = PROJECT_ROOT
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self.scraper = cloudscraper.create_scraper()
        self.apkcombo_base = "https://apkcombo.app"
        self.apkcombo_default_url = "https://apkcombo.com/crunchyroll/com.crunchyroll.crunchyroid/"

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

    def _extract_filename_from_headers(self, resp, fallback_url: str) -> str:
        cd = resp.headers.get("Content-Disposition", "")
        if "filename=" in cd:
            m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, flags=re.IGNORECASE)
            if m:
                from urllib.parse import unquote
                return unquote(m.group(1))
        from urllib.parse import urlparse
        from urllib.parse import unquote as unq
        path = urlparse(fallback_url).path
        name = os.path.basename(path)
        return unq(name) or "download.xapk"

    # ---------- APKCombo ----------
    def _apkcombo_parse_url(self, input_url: str):
        try:
            from urllib.parse import urlparse
            u = urlparse(input_url)
            parts = [p for p in (u.path or "").split("/") if p]
            if len(parts) < 2:
                return None, None
            return parts[-2], parts[-1]
        except Exception:
            return None, None

    def _apkcombo_find_latest_variants_page(self, org: str, repo: str) -> str:
        versions_url = f"{self.apkcombo_base}/{org}/{repo}/old-versions"
        r = self.scraper.get(versions_url, headers=self.headers, timeout=30)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all('a', href=True):
            href = a['href']
            if ("download/phone-" in href) and href.endswith("-apk"):
                return href if href.startswith("http") else (self.apkcombo_base + href)
        for a in soup.find_all('a', href=True):
            href = a['href']
            if "/download/" in href:
                return href if href.startswith("http") else (self.apkcombo_base + href)
        return None

    def _apkcombo_find_bundle_variant_url(self, variants_page_url: str) -> str:
        r = self.scraper.get(variants_page_url, headers=self.headers, timeout=30)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        bundle_links = []
        for a in soup.find_all('a', href=True):
            text = " ".join(a.get_text(" ", strip=True).lower().split())
            href = a['href']
            if ("bundle" in text) or ("xapk" in text) or ("type=bundle" in href) or ("xapk" in href):
                bundle_links.append(href)
        if not bundle_links:
            for a in soup.find_all('a', href=True):
                href = a['href']
                if "/download/" in href and ("bundle" in href or "xapk" in href or "type=bundle" in href):
                    bundle_links.append(href)
        if not bundle_links:
            for a in soup.find_all('a', href=True):
                href = a['href']
                if "/download/" in href:
                    bundle_links.append(href)
        if not bundle_links:
            return None

        def pref_score(h: str):
            h_lower = h.lower()
            score = 0
            if "universal" in h_lower or "noarch" in h_lower:
                score -= 3
            if "nodpi" in h_lower:
                score -= 1
            if "arm64" in h_lower:
                score -= 1
            if ("bundle" in h_lower) or ("xapk" in h_lower) or ("type=bundle" in h_lower):
                score -= 2
            return score

        bundle_links.sort(key=pref_score)
        chosen = bundle_links[0]
        return chosen if chosen.startswith("http") else (self.apkcombo_base + chosen)

    def _apkcombo_get_checkin_param(self) -> str:
        r = self.scraper.get(f"{self.apkcombo_base}/checkin", headers=self.headers, timeout=20)
        if r.status_code != 200:
            return ""
        return (r.text or "").strip()

    def _apkcombo_append_checkin(self, url: str, checkin: str) -> str:
        if not checkin:
            return url
        sep = "&" if ("?" in url) else "?"
        return f"{url}{sep}{checkin}"

    # ---------- public API ----------
    def download_crunchyroll_apk(self):
        print("=== PHASE 1: DOWNLOADING CRUNCHYROLL APK ===")
        print("Fetching Crunchyroll download page...")
        try:
            apkcombo_result = self._download_from_apkcombo()
            if apkcombo_result:
                return apkcombo_result
        except Exception as e:
            print(f"APKCombo fetch failed: {e}")
        print("Falling back to APKPremier...")
        return self._download_from_apkpremier()

    def use_local_package(self, package_path: str):
        """Process a local XAPK/APKM/APK package selected by the user and return APK info.

        - If APK: copy to output dir and return.
        - If XAPK/APKM: extract, find largest .apk, copy and return.
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

        output_dir = os.path.join(self.base_dir, f"download_crunchyroll_v{version}")
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

        if lower.endswith('.xapk') or lower.endswith('.apkm') or lower.endswith('.zip'):
            ext = os.path.splitext(lower)[1]
            print(f"Extracting {ext.upper()} package...")
            extract_dir = os.path.join(output_dir, "package_extracted")
            os.makedirs(extract_dir, exist_ok=True)
            try:
                with zipfile.ZipFile(package_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
            except zipfile.BadZipFile:
                print("Package is not a valid ZIP/XAPK/APKM file.")
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

        print("Unsupported package format. Provide APK/XAPK/APKM.")
        return None

    def _download_from_apkcombo(self):
        print("Source: APKCombo")
        org, repo = self._apkcombo_parse_url(self.apkcombo_default_url)
        if not org or not repo:
            return None

        variants_page = self._apkcombo_find_latest_variants_page(org, repo)
        if not variants_page:
            return None

        version = "unknown"
        m = re.search(r"/download/phone-([0-9_\-.]+)-apk", variants_page)
        if m:
            version = self._normalize_version(m.group(1) or "")

        try:
            vp_resp = self.scraper.get(variants_page, headers=self.headers, timeout=20)
            if vp_resp.status_code == 200:
                txt = vp_resp.text
                m2 = re.search(r"Version\s*([0-9._-]{3,})", txt, re.IGNORECASE) or re.search(r"v([0-9._-]{3,})", txt, re.IGNORECASE)
                if m2:
                    version = self._normalize_version(m2.group(1))
        except Exception:
            pass

        print("Requesting download link...")
        variant_url = self._apkcombo_find_bundle_variant_url(variants_page)
        if not variant_url:
            return None
        checkin = self._apkcombo_get_checkin_param()
        final_url = self._apkcombo_append_checkin(variant_url, checkin)

        with self.scraper.get(final_url, headers=self.headers, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            size_str = self._human_size(total_size) if total_size else "Unknown size"

            filename = self._extract_filename_from_headers(r, final_url)
            ver_in_name = None
            mv = re.search(r"(\d+(?:[._-]\d+){1,3})", filename)
            if mv:
                ver_in_name = self._normalize_version(mv.group(1))
            if ver_in_name:
                version = ver_in_name

            output_dir = os.path.join(self.base_dir, f"download_crunchyroll_v{version}")
            os.makedirs(output_dir, exist_ok=True)
            xapk_filename = os.path.join(output_dir, f"Crunchyroll_v{version}.xapk")

            print(f"Found Crunchyroll APK version: {version}")
            print(f"Found download link for Crunchyroll v{version} ({size_str})")
            print(f"Downloading XAPK to {xapk_filename}...")

            with open(xapk_filename, 'wb') as f:
                downloaded = 0
                for chunk in r.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\rDownload progress: {percent:.1f}% ({downloaded/(1024*1024):.2f} MB / {total_size/(1024*1024):.2f} MB)", end="")
        print("\nDownload complete!")

        print("Extracting XAPK file...")
        xapk_extract_dir = os.path.join(output_dir, "xapk_extracted")
        os.makedirs(xapk_extract_dir, exist_ok=True)
        with zipfile.ZipFile(xapk_filename, 'r') as zip_ref:
            zip_ref.extractall(xapk_extract_dir)

        print("Finding main APK file...")
        largest_apk = None
        largest_size = 0
        for root, dirs, files in os.walk(xapk_extract_dir):
            for file in files:
                if file.endswith('.apk'):
                    fp = os.path.join(root, file)
                    sz = os.path.getsize(fp)
                    if sz > largest_size:
                        largest_size = sz
                        largest_apk = fp
        if not largest_apk:
            print("Error: Could not find any APK file in the extracted XAPK")
            return None

        print(f"Found main APK: {os.path.basename(largest_apk)} ({largest_size/(1024*1024):.2f} MB)")
        apk_filename = f"Crunchyroll_v{version}.apk"
        apk_destination = os.path.join(output_dir, apk_filename)
        shutil.copy2(largest_apk, apk_destination)
        print(f"Main APK saved as: {os.path.abspath(apk_destination)}")

        print("Cleaning up temporary files...")
        try:
            os.remove(xapk_filename)
        except Exception:
            pass
        shutil.rmtree(xapk_extract_dir, ignore_errors=True)
        print(f"APK processing complete! Version: {version}")

        return {
            'path': apk_destination,
            'version': version,
            'file_size': size_str if total_size else "Unknown size"
        }

    # ---------- APKPremier ----------
    def _download_from_apkpremier(self):
        print("Source: APKPremier")
        url = "https://apkpremier.com/com-crunchyroll-crunchyroid/crunchyroll/download/"
        response = self.scraper.get(url, headers=self.headers)
        if response.status_code != 200:
            print(f"Failed to access download page. Status code: {response.status_code}")
            return None

        html_content = response.text
        ajax_send_match = re.search(r"ajaxRequest\.send\('([^']+)'\);", html_content)
        if not ajax_send_match:
            print("Failed to find the Ajax request parameters")
            return None

        param_string = ajax_send_match.group(1)
        params = {}
        for param in param_string.split('&'):
            key, value = param.split('=', 1)
            params[key] = value
        if not all(key in params for key in ['getapk', 't', 'h', 's', 'vc', 'ver']):
            print("Missing required parameters")
            return None

        version = params['ver']
        t_value = params['t']
        h_value = params['h']
        vc_value = params['vc']

        print(f"Found Crunchyroll APK version: {version}")
        print("Requesting download link...")

        post_data = {
            "getapk": "yes",
            "t": t_value,
            "h": h_value,
            "s": "a",
            "vc": vc_value,
            "ver": version
        }
        post_headers = self.headers.copy()
        post_headers["Content-Type"] = "application/x-www-form-urlencoded"
        post_headers["Accept"] = "*/*"
        post_headers["Origin"] = "https://apkpremier.com"
        post_headers["Referer"] = url

        post_response = self.scraper.post(url, data=post_data, headers=post_headers)
        if post_response.status_code != 200:
            print(f"Failed to get download link. Status code: {post_response.status_code}")
            return None

        soup = BeautifulSoup(post_response.text, 'html.parser')
        size_info = soup.find('h2')
        file_size = "Unknown size"
        if size_info:
            size_match = re.search(r'\((.*?)\)', size_info.text)
            if size_match:
                file_size = size_match.group(1)

        download_link_elem = soup.select_one('.down_status_url a')
        if not download_link_elem:
            print("Failed to extract download link from response")
            return None

        download_url = download_link_elem['href']
        print(f"Found download link for Crunchyroll v{version} ({file_size})")

        output_dir = os.path.join(self.base_dir, f"download_crunchyroll_v{version}")
        os.makedirs(output_dir, exist_ok=True)

        xapk_filename = os.path.join(output_dir, f"Crunchyroll_v{version}.xapk")
        print(f"Downloading XAPK to {xapk_filename}...")
        with self.scraper.get(download_url, headers=self.headers, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            with open(xapk_filename, 'wb') as f:
                downloaded = 0
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\rDownload progress: {percent:.1f}% ({downloaded/(1024*1024):.2f} MB / {total_size/(1024*1024):.2f} MB)", end="")
        print("\nDownload complete!")

        print("Extracting XAPK file...")
        xapk_extract_dir = os.path.join(output_dir, "xapk_extracted")
        os.makedirs(xapk_extract_dir, exist_ok=True)
        with zipfile.ZipFile(xapk_filename, 'r') as zip_ref:
            zip_ref.extractall(xapk_extract_dir)

        print("Finding main APK file...")
        largest_apk = None
        largest_size = 0
        for root, dirs, files in os.walk(xapk_extract_dir):
            for file in files:
                if file.endswith('.apk'):
                    fp = os.path.join(root, file)
                    sz = os.path.getsize(fp)
                    if sz > largest_size:
                        largest_size = sz
                        largest_apk = fp
        if not largest_apk:
            print("Error: Could not find any APK file in the extracted XAPK")
            return None

        print(f"Found main APK: {os.path.basename(largest_apk)} ({largest_size/(1024*1024):.2f} MB)")
        apk_filename = f"Crunchyroll_v{version}.apk"
        apk_destination = os.path.join(output_dir, apk_filename)
        shutil.copy2(largest_apk, apk_destination)
        print(f"Main APK saved as: {os.path.abspath(apk_destination)}")

        print("Cleaning up temporary files...")
        os.remove(xapk_filename)
        shutil.rmtree(xapk_extract_dir)

        print(f"APK processing complete! Version: {version}")
        return {
            'path': apk_destination,
            'version': version,
            'file_size': file_size
        }
