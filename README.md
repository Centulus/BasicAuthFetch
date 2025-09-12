# Crunchyroll Basic Auth Generator

This is a Python script that automatically fetches and generates the latest Basic Auth credentials for Crunchyroll.

## How It Works

1. Downloads the latest Crunchyroll APK.  
2. Decompiles the APK using ApkTool.  
3. Extracts the `client_id` and `client_secret` from the smali files using regex-based pattern matching.  
4. Encodes `client_id:client_secret` in Base64.  
5. Generates the `latest.json` file containing the updated credentials.  

## Cleanup and Help

- By default, the tool cleans up the `decompiled/` folder and the temporary APK version folder after it finishes.
- To keep these folders for inspection, pass `--no-clean`.

Show help:

```powershell
python .\main.py --help
```

Usage summary:

```text
python main.py [--tv|--mobile] [--manual [path]] [--no-clean] [-h|--help]

Options:
	--tv           Generate only Android TV outputs (latest-tv.json + tv credentials)
	--mobile       Generate only mobile outputs (latest.json + mobile credentials)
	--manual [p]   Use a local APK/XAPK/APKM file (optional path). If omitted, a file dialog opens.
	--no-clean     Keep decompiled files and downloaded APK folder after run (default is to clean)
	-h, --help     Show this help and exit

Behavior:
	No flags => generates both latest-mobile.json and latest-tv.json, and both credential files.
```

## Purpose

This script was designed to facilitate updates for the Crunchyroll addon in Kodi. However, future functionality is not guaranteed, as it relies on pattern-based regex searching, which may break if Crunchyroll changes its implementation.

## Important Note

Make sure to update the `APKTOOL_PATH` variable in the script to point to your [ApkTool Installation](https://apktool.org/docs/install/)

```python
APKTOOL_PATH = r"D:\ApkTool\apktool.bat"
```

## Feature Status

- [x] Compatibility: Windows  
- [x] Compatibility: Linux  
- [x] Automated setup  

## Usage Disclaimer

This script is provided for educational use only.