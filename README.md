# Crunchyroll Basic Auth Generator

Python script to generate Basic Auth credentials (Base64 pair + User-Agent) for the Crunchyroll Android app (mobile or Android TV) from a package you provide locally. Online APK fetching has been removed: always supply your own APK/XAPK/APKM.

## How It Works

1. You provide an APK/XAPK/APKM/APKS (or ZIP) via a positional path or the file dialog.
2. It decompiles the APK with ApkTool (auto‑installed locally into `apktool/` if missing).
3. It locates `client_id` and `client_secret` in smali using regex pattern scanning.
4. It builds the string `client_id:client_secret` and Base64‑encodes it.
5. It generates a JSON file (`latest-mobile.json` or `latest-tv.json`) containing: Base64 auth, User-Agent, version.
6. It writes a text credential summary file including validation results.

## Modes

The script supports three behaviors:

* Mobile (`--mobile`) → outputs `latest-mobile.json` + `crunchyroll_credentials_mobile_v<version>.txt`. A local package is mandatory.
* TV (`--tv`) → requires an Android TV APK / bundle and outputs `latest-tv.json` + `crunchyroll_credentials_tv_v<version>.txt`.
* Auto‑detection (default when no mode flag is provided) → inspects the decompiled `AndroidManifest.xml`; if a LEANBACK category (or leanback feature) is found it switches to TV mode, else Mobile.

## CLI / Help

Show help:

```powershell
python .\main.py --help
```

```text
Usage: python main.py [--tv|--mobile] [path] [--no-clean] [-h|--help]

Options:
	--tv [path]    Force Android TV mode.
	--mobile       Force Android Mobile mode.
	path           Optional positional path to APK/XAPK/APKM/APKS/ZIP. If omitted, a file dialog opens.
	--no-clean     Keep decompiled and downloaded folders (default: remove).
	-h, --help     Show this help and exit.

Behavior:
	Default (no --tv/--mobile) => auto-detect via manifest: TV if LEANBACK (or leanback feature), else Mobile.
	Mobile => latest-mobile.json + credentials (version inferred from filename when possible).
	TV mode => credentials from Constants.smali + version from AndroidManifest (versionName_versionCode).
```

## Outputs

| Mode   | JSON                | Credential file                                   | Contains |
|--------|---------------------|---------------------------------------------------|----------|
| Mobile | `latest-mobile.json`| `crunchyroll_credentials_mobile_v<ver>.txt`       | Base64 auth, mobile UA, shortened version |
| TV     | `latest-tv.json`    | `crunchyroll_credentials_tv_v<ver>.txt`           | Base64 auth, TV UA, manifest-derived version |

Field `auth` = Base64(`client_id:client_secret`).

## Cleanup

By default the script removes:
* The `decompiled/` directory
* The temporary extracted package folder

Keep them with `--no-clean` for debugging/inspection.

## ApkTool

No manual path needed: the tool automatically downloads the proper wrapper + latest jar into `apktool/` (Windows & Linux). If already present and valid, it's reused.

## Purpose

Simplifies updating credentials for tools such as a Crunchyroll Kodi addon. Future reliability is not guaranteed: the logic relies on static regex patterns that may break if the app changes.

## Feature Status

* [x] Windows
* [x] Linux
* [x] Automatic ApkTool installation

## Disclaimer

Provided for educational use only. You are responsible for how you use it.