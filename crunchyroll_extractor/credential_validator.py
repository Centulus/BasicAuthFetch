import base64
import uuid
import random
import json
import secrets
from curl_cffi import requests
from .config import PREFETCH_USER_AGENT_TEMPLATE

class CredentialValidator:
    """Validates extracted credentials by attempting an auth token request."""

    def __init__(self):
        # Impersonate Chrome 110 to match a modern browser TLS fingerprint
        self.session = requests.Session(impersonate="chrome110")

    def _generate_random_device(self, category: str = "mobile"):
        """Return a random (device_type, device_name, device_id, anonymous_id)."""
        mobile_devices = [
            ("Samsung SM-G998B", "Galaxy S21 Ultra"),
            ("Samsung SM-G991B", "Galaxy S21"),
            ("Samsung SM-N986B", "Galaxy Note 20 Ultra"),
            ("Samsung SM-A525F", "Galaxy A52"),
            ("Xiaomi MI 11", "Mi 11"),
            ("Xiaomi Redmi Note 10", "Redmi Note 10"),
            ("Xiaomi Mi 10T Pro", "Mi 10T Pro"),
            ("Xiaomi 11T Pro", "11T Pro"),
            ("OnePlus GM1913", "OnePlus 7T"),
            ("OnePlus KB2000", "OnePlus 8T"),
            ("OnePlus LE2117", "OnePlus 9"),
            ("OnePlus AC2003", "OnePlus Nord"),
            ("Google Pixel 6", "Pixel 6"),
            ("Google Pixel 5", "Pixel 5"),
            ("Google Pixel 4a", "Pixel 4a"),
            ("Google Pixel 7", "Pixel 7"),
            ("Huawei ELS-NX9", "P40 Pro"),
            ("Huawei VOG-L29", "P30 Pro"),
            ("Huawei ANE-LX1", "P20 Lite"),
            ("Huawei CLT-L29", "P30"),
            ("Sony XQ-BC72", "Xperia 1 III"),
            ("Sony XQ-AT72", "Xperia 5 II"),
            ("Sony G8441", "Xperia XZ2"),
            ("Sony H8314", "Xperia XZ3"),
            ("Oppo CPH2173", "Find X3 Pro"),
            ("Oppo CPH2069", "Reno4 Pro"),
            ("Oppo PDEM30", "A94"),
            ("Oppo PEGM00", "Find X2"),
            ("Vivo V2154A", "X60 Pro"),
            ("Vivo V2120A", "V21"),
            ("Vivo V2031A", "Y20s"),
            ("Vivo V1955A", "X51"),
            ("Motorola XT2125-4", "Edge 20"),
            ("Motorola XT2041-4", "G9 Plus"),
            ("Motorola XT2153-1", "One 5G"),
            ("Nokia TA-1198", "X20"),
            ("Nokia TA-1340", "G50"),
            ("Nokia TA-1388", "C31"),
        ]
        tv_devices = [
            ("Chromecast HD", "Chromecast"),
            ("Chromecast 4K", "Chromecast 4K"),
            ("Nvidia SHIELD Android TV", "NVIDIA Shield"),
            ("Nvidia SHIELD Pro", "NVIDIA Shield Pro"),
            ("MiBOX S (MDZ-22-AB)", "Mi Box S"),
            ("MiBOX 4K", "Mi Box 4K"),
            ("FireTV AFTMM", "Fire TV Stick 4K"),
            ("FireTV AFTSSS", "Fire TV Stick 4K Max"),
            ("Google TV GTV-BT-002", "Chromecast Google TV"),
            ("Philips TV PUS8506", "Philips 8506"),
            ("Sony BRAVIA KD-55XH90", "Bravia XH90"),
            ("Sony BRAVIA KD-55A80J", "Bravia A80J"),
            ("Hisense ATV A7GQ", "Hisense A7G"),
            ("TCL TV C825", "TCL C825"),
            ("TCL TV C735", "TCL C735"),
            ("Shield Android TV", "Shield TV"),
            ("Amazon AFTT", "Fire TV 4K"),
        ]
        pool = tv_devices if category.lower() == 'tv' else mobile_devices
        device_type, device_name = random.choice(pool)
        device_id = str(uuid.uuid4())
        anonymous_id = str(uuid.uuid4())
        return device_type, device_name, device_id, anonymous_id

    def _classify_network_error(self, exception):
        """Classify network exceptions into user-friendly error categories."""
        error_str = str(exception).lower()
        
        # Windows socket errors
        if 'winerror 10013' in error_str:
            return "Connection blocked (no internet or network restrictions)"
        if 'winerror 10060' in error_str or 'timed out' in error_str:
            return "Connection timeout (network unreachable)"
        if 'winerror 10061' in error_str or 'connection refused' in error_str:
            return "Connection refused (service unavailable)"
        
        # Generic connection errors
        if 'failed to establish' in error_str or 'connection error' in error_str:
            return "Connection failed (check internet connection)"
        if 'max retries exceeded' in error_str:
            return "Connection failed (network unavailable)"
        
        # SSL/TLS errors
        if 'ssl' in error_str or 'certificate' in error_str:
            return "SSL/TLS error (certificate issue)"
        
        # DNS errors
        if 'nodename nor servname provided' in error_str or 'name resolution' in error_str:
            return "DNS resolution failed (check internet connection)"
        
        return f"Network error: {str(exception)[:80]}"

    def _generate_datadog_headers(self):
        """Generate random Datadog telemetry headers."""
        trace_id = secrets.randbits(63)
        parent_id = secrets.randbits(63)
        tid = secrets.token_hex(8) + "00000000"
        rsid = str(uuid.uuid4())
        trace_id_hex = f"{trace_id:016x}"
        parent_id_hex = f"{parent_id:016x}"
        traceparent = f"00-{tid}{trace_id_hex}-{parent_id_hex}-00"

        return {
            "x-datadog-trace-id": str(trace_id),
            "x-datadog-parent-id": str(parent_id),
            "x-datadog-origin": "rum",
            "x-datadog-tags": f"_dd.p.tid={tid},_dd.p.rsid={rsid}",
            "x-datadog-sampling-priority": "0",
            "traceparent": traceparent,
            "tracestate": f"dd=p:{parent_id};s:0;o:rum"
        }

    def _prefetch_mobile_cookie(self, user_agent: str, version_code: str, device_name: str, device_type: str):
        """Prefetch Cloudflare cookie using the CF-protected XML endpoint."""
        url = "https://www.crunchyroll.com/i18n/cr-android-app/katamari/en-US.xml"
        
        version = user_agent.split('/')[1].split()[0] if '/' in user_agent else "3.105.1"
        prefetch_ua = PREFETCH_USER_AGENT_TEMPLATE.format(version, version_code, device_name, device_type.split()[0], device_name.split()[0])
        
        headers = {
            "User-Agent": prefetch_ua,
            "Accept": "application/json",
            "Accept-Charset": "UTF-8",
            "x-datadog-sampling-priority": "0",
            "traceparent": self._generate_datadog_headers()["traceparent"],
            "Host": "www.crunchyroll.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
        }
        try:
            self.session.get(url, headers=headers)
        except Exception:
            pass  # Fail gracefully

    def validate_credentials(self, auth_token: str, user_agent: str, version_code: str = "1102"):
        print("\n=== PHASE 4: VALIDATING CREDENTIALS ===")
        print("Testing authentication with:")
        print(f"Auth Token: {auth_token}")
        print(f"User-Agent: {user_agent}")

        url = "https://www.crunchyroll.com/auth/v1/token"
        device_type, device_name, device_id, anonymous_id = self._generate_random_device('mobile')

        print("Prefetching Cloudflare __cf_bm cookie...")
        self._prefetch_mobile_cookie(user_agent, version_code, device_name, device_type)

        headers = {
            "Host": "www.crunchyroll.com",
            "authorization": f"Basic {auth_token}",
            "etp-anonymous-id": anonymous_id,
            "content-type": "application/x-www-form-urlencoded",
            "accept-encoding": "gzip",
            "user-agent": user_agent,
        }
        
        headers.update(self._generate_datadog_headers())

        data = {
            "grant_type": "client_id",
            "device_id": device_id,
            "device_name": device_name,
            "device_type": device_type,
        }

        try:
            print(f"Sending authentication request to {url}...")
            print(f"Using device: {device_name} ({device_type})")
            response = self.session.post(url, headers=headers, data=data)
            if response.status_code == 200:
                try:
                    response_json = response.json()
                    if "access_token" in response_json:
                        print("✅ Authentication SUCCESSFUL - Access token obtained")
                        return {
                            'valid': True,
                            'status_code': response.status_code,
                            'access_token': response_json.get('access_token', '')[:50] + "...",
                            'token_type': response_json.get('token_type', ''),
                            'expires_in': response_json.get('expires_in', ''),
                            'message': 'Credentials are valid and working',
                        }
                    print("❌ Authentication FAILED - No access_token in response")
                    return {
                        'valid': False,
                        'status_code': response.status_code,
                        'error_reason': 'Invalid credentials (no access token)',
                        'response': response.text[:200] + "..." if len(response.text) > 200 else response.text,
                        'message': 'No access_token in response',
                    }
                except json.JSONDecodeError:
                    print("❌ Authentication FAILED - Non-JSON response")
                    return {
                        'valid': False,
                        'status_code': response.status_code,
                        'error_reason': 'Invalid API response (parse error)',
                        'response': response.text[:200] + "..." if len(response.text) > 200 else response.text,
                        'message': 'Non-JSON response received',
                    }
            error_msg = f"Authentication failed (HTTP {response.status_code})"
            print(f"❌ {error_msg}")
            return {
                'valid': False,
                'status_code': response.status_code,
                'error_reason': error_msg,
                'response': response.text[:200] + "..." if len(response.text) > 200 else response.text,
                'message': f'HTTP error: {response.status_code}',
            }
        except Exception as e:
            error_msg = self._classify_network_error(e)
            print(f"❌ {error_msg}")
            return {
                'valid': False,
                'status_code': None,
                'error_reason': error_msg,
                'error': str(e),
                'message': f'Request failed: {e}',
            }

    def validate_tv_credentials(self, client_id: str, client_secret: str, user_agent: str):
        """Validate TV credentials via a 3-step flow: CF cookie seed → anonymous token → device code."""
        print("\n=== PHASE 4 (TV): VALIDATING TV CREDENTIALS ===")
        session = self.session
        base = "https://www.crunchyroll.com"
        browse_url = f"{base}/content/v2/discover/browse?locale=en-US&sort_by=popularity&n=1600"
        
        print("[TV] Step 1: Initial browse request to obtain __cf_bm cookie...")
        headers1 = {
            "User-Agent": user_agent,
            "Authorization": "Bearer",
            "Accept": "application/json",
            "Accept-Charset": "UTF-8",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
        }
        cf_cookie = None
        try:
            r1 = session.get(browse_url, headers=headers1)
            cf_cookie = r1.cookies.get('__cf_bm')
            if cf_cookie:
                print(f"[TV] Got __cf_bm cookie fragment: {cf_cookie[:20]}...")
            else:
                print("[TV] Warning: __cf_bm cookie not obtained (continuing anyway).")
        except Exception as e:
            error_msg = self._classify_network_error(e)
            print(f"[TV] ❌ {error_msg}")
            return {
                'valid': False,
                'error_reason': error_msg,
                'error_step': 'browse_request',
            }

        print("[TV] Step 2: Anonymous token request (client_id + client_secret)...")
        anon_url = f"{base}/auth/v1/token"
        anonymous_id = str(uuid.uuid4())
        form_data = {
            "grant_type": "client_id",
            "scope": "offline_access",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        headers2 = {
            "ETP-Anonymous-ID": anonymous_id,
            "User-Agent": user_agent,
            "Accept": "application/json",
            "Accept-Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
        }
        access_token = None
        try:
            r2 = session.post(anon_url, data=form_data, headers=headers2)
            if r2.status_code == 200:
                try:
                    js = r2.json()
                    access_token = js.get('access_token')
                    if access_token:
                        print("[TV] Anonymous access_token acquired (truncated):", access_token[:40] + "...")
                    else:
                        print("[TV] No access_token in anonymous response.")
                        return {
                            'valid': False,
                            'error_reason': 'Invalid credentials (no access token)',
                            'error_step': 'anonymous_token',
                        }
                except Exception:
                    print("[TV] Failed to parse JSON from anonymous token response.")
                    return {
                        'valid': False,
                        'error_reason': 'Invalid API response (parse error)',
                        'error_step': 'anonymous_token',
                    }
            else:
                error_msg = f"Authentication failed (HTTP {r2.status_code})"
                print(f"[TV] ❌ {error_msg}")
                return {
                    'valid': False,
                    'error_reason': error_msg,
                    'error_step': 'anonymous_token',
                }
        except Exception as e:
            error_msg = self._classify_network_error(e)
            print(f"[TV] ❌ {error_msg}")
            return {
                'valid': False,
                'error_reason': error_msg,
                'error_step': 'anonymous_token',
            }

        print("[TV] Step 3: Device code generation...")
        device_url = f"{base}/auth/v1/device/code"
        basic_auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers3 = {
            "User-Agent": user_agent,
            "Accept": "application/json",
            "Accept-Charset": "UTF-8",
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": "0",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
        }
        user_code = None
        device_code = None
        try:
            r3 = session.post(device_url, headers=headers3)
            if r3.status_code == 200:
                try:
                    js = r3.json()
                    user_code = js.get('user_code')
                    device_code = js.get('device_code')
                    if user_code and device_code:
                        print(f"[TV] Device code OK: user_code={user_code} device_code={device_code}")
                    else:
                        print("[TV] Missing user_code/device_code in response.")
                        return {
                            'valid': False,
                            'error_reason': 'Invalid API response (missing device codes)',
                            'error_step': 'device_code',
                        }
                except Exception:
                    print("[TV] Failed to parse JSON from device code response.")
                    return {
                        'valid': False,
                        'error_reason': 'Invalid API response (parse error)',
                        'error_step': 'device_code',
                    }
            else:
                error_msg = f"Device code request failed (HTTP {r3.status_code})"
                print(f"[TV] ❌ {error_msg}")
                return {
                    'valid': False,
                    'error_reason': error_msg,
                    'error_step': 'device_code',
                }
        except Exception as e:
            error_msg = self._classify_network_error(e)
            print(f"[TV] ❌ {error_msg}")
            return {
                'valid': False,
                'error_reason': error_msg,
                'error_step': 'device_code',
            }

        return {
            'valid': True,
            'cf_bm': cf_cookie,
            'anonymous_access_token_present': access_token is not None,
            'user_code': user_code,
            'device_code': device_code,
        }
