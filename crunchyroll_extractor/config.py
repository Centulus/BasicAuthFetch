import os

# Base paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DECOMPILED_DIR = os.path.join(PROJECT_ROOT, "decompiled")
APKTOOL_DIR = os.path.join(PROJECT_ROOT, "apktool")
OUTPUT_JSON_FILENAME = "latest.json"

# App-specific
USER_AGENT_TEMPLATE = "Crunchyroll/{} Android/13 okhttp/4.12.0"
TARGET_PATTERNS = [
    "https://www.crunchyroll.com",
    "https://static.crunchyroll.com",
    "https://imgsrv.crunchyroll.com/cdn-cgi/image/",
    "CR-AndroidMobile-CSAI-Prod-SVOD",
    "app-config-default-production.json",
    "6B9FA461",
]
