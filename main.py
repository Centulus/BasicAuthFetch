"""Crunchyroll credential extractor – no decompilation required.

Reads DEX string tables and binary AndroidManifest.xml directly from the
APK/APKM file. No APKTool, no Java, no smali files. Typical runtime: 1-3 s.

Usage:
    python main.py [--tv|--mobile] path/to/app.apkm [--no-clean] [-h]
"""
import base64
import json
import os
import sys
import time

try:
    import tkinter as tk
    from tkinter import filedialog
except Exception:
    tk = None
    filedialog = None

from crunchyroll_extractor.config import (
    PROJECT_ROOT,
    OUTPUT_JSON_FILENAME_TV,
    OUTPUT_JSON_FILENAME_MOBILE,
    USER_AGENT_TEMPLATE,
    TV_USER_AGENT_TEMPLATE,
)
from crunchyroll_extractor.apk_reader import load_package
from crunchyroll_extractor.axml_parser import parse_manifest
from crunchyroll_extractor.dex_extractor import DexExtractor
from crunchyroll_extractor.credential_validator import CredentialValidator


# ─────────────────────────────────────────────────────────────────────────────

def _short_mobile_version(version: str) -> str:
    """Strip trailing build segment from 4-part version (e.g. 3.91.1.960 → 3.91.1)."""
    if not version:
        return version
    parts = version.split('.')
    if len(parts) > 3 and all(p.isdigit() for p in parts):
        return '.'.join(parts[:-1])
    return version


def _write_json(path: str, data: dict) -> None:
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2)


class CrunchyrollAnalyzer:
    """Orchestrates DEX-based extraction, validation and output."""

    def __init__(self) -> None:
        self.validator = CredentialValidator()
        self.extractor = DexExtractor(verbose=True)

    # ── output helpers ───────────────────────────────────────────────────────

    def _emit_mobile(
        self,
        client_id: str,
        secret_id: str,
        app_version: str,
        file_size: str,
        validation: dict,
    ) -> None:
        auth_str   = f"{client_id}:{secret_id}"
        b64_auth   = base64.b64encode(auth_str.encode()).decode()
        user_agent = USER_AGENT_TEMPLATE.format(app_version)

        json_path = os.path.join(PROJECT_ROOT, OUTPUT_JSON_FILENAME_MOBILE)
        _write_json(json_path, {
            'auth': b64_auth,
            'user-agent': user_agent,
            'app-version': app_version,
        })

        creds_path = os.path.join(PROJECT_ROOT, f"crunchyroll_credentials_mobile_v{app_version}.txt")
        with open(creds_path, 'w', encoding='utf-8') as fh:
            fh.write(f"Crunchyroll Version: {app_version}\n")
            fh.write(f"File Size: {file_size}\n")
            fh.write(f"Client ID: {client_id}\n")
            fh.write(f"Secret ID: {secret_id}\n")
            fh.write(f"Basic Auth: {b64_auth}\n")
            fh.write(f"User-Agent: {user_agent}\n")
            fh.write(f"Validation Status: {'VALID' if validation['valid'] else 'INVALID'}\n")
            fh.write(f"Tested At: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n")

        print(f"\n=== PHASE 3: OUTPUT ===")
        print(f"Output JSON : {json_path}")
        print(f"Credentials : {creds_path}")
        print(f"Basic Auth  : {b64_auth}")
        print(f"User-Agent  : {user_agent}")
        print(f"App Version : {app_version}")

    def _emit_tv(
        self,
        client_id: str,
        secret_id: str,
        version_name: str,
        version_code: str,
        validation: dict,
    ) -> None:
        tv_version = f"{version_name}_{version_code}"
        auth_str   = f"{client_id}:{secret_id}"
        b64_auth   = base64.b64encode(auth_str.encode()).decode()
        user_agent = TV_USER_AGENT_TEMPLATE.format(tv_version)

        json_path = os.path.join(PROJECT_ROOT, OUTPUT_JSON_FILENAME_TV)
        _write_json(json_path, {
            'auth': b64_auth,
            'user-agent': user_agent,
            'app-version': tv_version,
        })

        creds_path = os.path.join(PROJECT_ROOT, f"crunchyroll_credentials_tv_v{tv_version}.txt")
        with open(creds_path, 'w', encoding='utf-8') as fh:
            fh.write(f"Crunchyroll TV Version: {tv_version}\n")
            fh.write(f"Client ID: {client_id}\n")
            fh.write(f"Secret ID: {secret_id}\n")
            fh.write(f"Basic Auth: {b64_auth}\n")
            fh.write(f"User-Agent: {user_agent}\n")
            fh.write(f"CF_BM Cookie: {validation.get('cf_bm') or 'None'}\n")
            fh.write(f"Anonymous Access Token Present: {validation.get('anonymous_access_token_present')}\n")
            fh.write(f"User Code: {validation.get('user_code') or 'None'}\n")
            fh.write(f"Device Code: {validation.get('device_code') or 'None'}\n")
            fh.write(f"Validation Status: {'VALID' if validation['valid'] else 'INVALID'}\n")
            fh.write(f"Tested At: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n")

        print(f"\n=== PHASE 3: OUTPUT ===")
        print(f"Output JSON : {json_path}")
        print(f"Credentials : {creds_path}")
        print(f"Basic Auth  : {b64_auth}")
        print(f"User-Agent  : {user_agent}")
        print(f"TV Version  : {tv_version}")

    # ── main entry point ─────────────────────────────────────────────────────

    def run(self, package_path: str, *, mode: str = 'auto') -> bool:
        """Run the full extraction pipeline.

        mode: 'auto' | 'tv' | 'mobile'
        Returns True on success, False on failure.
        """
        print("=== CRUNCHYROLL CREDENTIAL EXTRACTOR (no-decompile) ===")
        print(f"Package : {package_path}")
        print("=" * 55)

        t_start = time.time()

        # ── Phase 1: load package ────────────────────────────────────────────
        print("\n=== PHASE 1: LOADING PACKAGE ===")
        contents = load_package(package_path)
        if contents is None:
            print("ERROR: Failed to load package.")
            return False
        print(f"Loaded {contents.apk_name} ({contents.file_size_str})")
        print(f"  DEX files : {len(contents.dex_files)}")

        # ── Phase 2: parse manifest ──────────────────────────────────────────
        print("\n=== PHASE 2: PARSING MANIFEST ===")
        manifest = parse_manifest(contents.manifest_data)
        version_name = manifest['versionName'] or 'unknown'
        version_code = manifest['versionCode'] or '0'
        detected_tv  = manifest['is_tv']
        print(f"  versionName : {version_name}")
        print(f"  versionCode : {version_code}")
        print(f"  Android TV  : {detected_tv}")

        # resolve mode
        if mode == 'auto':
            resolved = 'tv' if detected_tv else 'mobile'
            print(f"  [AUTO] resolved mode → {resolved.upper()}")
        else:
            resolved = mode

        # ── Phase 3: extract credentials ─────────────────────────────────────
        if resolved == 'tv':
            client_id, secret_id = self.extractor.find_tv_credentials(contents.dex_files)
        else:
            client_id, secret_id = self.extractor.find_mobile_credentials(contents.dex_files)

        # TV fallback: if mobile scan found nothing and manifest says TV, try TV extractor
        if not (client_id and secret_id) and resolved == 'mobile' and detected_tv:
            print("\n[Fallback] Mobile scan found nothing; manifest indicates TV. Trying TV extractor…")
            client_id, secret_id = self.extractor.find_tv_credentials(contents.dex_files)
            if client_id and secret_id:
                resolved = 'tv'

        if not (client_id and secret_id):
            print("\nERROR: Credentials not found.")
            return False

        # ── Phase 4: validate ────────────────────────────────────────────────
        if resolved == 'tv':
            tv_version = f"{version_name}_{version_code}"
            user_agent = TV_USER_AGENT_TEMPLATE.format(tv_version)
            print(f"\n=== PHASE 4: VALIDATING TV CREDENTIALS ===")
            validation = self.validator.validate_tv_credentials(client_id, secret_id, user_agent)
        else:
            app_version = _short_mobile_version(version_name)
            auth_str    = f"{client_id}:{secret_id}"
            b64_auth    = base64.b64encode(auth_str.encode()).decode()
            user_agent  = USER_AGENT_TEMPLATE.format(app_version)
            print(f"\n=== PHASE 4: VALIDATING MOBILE CREDENTIALS ===")
            validation = self.validator.validate_credentials(b64_auth, user_agent, version_code)

        valid = validation.get('valid', False)

        # ── Phase 5: write output ────────────────────────────────────────────
        if resolved == 'tv':
            self._emit_tv(client_id, secret_id, version_name, version_code, validation)
        else:
            app_version = _short_mobile_version(version_name)
            self._emit_mobile(client_id, secret_id, app_version, contents.file_size_str, validation)

        # ── Summary ──────────────────────────────────────────────────────────
        elapsed = time.time() - t_start
        print("\n" + "=" * 55)
        if valid:
            print("=== EXTRACTION AND VALIDATION SUCCESSFUL ===")
        else:
            print("=== EXTRACTION COMPLETE – VALIDATION FAILED ===")
            err = validation.get('error_reason', 'Unknown error')
            print(f"Reason: {err}")
        print(f"Total time : {elapsed:.2f}s")
        print("=" * 55)
        return valid


