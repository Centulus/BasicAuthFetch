# Crunchyroll Basic Auth Generator

This is a Python script that automatically fetches and generates the latest Basic Auth credentials for Crunchyroll.

## How It Works

1. Downloads the latest Crunchyroll APK.
2. Decompiles the APK using ApkTool.
3. Extracts the `client_id` and `client_secret` from the smali files using regex-based pattern matching.
4. Encodes `client_id:client_secret` in Base64.
5. Generates the `latest.json` file containing the updated credentials.

## Purpose

This script was designed to facilitate updates for the Crunchyroll addon in Kodi. However, future functionality is not guaranteed, as it relies on pattern-based regex searching, which may break if Crunchyroll changes its implementation.

## Important Note

Make sure to update the `APKTOOL_PATH` variable in the script to point to your ApkTool installation [ApkTool Installation](https://apktool.org/docs/install/)

```python
APKTOOL_PATH = r"D:\ApkTool\apktool.bat"
```
