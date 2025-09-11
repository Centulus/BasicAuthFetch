import uuid
import random
import json
import cloudscraper


class CredentialValidator:
    """Validates extracted credentials by attempting an auth token request."""

    def __init__(self):
        self.scraper = cloudscraper.create_scraper()

    def _generate_random_device(self):
        devices = [
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
        device_type, device_name = random.choice(devices)
        device_id = str(uuid.uuid4())
        anonymous_id = str(uuid.uuid4())
        return device_type, device_name, device_id, anonymous_id

    def validate_credentials(self, auth_token: str, user_agent: str):
        print("\n=== PHASE 4: VALIDATING CREDENTIALS ===")
        print("Testing authentication with:")
        print(f"Auth Token: {auth_token}")
        print(f"User-Agent: {user_agent}")

        url = "https://www.crunchyroll.com/auth/v1/token"
        device_type, device_name, device_id, anonymous_id = self._generate_random_device()
        headers = {
            "Host": "www.crunchyroll.com",
            "Content-Length": "127",
            "authorization": f"Basic {auth_token}",
            "etp-anonymous-id": anonymous_id,
            "content-type": "application/x-www-form-urlencoded",
            "accept-encoding": "gzip",
            "user-agent": user_agent,
        }
        data = {
            "grant_type": "client_id",
            "device_id": device_id,
            "device_name": device_name,
            "device_type": device_type,
        }

        try:
            print(f"Sending authentication request to {url}...")
            print(f"Using device: {device_name} ({device_type})")
            response = self.scraper.post(url, headers=headers, data=data)
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
                        'response': response.text[:200] + "..." if len(response.text) > 200 else response.text,
                        'message': 'No access_token in response',
                    }
                except json.JSONDecodeError:
                    print("❌ Authentication FAILED - Non-JSON response")
                    return {
                        'valid': False,
                        'status_code': response.status_code,
                        'response': response.text[:200] + "..." if len(response.text) > 200 else response.text,
                        'message': 'Non-JSON response received',
                    }
            print(f"❌ Authentication FAILED - Status code: {response.status_code}")
            return {
                'valid': False,
                'status_code': response.status_code,
                'response': response.text[:200] + "..." if len(response.text) > 200 else response.text,
                'message': f'HTTP error: {response.status_code}',
            }
        except Exception as e:
            print(f"❌ Authentication ERROR - Request failed: {e}")
            return {
                'valid': False,
                'status_code': None,
                'error': str(e),
                'message': f'Request failed: {e}',
            }
