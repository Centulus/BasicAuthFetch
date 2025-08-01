import os
import re
import time
import shutil
import zipfile
import cloudscraper
import subprocess
import json
import base64
import multiprocessing
import platform
import stat
import uuid
import random
from multiprocessing import Pool
from bs4 import BeautifulSoup

# Constants and Configuration Settings
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DECOMPILED_DIR = os.path.join(BASE_DIR, "decompiled")
APKTOOL_DIR = os.path.join(BASE_DIR, "apktool")
APKTOOL_PATH = None
OUTPUT_JSON_FILENAME = "latest.json"
USER_AGENT_TEMPLATE = "Crunchyroll/{} Android/13 okhttp/4.12.0"
TARGET_PATTERNS = [
    "https://www.crunchyroll.com",
    "https://static.crunchyroll.com",
    "https://imgsrv.crunchyroll.com/cdn-cgi/image/",
    "CR-AndroidMobile-CSAI-Prod-SVOD",
    "app-config-default-production.json",
    "6B9FA461"
]


class APKToolInstaller:
    """Handles automatic installation of APKTool."""
    
    def __init__(self):
        self.base_dir = BASE_DIR
        self.apktool_dir = APKTOOL_DIR
        self.scraper = cloudscraper.create_scraper()
        self.is_windows = platform.system().lower() == "windows"
        self.is_linux = platform.system().lower() == "linux"
    
    def get_apktool_path(self):
        """Get the path to the installed APKTool executable."""
        if self.is_windows:
            return os.path.join(self.apktool_dir, "apktool.bat")
        else:
            return os.path.join(self.apktool_dir, "apktool")
    
    def is_apktool_installed(self):
        """Check if APKTool is already installed locally."""
        apktool_executable = self.get_apktool_path()
        apktool_jar = os.path.join(self.apktool_dir, "apktool.jar")
        
        return (os.path.exists(apktool_executable) and 
                os.path.exists(apktool_jar) and 
                os.path.getsize(apktool_jar) > 1000000)  # At least 1MB
    
    def install_apktool(self):
        """Download and install APKTool automatically."""
        print("=== INSTALLING APKTOOL ===")
        
        if not (self.is_windows or self.is_linux):
            print(f"Unsupported operating system: {platform.system()}")
            return False
        
        # Create apktool directory
        os.makedirs(self.apktool_dir, exist_ok=True)
        
        try:
            # Step 1: Get installation page and parse links
            print("Fetching APKTool installation instructions...")
            install_url = "https://apktool.org/docs/install/"
            response = self.scraper.get(install_url)
            
            if response.status_code != 200:
                print(f"Failed to access installation page. Status code: {response.status_code}")
                return False
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Step 2: Download wrapper script
            print(f"Downloading wrapper script for {platform.system()}...")
            if self.is_windows:
                wrapper_link = soup.find('a', href=re.compile(r'.*apktool\.bat$'))
                wrapper_filename = "apktool.bat"
            else:  # Linux
                wrapper_link = soup.find('a', href=re.compile(r'.*scripts/linux/apktool$'))
                wrapper_filename = "apktool"
            
            if not wrapper_link:
                print("Could not find wrapper script link")
                return False
            
            wrapper_url = wrapper_link['href']
            wrapper_path = os.path.join(self.apktool_dir, wrapper_filename)
            
            wrapper_response = self.scraper.get(wrapper_url)
            if wrapper_response.status_code != 200:
                print(f"Failed to download wrapper script. Status code: {wrapper_response.status_code}")
                return False
            
            with open(wrapper_path, 'wb') as f:
                f.write(wrapper_response.content)
            
            # Make executable on Linux
            if self.is_linux:
                os.chmod(wrapper_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
            
            print(f"Wrapper script saved to: {wrapper_path}")
            
            # Step 3: Get latest APKTool version from Bitbucket
            print("Fetching latest APKTool version...")
            bitbucket_url = "https://bitbucket.org/iBotPeaches/apktool/downloads"
            bitbucket_response = self.scraper.get(bitbucket_url)
            
            if bitbucket_response.status_code != 200:
                print(f"Failed to access Bitbucket downloads. Status code: {bitbucket_response.status_code}")
                return False
            
            bitbucket_soup = BeautifulSoup(bitbucket_response.text, 'html.parser')
            
            # Find the latest apktool jar download link
            jar_links = bitbucket_soup.find_all('a', href=re.compile(r'.*apktool_.*\.jar$'))
            if not jar_links:
                print("Could not find APKTool jar download links")
                return False
            
            # Get the first (latest) jar file
            latest_jar_link = jar_links[0]['href']
            if not latest_jar_link.startswith('http'):
                latest_jar_link = "https://bitbucket.org" + latest_jar_link
            
            # Extract version from filename
            jar_filename = latest_jar_link.split('/')[-1]
            version_match = re.search(r'apktool_(\d+\.\d+\.\d+)', jar_filename)
            version = version_match.group(1) if version_match else "unknown"
            
            print(f"Found APKTool version: {version}")
            
            # Step 4: Download APKTool jar
            print(f"Downloading {jar_filename}...")
            jar_response = self.scraper.get(latest_jar_link, stream=True)
            if jar_response.status_code != 200:
                print(f"Failed to download APKTool jar. Status code: {jar_response.status_code}")
                return False
            
            jar_path = os.path.join(self.apktool_dir, "apktool.jar")
            total_size = int(jar_response.headers.get('content-length', 0))
            
            with open(jar_path, 'wb') as f:
                downloaded = 0
                for chunk in jar_response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\rDownload progress: {percent:.1f}% ({downloaded/(1024*1024):.2f} MB / {total_size/(1024*1024):.2f} MB)", end="")
            
            print(f"\nAPKTool jar saved to: {jar_path}")
            
            # Make jar executable on Linux
            if self.is_linux:
                os.chmod(jar_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
            
            # Step 5: Verify installation by checking files
            print("Verifying APKTool installation...")
            
            # Check wrapper script
            if not os.path.exists(wrapper_path):
                print("Wrapper script is missing")
                return False
            
            wrapper_size = os.path.getsize(wrapper_path)
            if wrapper_size == 0:
                print("Wrapper script is empty")
                return False
            
            # Check jar file
            if not os.path.exists(jar_path):
                print("APKTool jar is missing")
                return False
            
            jar_size = os.path.getsize(jar_path)
            expected_size = total_size if total_size > 0 else 20000000  # Au moins 20MB
            
            if jar_size < expected_size * 0.95:  # Tolérance de 5%
                print(f"APKTool jar size mismatch. Expected ~{expected_size/(1024*1024):.1f}MB, got {jar_size/(1024*1024):.1f}MB")
                return False
            
            print("APKTool installation successful!")
            print(f"Wrapper script: {wrapper_size} bytes")
            print(f"APKTool jar: {jar_size/(1024*1024):.2f} MB")
            return True
                
        except Exception as e:
            print(f"Error installing APKTool: {e}")
            return False


class APKDownloader:
    """Handles downloading the latest Crunchyroll APK from the web."""
    
    def __init__(self):
        self.base_dir = BASE_DIR
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        # Initialiser cloudscraper
        self.scraper = cloudscraper.create_scraper()
    
    def download_crunchyroll_apk(self):
        """Download the latest Crunchyroll APK from APKPremier."""
        print("=== PHASE 1: DOWNLOADING CRUNCHYROLL APK ===")
        
        # Step 1: Initial GET request to get the HTML content
        print("Fetching Crunchyroll download page...")
        url = "https://apkpremier.com/com-crunchyroll-crunchyroid/crunchyroll/download/"
        
        # Utiliser cloudscraper au lieu de requests
        response = self.scraper.get(url, headers=self.headers)
        
        if response.status_code != 200:
            print(f"Failed to access download page. Status code: {response.status_code}")
            return None
        
        # Step 2: Extract parameters from the HTML
        html_content = response.text
        
        # Look for ajaxRequest.send line in JavaScript to get all the parameters
        ajax_send_match = re.search(r"ajaxRequest\.send\('([^']+)'\);", html_content)
        
        if not ajax_send_match:
            print("Failed to find the Ajax request parameters")
            return None
        
        # Get the full parameter string
        param_string = ajax_send_match.group(1)
        
        # Parse parameters
        params = {}
        for param in param_string.split('&'):
            key, value = param.split('=', 1)
            params[key] = value
        
        # Extract all required parameters
        if not all(key in params for key in ['getapk', 't', 'h', 's', 'vc', 'ver']):
            print("Missing required parameters")
            return None
        
        version = params['ver']
        t_value = params['t']
        h_value = params['h']
        vc_value = params['vc']
        
        print(f"Found Crunchyroll APK version: {version}")
        
        # Step 3: Send POST request to get download link
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
        
        # Step 4: Extract download URL from the response
        soup = BeautifulSoup(post_response.text, 'html.parser')
        
        # Find file size
        size_info = soup.find('h2')
        file_size = "Unknown size"
        if size_info:
            size_match = re.search(r'\((.*?)\)', size_info.text)
            if size_match:
                file_size = size_match.group(1)
        
        # Find download link
        download_link_elem = soup.select_one('.down_status_url a')
        if not download_link_elem:
            print("Failed to extract download link from response")
            return None
        
        download_url = download_link_elem['href']
        
        print(f"Found download link for Crunchyroll v{version} ({file_size})")
        
        # Create a dedicated directory for this version
        output_dir = os.path.join(self.base_dir, f"download_crunchyroll_v{version}")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Step 5: Download the XAPK file
        xapk_filename = os.path.join(output_dir, f"Crunchyroll_v{version}.xapk")
        print(f"Downloading XAPK to {xapk_filename}...")
        
        # Utiliser cloudscraper pour le téléchargement en streaming
        with self.scraper.get(download_url, headers=self.headers, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            
            with open(xapk_filename, 'wb') as f:
                downloaded = 0
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Simple progress display
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\rDownload progress: {percent:.1f}% ({downloaded/(1024*1024):.2f} MB / {total_size/(1024*1024):.2f} MB)", end="")
        
        print("\nDownload complete!")
        
        # Step 6: Extract the XAPK file
        print("Extracting XAPK file...")
        xapk_extract_dir = os.path.join(output_dir, "xapk_extracted")
        if not os.path.exists(xapk_extract_dir):
            os.makedirs(xapk_extract_dir)
        
        with zipfile.ZipFile(xapk_filename, 'r') as zip_ref:
            zip_ref.extractall(xapk_extract_dir)
        
        # Step 7: Find the largest APK file in the extracted XAPK
        print("Finding main APK file...")
        largest_apk = None
        largest_size = 0
        
        for root, dirs, files in os.walk(xapk_extract_dir):
            for file in files:
                if file.endswith('.apk'):
                    file_path = os.path.join(root, file)
                    file_size = os.path.getsize(file_path)
                    if file_size > largest_size:
                        largest_size = file_size
                        largest_apk = file_path
        
        if not largest_apk:
            print("Error: Could not find any APK file in the extracted XAPK")
            return None
        
        print(f"Found main APK: {os.path.basename(largest_apk)} ({largest_size/(1024*1024):.2f} MB)")
        
        # Copy the main APK to the output directory
        apk_filename = f"Crunchyroll_v{version}.apk"
        apk_destination = os.path.join(output_dir, apk_filename)
        shutil.copy2(largest_apk, apk_destination)
        print(f"Main APK saved as: {os.path.abspath(apk_destination)}")
        
        # Clean up temporary files
        print("Cleaning up temporary files...")
        # Remove the XAPK file
        os.remove(xapk_filename)
        # Remove extracted directory
        shutil.rmtree(xapk_extract_dir)
        
        print(f"APK processing complete! Version: {version}")
        
        # Return the path to the APK and its version
        return {
            'path': apk_destination,
            'version': version,
            'file_size': file_size
        }


class APKDecompiler:
    """Handles decompiling APK files to extract smali code."""
    
    def __init__(self, apktool_path):
        self.base_dir = BASE_DIR
        self.decompiled_dir = DECOMPILED_DIR
        self.apktool_path = apktool_path
    
    def decompile_apk(self, apk_path):
        """Decompile the provided APK file."""
        print("\n=== PHASE 2: DECOMPILING APK ===")
        
        # Create output directory if it doesn't exist
        os.makedirs(self.decompiled_dir, exist_ok=True)
        
        if not os.path.exists(apk_path):
            print(f"APK file not found at {apk_path}")
            return False
        
        # Decompile the APK file
        apk_filename = os.path.basename(apk_path)
        print(f"Decompiling {apk_filename}...")
        
        try:
            # Utiliser la même approche que pour le test, avec shell=True sur Windows
            if platform.system().lower() == "windows":
                cmd = f'"{self.apktool_path}" d "{apk_path}" -o "{self.decompiled_dir}" -f'
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    shell=True
                )
            else:
                process = subprocess.Popen(
                    [self.apktool_path, 'd', apk_path, '-o', self.decompiled_dir, '-f'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True
                )
            
            # Monitor the output in real-time
            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                print(line)
                
                # When we detect the final message before the prompt, we can consider it complete
                if "Copying unknown files..." in line:
                    print("Detected completion message. Continuing without waiting for user input...")
                    # Allow time for APKTool to finish writing files
                    time.sleep(2)
                    
                    # Terminate the process to bypass the "Press any key" prompt
                    try:
                        if platform.system().lower() == "windows":
                            # On Windows, use taskkill to forcefully terminate the process tree
                            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], 
                                          stdout=subprocess.DEVNULL, 
                                          stderr=subprocess.DEVNULL)
                        else:
                            process.terminate()
                    except Exception as kill_error:
                        print(f"Error terminating process: {kill_error}")
                        process.terminate()
                    break
            
            # Verify the decompilation was successful by checking if smali directories exist
            if os.path.exists(self.decompiled_dir) and any(d.startswith("smali") for d in os.listdir(self.decompiled_dir) if os.path.isdir(os.path.join(self.decompiled_dir, d))):
                self.cleanup_decompiled_dir()
                return True
            else:
                print("Decompilation may not have completed successfully. Check the output directory.")
                return False
                
        except Exception as e:
            print(f"Error decompiling {apk_filename}: {e}")
            return False
    
    def cleanup_decompiled_dir(self):
        """Keep only smali directories in the decompiled directory."""
        print("Cleaning up decompiled directory...")
        # Get all items in the decompiled directory
        items = os.listdir(self.decompiled_dir)
        
        # Keep track of smali directories
        smali_dirs = []
        
        for item in items:
            item_path = os.path.join(self.decompiled_dir, item)
            
            # Keep directories that start with "smali"
            if os.path.isdir(item_path) and item.startswith("smali"):
                smali_dirs.append(item)
                continue
            
            # Remove everything else
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


class CredentialSearcher:
    """Searches for Crunchyroll credentials in decompiled code."""
    
    def __init__(self, decompiled_dir):
        self.decompiled_dir = decompiled_dir
        # Target strings to look for in the static block
        self.target_patterns = TARGET_PATTERNS
    
    def process_file(self, file_path):
        """Process a single file to search for credential patterns."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
                # Check if any of our target patterns exist in this file at all
                pattern_matches = sum(1 for pattern in self.target_patterns if pattern in content)
                if pattern_matches >= 2:  # If at least 2 patterns match
                    
                    # Try different types of static block patterns
                    static_blocks = []
                    # Class static initializer
                    static_blocks.extend(re.findall(r'\.method static constructor <clinit>\(\)V[\s\S]+?\.end method', content))
                    # General static methods
                    static_blocks.extend(re.findall(r'\.method.*?static[\s\S]+?\.end method', content))
                    
                    results = []
                    for block in static_blocks:
                        matches = sum(1 for pattern in self.target_patterns if pattern in block)
                        # If enough patterns match, it's likely the right block
                        if matches >= 2:
                            # Find the secret ID (32 chars with possible dash)
                            secret_id_match = re.search(r'const-string\s+[vp]\d+,\s+"([A-Za-z0-9_-]{30,33})"', block)
                            secret_id = secret_id_match.group(1) if secret_id_match else None
                            
                            # If we found a secret ID, extract all 20-char strings to find client ID
                            if secret_id:
                                # Extract all potential client IDs (20-char strings)
                                client_id_candidates = re.findall(r'const-string\s+[vp]\d+,\s+"([A-Za-z0-9]{20})"', block)
                                
                                # Find the client ID closest to the secret ID in the code
                                client_id = "Not found"
                                if client_id_candidates:
                                    # Get positions of all matches in the block
                                    secret_pos = block.find(secret_id)
                                    closest_dist = float('inf')
                                    for candidate in client_id_candidates:
                                        
                                        pos = block.find(candidate)
                                        dist = abs(pos - secret_pos)
                                        if dist < closest_dist:
                                            closest_dist = dist
                                            client_id = candidate
                                
                                # Only add if both IDs are found
                                if secret_id and client_id != "Not found":
                                    # Use block hash to avoid duplicates
                                    block_hash = hash(block)
                                    results.append({
                                        'file_path': file_path,
                                        'matches': matches,
                                        'secret_id': secret_id,
                                        'client_id': client_id,
                                        'block_hash': block_hash
                                    })
                    
                    return results
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
        
        return []
    
    def find_credentials(self):
        """
        Search for client ID and secret ID in the decompiled code by looking for
        a static block containing specific URLs and patterns, then extracting
        nearby secret and client IDs using parallel processing.
        """
        print("\n=== PHASE 3: SEARCHING FOR CREDENTIALS ===")
        
        # Check if the directory exists
        if not os.path.exists(self.decompiled_dir):
            print(f"ERROR: Directory {self.decompiled_dir} does not exist!")
            return None, None
        
        # Collect all .smali files
        print("Collecting .smali files...")
        smali_files = []
        for root, dirs, files in os.walk(self.decompiled_dir):
            for file in files:
                if file.endswith(".smali"):
                    smali_files.append(os.path.join(root, file))
        
        print(f"Found {len(smali_files)} .smali files to process")
        
        # Start parallel processing
        start_time = time.time()
        num_processes = multiprocessing.cpu_count()
        print(f"Using {num_processes} CPU cores for parallel search")
        
        # Use multiprocessing to search files in parallel
        with Pool(processes=num_processes) as pool:
            results = pool.map(self.process_file, smali_files)
        
        # Flatten results list
        all_results = []
        for result_list in results:
            if result_list:
                all_results.extend(result_list)
        
        # Remove duplicates by block hash
        unique_results = {}
        for result in all_results:
            block_hash = result['block_hash']
            if block_hash not in unique_results or result['matches'] > unique_results[block_hash]['matches']:
                unique_results[block_hash] = result
        
        found_files = list(unique_results.values())
        
        total_time = time.time() - start_time
        print(f"Search completed in {total_time:.2f} seconds. Processed {len(smali_files)} files.")
        
        # Sort results by number of matches (highest first)
        found_files.sort(key=lambda x: x['matches'], reverse=True)
        
        # Print the top results
        if found_files:
            print("\n===== SEARCH RESULTS =====")
            for i, result in enumerate(found_files[:5]):  # Show top 5 results
                print(f"\nResult #{i+1} - {result['matches']} matches in {result['file_path']}")
                print(f"Secret ID: {result['secret_id']}")
                print(f"Client ID: {result['client_id']}")
                print("-" * 50)
            
            best = found_files[0]
            return best['secret_id'], best['client_id']
        else:
            print("No matching static blocks found after processing all files.")
            return None, None


class CredentialValidator:
    """Validates extracted Crunchyroll credentials by testing authentication."""
    
    def __init__(self):
        self.scraper = cloudscraper.create_scraper()
    
    def generate_random_device(self):
        """Generate random device information for authentication."""
        device_types = [
            "Samsung SM-G998B", "Samsung SM-G991B", "Samsung SM-N986B", "Samsung SM-A525F",
            "Xiaomi MI 11", "Xiaomi Redmi Note 10", "Xiaomi Mi 10T Pro", "Xiaomi 11T Pro",
            "OnePlus GM1913", "OnePlus KB2000", "OnePlus LE2117", "OnePlus AC2003",
            "Google Pixel 6", "Google Pixel 5", "Google Pixel 4a", "Google Pixel 7",
            "Huawei ELS-NX9", "Huawei VOG-L29", "Huawei ANE-LX1", "Huawei CLT-L29",
            "Sony XQ-BC72", "Sony XQ-AT72", "Sony G8441", "Sony H8314",
            "Oppo CPH2173", "Oppo CPH2069", "Oppo PDEM30", "Oppo PEGM00",
            "Vivo V2154A", "Vivo V2120A", "Vivo V2031A", "Vivo V1955A",
            "Motorola XT2125-4", "Motorola XT2041-4", "Motorola XT2153-1",
            "Nokia TA-1198", "Nokia TA-1340", "Nokia TA-1388"
        ]
        
        device_names = [
            "Galaxy S21 Ultra", "Galaxy S21", "Galaxy Note 20 Ultra", "Galaxy A52",
            "Mi 11", "Redmi Note 10", "Mi 10T Pro", "11T Pro",
            "OnePlus 7T", "OnePlus 8T", "OnePlus 9", "OnePlus Nord",
            "Pixel 6", "Pixel 5", "Pixel 4a", "Pixel 7",
            "P40 Pro", "P30 Pro", "P20 Lite", "P30",
            "Xperia 1 III", "Xperia 5 II", "Xperia XZ2", "Xperia XZ3",
            "Find X3 Pro", "Reno4 Pro", "A94", "Find X2",
            "X60 Pro", "V21", "Y20s", "X51",
            "Edge 20", "G9 Plus", "One 5G",
            "X20", "G50", "C31"
        ]
        
        device_type = random.choice(device_types)
        device_name = random.choice(device_names)
        device_id = str(uuid.uuid4())
        anonymous_id = str(uuid.uuid4())
        
        return device_type, device_name, device_id, anonymous_id
    
    def validate_credentials(self, auth_token, user_agent):
        """
        Validate if the auth_token and user_agent pair is valid.
        
        Args:
            auth_token (str): Basic authorization token
            user_agent (str): User-Agent string
        
        Returns:
            dict: Validation result with status and details
        """
        print("\n=== PHASE 4: VALIDATING CREDENTIALS ===")
        print(f"Testing authentication with:")
        print(f"Auth Token: {auth_token}")
        print(f"User-Agent: {user_agent}")
        
        url = "https://www.crunchyroll.com/auth/v1/token"
        
        device_type, device_name, device_id, anonymous_id = self.generate_random_device()
        
        headers = {
            "Host": "www.crunchyroll.com",
            "Content-Length": "127",
            "authorization": f"Basic {auth_token}",
            "etp-anonymous-id": anonymous_id,
            "content-type": "application/x-www-form-urlencoded",
            "accept-encoding": "gzip",
            "user-agent": user_agent
        }
        
        data = {
            "grant_type": "client_id",
            "device_id": device_id,
            "device_name": device_name,
            "device_type": device_type
        }
        
        try:
            print(f"Sending authentication request to {url}...")
            print(f"Using device: {device_name} ({device_type})")
            
            response = self.scraper.post(url, headers=headers, data=data)
            
            # Check if request returns 200
            if response.status_code == 200:
                try:
                    # Check if response contains access_token
                    response_json = response.json()
                    if "access_token" in response_json:
                        print("✅ Authentication SUCCESSFUL - Access token obtained")
                        return {
                            'valid': True,
                            'status_code': response.status_code,
                            'access_token': response_json.get('access_token', '')[:50] + "...",
                            'token_type': response_json.get('token_type', ''),
                            'expires_in': response_json.get('expires_in', ''),
                            'message': 'Credentials are valid and working'
                        }
                    else:
                        print("❌ Authentication FAILED - No access_token in response")
                        return {
                            'valid': False,
                            'status_code': response.status_code,
                            'response': response.text[:200] + "..." if len(response.text) > 200 else response.text,
                            'message': 'No access_token in response'
                        }
                except json.JSONDecodeError:
                    print("❌ Authentication FAILED - Non-JSON response")
                    return {
                        'valid': False,
                        'status_code': response.status_code,
                        'response': response.text[:200] + "..." if len(response.text) > 200 else response.text,
                        'message': 'Non-JSON response received'
                    }
            else:
                print(f"❌ Authentication FAILED - Status code: {response.status_code}")
                return {
                    'valid': False,
                    'status_code': response.status_code,
                    'response': response.text[:200] + "..." if len(response.text) > 200 else response.text,
                    'message': f'HTTP error: {response.status_code}'
                }
                
        except Exception as e:
            print(f"❌ Authentication ERROR - Request failed: {e}")
            return {
                'valid': False,
                'status_code': None,
                'error': str(e),
                'message': f'Request failed: {e}'
            }


class CrunchyrollAnalyzer:
    """Main class that orchestrates the entire process."""
    
    def __init__(self):
        self.base_dir = BASE_DIR
        self.decompiled_dir = DECOMPILED_DIR
        
        # Initialize APKTool installer
        self.apktool_installer = APKToolInstaller()
        
        # Initialize components (APKDecompiler will be initialized after APKTool setup)
        self.downloader = APKDownloader()
        self.decompiler = None
        self.validator = CredentialValidator()
    
    def setup_apktool(self):
        """Setup APKTool (install if necessary)."""
        global APKTOOL_PATH
        
        print("=== APKTOOL SETUP ===")
        
        if self.apktool_installer.is_apktool_installed():
            print("APKTool is already installed locally.")
            APKTOOL_PATH = self.apktool_installer.get_apktool_path()
            print(f"Using APKTool at: {APKTOOL_PATH}")
            return True
        else:
            print("APKTool not found. Installing automatically...")
            if self.apktool_installer.install_apktool():
                APKTOOL_PATH = self.apktool_installer.get_apktool_path()
                print(f"APKTool installed successfully at: {APKTOOL_PATH}")
                return True
            else:
                print("Failed to install APKTool automatically.")
                return False
    
    def generate_latest_json(self, client_id, secret_id, app_version):
        """Generate latest.json file with authentication details."""
        print("\n=== PHASE 5: GENERATING LATEST.JSON ===")
        
        # Create Basic Auth string (base64 encoded clientid:secretid)
        auth_string = f"{client_id}:{secret_id}"
        auth_bytes = auth_string.encode('ascii')
        base64_auth = base64.b64encode(auth_bytes).decode('ascii')
        
        # Format user agent with app version
        user_agent = USER_AGENT_TEMPLATE.format(app_version)
        
        # Create the JSON object
        latest_data = {
            "auth": base64_auth,
            "user-agent": user_agent,
            "app-version": app_version
        }
        
        # Save to file
        output_path = os.path.join(self.base_dir, OUTPUT_JSON_FILENAME)
        with open(output_path, 'w') as f:
            json.dump(latest_data, f, indent=2)
        
        print(f"Generated latest.json at: {output_path}")
        print(f"Basic Auth: {base64_auth}")
        print(f"User-Agent: {user_agent}")
        print(f"App Version: {app_version}")
        
        return output_path
    
    def run(self):
        """Run the full analysis process."""
        print("=== CRUNCHYROLL CREDENTIAL EXTRACTOR ===")
        print("This tool will download, decompile, and extract credentials from Crunchyroll APK")
        print("=" * 50)
        
        try:
            # Phase 0: Setup APKTool
            if not self.setup_apktool():
                print("APKTool setup failed. Aborting.")
                return
            
            # Initialize decompiler now that we have APKTool path
            self.decompiler = APKDecompiler(APKTOOL_PATH)
            
            # Phase 1: Download the APK
            apk_info = self.downloader.download_crunchyroll_apk()
            if not apk_info:
                print("Failed to download the APK. Aborting.")
                return
            
            # Phase 2: Decompile the APK
            if not self.decompiler.decompile_apk(apk_info['path']):
                print("Failed to decompile the APK. Aborting.")
                return
            
            # Phase 3: Search for credentials
            searcher = CredentialSearcher(self.decompiled_dir)
            secret_id, client_id = searcher.find_credentials()
            
            # Validation and Final Results
            if secret_id and client_id:
                # Phase 4: Validate credentials
                auth_string = f"{client_id}:{secret_id}"
                auth_bytes = auth_string.encode('ascii')
                base64_auth = base64.b64encode(auth_bytes).decode('ascii')
                user_agent = USER_AGENT_TEMPLATE.format(apk_info['version'])
                
                validation_result = self.validator.validate_credentials(base64_auth, user_agent)
                
                # Phase 5: Generate latest.json
                latest_json_path = self.generate_latest_json(client_id, secret_id, apk_info['version'])
                
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
                
                # Save credentials to a file with validation info
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
                
                # Summary message
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
    """Main entry point for the application."""
    analyzer = CrunchyrollAnalyzer()
    analyzer.run()


if __name__ == "__main__":
    main()
