"""
Small CLI helper to fetch and print an eBay OAuth token for manual testing.
Reuses the cached get_access_token() from search_items.py instead of
duplicating the auth logic.

Usage: python get_token.py
"""
from search_items import get_access_token

if __name__ == "__main__":
    try:
        token = get_access_token()
        print("Token obtained:", token[:20] + "...")
    except Exception as e:
        print("Error obtaining token:", e)