import requests
import json
from typing import Optional, Tuple, Dict

class SecurityTester:
    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url
        self.token: Optional[str] = None
    
    def login(self, username: str) -> Tuple[bool, Dict]:
        """Test the login endpoint"""
        response = requests.post(
            f"{self.base_url}/login-test",
            json={"username": username}
        )
        data = response.json()
        
        if response.status_code == 200:
            self.token = data.get('token')
            print("✅ Login successful")
            print(f"Token: {self.token}")
        else:
            print("❌ Login failed")
            print(f"Error: {data.get('error')}")
            
        return response.status_code == 200, data
    
    def test_secure_endpoint(self) -> Tuple[bool, Dict]:
        """Test the secure endpoint"""
        if not self.token:
            print("❌ No token available. Please login first.")
            return False, {"error": "No token"}
            
        response = requests.post(
            f"{self.base_url}/secure-test",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        data = response.json()
        
        if response.status_code == 200:
            print("✅ Secure endpoint accessed successfully")
            print(f"Response: {json.dumps(data, indent=2)}")
        else:
            print("❌ Secure endpoint access failed")
            print(f"Error: {data.get('error')}")
            
        return response.status_code == 200, data
    
    def test_secure_endpoint_no_token(self) -> Tuple[bool, Dict]:
        """Test the secure endpoint without a token"""
        response = requests.post(f"{self.base_url}/secure-test")
        data = response.json()
        
        if response.status_code == 401:
            print("✅ Unauthorized access properly rejected")
        else:
            print("❌ Security check failed - endpoint accessible without token")
            
        return response.status_code == 401, data

def main():
    tester = SecurityTester()
    
    print("\n1. Testing Login...")
    success, _ = tester.login("test_user")
    
    if success:
        print("\n2. Testing Secure Endpoint with Token...")
        tester.test_secure_endpoint()
    
    print("\n3. Testing Secure Endpoint without Token...")
    tester.test_secure_endpoint_no_token()

if __name__ == "__main__":
    main() 