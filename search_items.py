import requests
import base64
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
load_dotenv()

CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
ENV = os.getenv("EBAY_ENV")

base_url = "https://api.sandbox.ebay.com" if ENV == "sandbox" else "https://api.ebay.com"

credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
encoded_credentials = base64.b64encode(credentials.encode()).decode()


def get_access_token():
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_credentials}"
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope"
    }
    response = requests.post(f"{base_url}/identity/v1/oauth2/token", headers=headers, data=data)
    response.raise_for_status()
    return response.json()["access_token"]


def search_items(keyword, limit=10):
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
    }
    params = {
        "q": keyword,
        "limit": limit,
        "filter": "buyingOptions:{AUCTION}"
    }
    response = requests.get(
        f"{base_url}/buy/browse/v1/item_summary/search",
        headers=headers,
        params=params
    )
    response.raise_for_status()
    return response.json()


def get_usd_to_inr_rate():
    try:
        response = requests.get("https://open.er-api.com/v6/latest/USD")
        response.raise_for_status()
        data = response.json()
        return data["rates"]["INR"]
    except Exception as e:
        print("Could not fetch live rate, using fallback:", e)
        return 83.0


def get_item_details(item_id, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
    }
    response = requests.get(f"{base_url}/buy/browse/v1/item/{item_id}", headers=headers)
    response.raise_for_status()
    return response.json()


def format_time_left(end_date_str):
    if not end_date_str:
        return "Unknown"
    end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    delta = end_date - now
    if delta.total_seconds() <= 0:
        return "Ended"
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes}m"


def print_auction_summary(results):
    items = results.get("itemSummaries", [])
    usd_to_inr = get_usd_to_inr_rate()
    token = get_access_token()

    print(f"Found {len(items)} auction items (1 USD = {usd_to_inr:.2f} INR)\n")

    for item in items:
        title = item.get("title")
        item_id = item.get("itemId")

        bid_info = item.get("currentBidPrice") or item.get("price") or {}
        price = bid_info.get("value")
        currency = bid_info.get("currency")
        price_inr = float(price) * usd_to_inr if price else None

        url = item.get("itemWebUrl")

        try:
            details = get_item_details(item_id, token)
            end_date = details.get("itemEndDate")
            bid_count = details.get("bidCount", "N/A")
            time_left = format_time_left(end_date)
        except Exception:
            time_left = "N/A"
            bid_count = "N/A"

        print(f"- {title}")
        if price_inr:
            print(f"  Current bid: {price} {currency}  (~₹{price_inr:.2f})")
        else:
            print("  Current bid: N/A")
        print(f"  Time left: {time_left}")
        print(f"  Bids: {bid_count}")
        print(f"  Link: {url}")
        print()


if __name__ == "__main__":
    results = search_items("vintage camera", limit=10)
    print_auction_summary(results)