# ─────────────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str]) -> tuple[str | None, str, bool]:
    """Return (package_path, mode, show_help)."""
    args = [a for a in argv if a]
    if '-h' in args or '--help' in args:
        return None, 'auto', True

    explicit_tv     = '--tv'     in args
    explicit_mobile = '--mobile' in args
    if explicit_tv:
        mode = 'tv'
    elif explicit_mobile:
        mode = 'mobile'
    else:
        mode = 'auto'

    # Extract path: first positional arg not starting with '-'
    path: str | None = None
    skip_next = False
    for i, a in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if a in ('--tv', '--mobile', '--no-clean', '-h', '--help'):
            # value flags that consume next token as path
            if a in ('--tv', '--mobile') and i + 1 < len(args) and not args[i + 1].startswith('-') and path is None:
                path = args[i + 1]
                skip_next = True
            continue
        if not a.startswith('-') and path is None:
            path = a

    return path, mode, False


def main() -> None:
    package_path, mode, show_help = _parse_args(sys.argv[1:])

    if show_help:
        print("Usage: python main.py [--tv|--mobile] [path] [-h|--help]")
        print()
        print("Options:")
        print("  --tv [path]    Force Android TV mode.")
        print("  --mobile       Force Android Mobile mode.")
        print("  path           Local APK/XAPK/APKM/APKS/ZIP path.")
        print("  -h, --help     Show this help and exit.")
        print()
        print("No APKTool required. Credentials are extracted directly from DEX files.")
        return

    if not package_path:
        print("Select the APK/XAPK/APKM package…")
        chosen: str | None = None
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

    if not package_path:
        print("ERROR: No package provided. Use --help for usage.")
        sys.exit(1)

    analyzer = CrunchyrollAnalyzer()
    ok = analyzer.run(package_path, mode=mode)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
