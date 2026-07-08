import requests
import base64
import os
from dotenv import load_dotenv
load_dotenv()

CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
ENV = os.getenv("EBAY_ENV")
base_url = "https://api.sandbox.ebay.com" if ENV == "sandbox" else "https://api.ebay.com"

credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
encoded_credentials = base64.b64encode(credentials.encode()).decode()

headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Authorization": f"Basic {encoded_credentials}"
}

data = {
    "grant_type": "client_credentials",
    "scope": "https://api.ebay.com/oauth/api_scope"
}

response = requests.post(f"{base_url}/identity/v1/oauth2/token", headers=headers, data=data)

if response.status_code == 200:
    token_data = response.json()
    access_token = token_data["access_token"]
    expires_in = token_data["expires_in"]  # seconds, usually 7200
    print("Token obtained:", access_token[:20] + "...")
    print("Expires in (sec):", expires_in)
else:
    print("Error:", response.status_code, response.text)