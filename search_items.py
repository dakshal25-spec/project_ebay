import requests
import base64
import time
import threading
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
load_dotenv()

CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
ENV = os.getenv("EBAY_ENV")

base_url = "https://api.sandbox.ebay.com" if ENV == "sandbox" else "https://api.ebay.com"

REQUEST_TIMEOUT = 15  # seconds, applied to every outbound HTTP call in this module

# --- Token cache -------------------------------------------------------
# eBay client-credentials tokens are valid ~7200s. Without caching, every
# search/detail call re-authenticates, which is slow and burns rate limit.
_token_lock = threading.Lock()
_cached_token = None
_token_expires_at = 0  # epoch seconds


def _get_encoded_credentials():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError(
            "EBAY_CLIENT_ID and EBAY_CLIENT_SECRET must be set in .env"
        )
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    return base64.b64encode(credentials.encode()).decode()


def get_access_token(force_refresh=False):
    """Returns a cached eBay OAuth token, refreshing it only when expired
    (or when force_refresh=True). Thread-safe so the background scheduler
    and Flask request threads don't race each other."""
    global _cached_token, _token_expires_at

    with _token_lock:
        if not force_refresh and _cached_token and time.time() < _token_expires_at:
            return _cached_token

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {_get_encoded_credentials()}"
        }
        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope"
        }
        response = requests.post(
            f"{base_url}/identity/v1/oauth2/token",
            headers=headers,
            data=data,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()

        _cached_token = payload["access_token"]
        # Refresh a bit early (60s buffer) to avoid using a token that expires
        # mid-request.
        _token_expires_at = time.time() + payload.get("expires_in", 7200) - 60
        return _cached_token


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
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code == 401:
        # Token may have been invalidated server-side; force one retry with a fresh token.
        token = get_access_token(force_refresh=True)
        headers["Authorization"] = f"Bearer {token}"
        response = requests.get(
            f"{base_url}/buy/browse/v1/item_summary/search",
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
    response.raise_for_status()
    return response.json()


def get_usd_to_inr_rate():
    try:
        response = requests.get("https://open.er-api.com/v6/latest/USD", timeout=REQUEST_TIMEOUT)
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
    response = requests.get(
        f"{base_url}/buy/browse/v1/item/{item_id}",
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
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