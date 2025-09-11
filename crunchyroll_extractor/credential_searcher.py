import os
import re
import time
import multiprocessing
from multiprocessing import Pool

from .config import DECOMPILED_DIR, TARGET_PATTERNS


class CredentialSearcher:
    """Scans smali files for static blocks containing known CR patterns and extracts client/secret IDs."""

    def __init__(self, decompiled_dir: str = DECOMPILED_DIR):
        self.decompiled_dir = decompiled_dir
        self.target_patterns = TARGET_PATTERNS

    def process_file(self, file_path: str):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                pattern_matches = sum(1 for p in self.target_patterns if p in content)
                if pattern_matches >= 2:
                    static_blocks = []
                    static_blocks.extend(re.findall(r'\.method static constructor <clinit>\(\)V[\s\S]+?\.end method', content))
                    static_blocks.extend(re.findall(r'\.method.*?static[\s\S]+?\.end method', content))
                    results = []
                    for block in static_blocks:
                        matches = sum(1 for p in self.target_patterns if p in block)
                        if matches >= 2:
                            secret_id_match = re.search(r'const-string\s+[vp]\d+,\s+"([A-Za-z0-9_-]{30,33})"', block)
                            secret_id = secret_id_match.group(1) if secret_id_match else None
                            if secret_id:
                                client_id_candidates = re.findall(r'const-string\s+[vp]\d+,\s+"([A-Za-z0-9_]{20})"', block)
                                client_id = "Not found"
                                if client_id_candidates:
                                    secret_pos = block.find(secret_id)
                                    closest = float('inf')
                                    for cand in client_id_candidates:
                                        pos = block.find(cand)
                                        dist = abs(pos - secret_pos)
                                        if dist < closest:
                                            closest = dist
                                            client_id = cand
                                if secret_id and client_id != "Not found":
                                    block_hash = hash(block)
                                    results.append({
                                        'file_path': file_path,
                                        'matches': matches,
                                        'secret_id': secret_id,
                                        'client_id': client_id,
                                        'block_hash': block_hash,
                                    })
                    return results
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
        return []

    def find_credentials(self):
        print("\n=== PHASE 3: SEARCHING FOR CREDENTIALS ===")
        if not os.path.exists(self.decompiled_dir):
            print(f"ERROR: Directory {self.decompiled_dir} does not exist!")
            return None, None

        print("Collecting .smali files...")
        smali_files = []
        for root, _dirs, files in os.walk(self.decompiled_dir):
            for file in files:
                if file.endswith(".smali"):
                    smali_files.append(os.path.join(root, file))
        print(f"Found {len(smali_files)} .smali files to process")

        start = time.time()
        num_processes = multiprocessing.cpu_count()
        print(f"Using {num_processes} CPU cores for parallel search")
        with Pool(processes=num_processes) as pool:
            results = pool.map(self.process_file, smali_files)

        all_results = []
        for lst in results:
            if lst:
                all_results.extend(lst)

        unique = {}
        for res in all_results:
            h = res['block_hash']
            if h not in unique or res['matches'] > unique[h]['matches']:
                unique[h] = res
        found_files = list(unique.values())

        total = time.time() - start
        print(f"Search completed in {total:.2f} seconds. Processed {len(smali_files)} files.")

        found_files.sort(key=lambda x: x['matches'], reverse=True)
        if found_files:
            print("\n===== SEARCH RESULTS =====")
            for i, res in enumerate(found_files[:5]):
                print(f"\nResult #{i+1} - {res['matches']} matches in {res['file_path']}")
                print(f"Secret ID: {res['secret_id']}")
                print(f"Client ID: {res['client_id']}")
                print("-" * 50)
            best = found_files[0]
            return best['secret_id'], best['client_id']
        else:
            print("No matching static blocks found after processing all files.")
            return None, None
