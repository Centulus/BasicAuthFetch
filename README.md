# Crunchyroll Basic Auth Generator

Python script that automatically fetches and generates up‑to‑date Basic Auth credentials (Base64 pair + User-Agent) for the Crunchyroll Android app (mobile or Android TV).

## How It Works

1. Downloads the latest public Crunchyroll mobile APK (unless you supply your own file with `--manual`).
2. Decompiles it with ApkTool (auto‑installed locally into `apktool/` if missing).
3. Locates `client_id` and `client_secret` in smali using regex pattern scanning.
4. Builds the string `client_id:client_secret` and Base64‑encodes it.
5. Generates a JSON file (`latest-mobile.json` or `latest-tv.json`) containing: Base64 auth, User-Agent, version.
6. Writes a text credential summary file including validation results.

## Modes

The script supports three primary behaviors:

* Mobile (default) → outputs `latest-mobile.json` + `crunchyroll_credentials_mobile_v<version>.txt`.
* TV (`--tv`) → requires an Android TV APK / bundle (given or selected) and outputs `latest-tv.json` + `crunchyroll_credentials_tv_v<version>.txt`.
* Auto‑detection (when `--manual` is used without `--tv` or `--mobile`) → inspects the decompiled `AndroidManifest.xml`; if a LEANBACK category is found it switches to TV mode, else Mobile.

## CLI / Help

Show help:

```powershell
python .\main.py --help
```

```text
Usage: python main.py [--tv|--mobile] [--manual [path]] [--no-clean] [-h|--help]

Options:
	--tv [path]    Force Android TV mode. Optional path immediately after flag.
	--mobile       Force Android Mobile mode (default when no mode flag).
	--manual [p]   Use a local APK/XAPK/APKM; if path omitted a file dialog is opened.
								 With --manual only (no mode flag) the manifest is inspected to auto-detect TV.
	--no-clean     Keep decompiled and downloaded folders (default: remove).
	-h, --help     Show this help and exit.

Behavior:
	Default => mobile artifacts only (latest-mobile.json + credentials).
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
* The temporary downloaded APK version folder

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