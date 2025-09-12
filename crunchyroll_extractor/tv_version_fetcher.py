import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Fetch latest Crunchyroll Android TV version by parsing Startpage SERP only.

STARTPAGE_URL = "https://www.startpage.com/sp/search"
DEFAULT_QUERY = "crunchyroll android tv site:apkmirror.com"

# Detect APKMirror links pointing to Crunchyroll's Android TV category
APKMIRROR_PREFIX_RE = re.compile(
    r"^https?://www\.apkmirror\.com/apk/(?:crunchyroll-llc-2|ellation-inc)/crunchyroll-everything-anime-android-tv/",
    re.IGNORECASE,
)


def _version_key(v: str):
    # Simple version sorting: X.Y.Z[.W] -> tuple of integers
    parts = [int(x) for x in v.split(".") if x.isdigit()]
    parts = (parts + [0, 0, 0, 0])[:4]
    return tuple(parts)


def _fetch_startpage_html(query: str) -> str:
    # Builds the Startpage POST request (mobile mode) with EN locale
    data = {
        "query": query,
        "t": "device",
        "lui": "english",
        "cat": "web",
        "abd": "1",
        "abe": "1",
    }
    body = urlencode(data).encode("utf-8")

    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "max-age=0",
        "content-type": "application/x-www-form-urlencoded",
        "dnt": "1",
        "origin": "https://www.startpage.com",
        "priority": "u=0, i",
        "referer": "https://www.startpage.com/",
        "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "sec-gpc": "1",
        "upgrade-insecure-requests": "1",
        "user-agent": (
            "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
        ),
    }

    req = Request(STARTPAGE_URL, data=body, headers=headers, method="POST")
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _parse_versions(html: str) -> set[str]:
    # Extracts all candidate versions from the Startpage HTML
    versions: set[str] = set()
    urls = re.findall(r"https?://[^\s'\"<>]+", html, flags=re.IGNORECASE)
    for url in urls:
        if APKMIRROR_PREFIX_RE.match(url) and "-release" in url:
            m = re.search(r"(\d+(?:-\d+){1,3})-release", url)
            if m:
                versions.add(m.group(1).replace("-", "."))

    # Some SERPs display: "About Crunchyroll (Android TV) X.Y.Z"
    text = re.sub(r"<[^>]+>", " ", html)
    m_all = re.findall(r"About\s+Crunchyroll\s*\(Android\s*TV\)\s+(\d+(?:\.\d+){1,3})", text, flags=re.IGNORECASE)
    for v in m_all:
        versions.add(v)

    return versions


def get_latest_android_tv_version(query: str = DEFAULT_QUERY) -> str | None:
    """Return the highest Android TV version found on Startpage SERP, or None."""
    html = _fetch_startpage_html(query)
    versions = _parse_versions(html)
    if not versions:
        return None
    return sorted(versions, key=_version_key, reverse=True)[0]
