import os

# Base paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
OUTPUT_JSON_FILENAME_TV = "latest-tv.json"
OUTPUT_JSON_FILENAME_MOBILE = "latest-mobile.json"

# User-Agent templates  ({} = app version string)
USER_AGENT_TEMPLATE = "Crunchyroll/{} Android/13 okhttp/5.3.2"
PREFETCH_USER_AGENT_TEMPLATE = "Crunchyroll/{}_{} Android/13; MOBILE; {}; {}; {}"
TV_USER_AGENT_TEMPLATE = "Crunchyroll/ANDROIDTV/{} (Android 14; en-US; Chromecast)"

# DEX extraction: class holding TV client credentials
TV_CONSTANTS_CLASS = "Lcom/crunchyroll/api/util/Constants;"

# DEX extraction: strings that must co-occur with credentials in the same method
TARGET_PATTERNS: list[str] = [
    "https://www.crunchyroll.com",
    "https://static.crunchyroll.com",
    "https://imgsrv.crunchyroll.com/cdn-cgi/image/",
    "CR-AndroidMobile-CSAI-Prod-SVOD",
    "app-config-default-production.json",
    "6B9FA461",
]