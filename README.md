# Crunchyroll Basic Auth Generator

Generate Basic Auth credentials (Base64 pair + User‑Agent) for the Crunchyroll Android app (Mobile or Android TV) from a local package you provide.

No decompilation required. Credentials are extracted directly from the DEX binary in < 2 s.

## How It Works

1. You provide a package path (APK/XAPK/APKM/APKS/ZIP) or a folder with APKs.
2. The container is opened in memory; no files are extracted to disk.
3. `AndroidManifest.xml` (binary AXML) is parsed to get `versionName`, `versionCode`, and TV/mobile detection.
4. DEX files (`classes*.dex`) are scanned for credentials:
   - **Mobile** – finds the method referencing known Crunchyroll URLs and picks the `client_id`/`secret` pair closest together in bytecode.
   - **TV** – reads string constants directly from `com.crunchyroll.api.util.Constants`.
5. Version strings:
   - Mobile: `versionName` (e.g. `3.110.1`)
   - TV: `versionName_versionCode` (e.g. `3.65.0_22347`)
6. A JSON file is generated with Base64 auth, User‑Agent, and app version.
7. A credential summary text file is written, including validation results.

## Modes

* Mobile (`--mobile`) → outputs `latest-mobile.json` + `crunchyroll_credentials_mobile_v<versionName>.txt`.
* TV (`--tv`) → use an Android TV APK/bundle; outputs `latest-tv.json` + `crunchyroll_credentials_tv_v<versionName_versionCode>.txt`.
* Auto‑detected (default) → reads the binary manifest to decide TV (`LEANBACK_LAUNCHER` present) vs Mobile.

## CLI / Help

Show help:

```bash
python main.py --help
```

```text
Usage: python main.py [--tv|--mobile] [path] [-h|--help]

Options:
  --tv [path]    Force Android TV mode. Optional path immediately after flag.
  --mobile       Force Android Mobile mode.
  path           Local APK/XAPK/APKM/APKS/ZIP path. If omitted, a file dialog opens.
  -h, --help     Show this help and exit.

Behavior:
  Default (no --tv/--mobile) => auto‑detect via manifest: TV if LEANBACK_LAUNCHER present, else Mobile.
  Version source is AndroidManifest.xml (binary):
    • Mobile => versionName
    • TV    => versionName_versionCode
```

## Outputs

| Mode   | JSON                 | Credential file                                              | Contains |
|--------|----------------------|--------------------------------------------------------------|----------|
| Mobile | `latest-mobile.json` | `crunchyroll_credentials_mobile_v<versionName>.txt`          | Base64 auth, UA (mobile), versionName |
| TV     | `latest-tv.json`     | `crunchyroll_credentials_tv_v<versionName_versionCode>.txt`  | Base64 auth, UA (TV), versionName_versionCode |

Field `auth` = Base64(`client_id:client_secret`).

## Requirements

```
curl_cffi
```

Install: `pip install curl_cffi`

## Feature Status

* [x] Windows
* [x] Linux
* [x] Auto TV/mobile detection
* [x] No APKTool or Java required

## Purpose

Simplifies updating credentials for tools such as a Crunchyroll Kodi addon. Future reliability is not guaranteed: the logic relies on static patterns that may break if the app's code structure changes significantly.

## Disclaimer

Provided for educational use only. You are responsible for how you use it.
