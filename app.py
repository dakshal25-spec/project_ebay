from flask import Flask, jsonify, request
from flask_cors import CORS
from search_items import search_items, get_usd_to_inr_rate, get_item_details, format_time_left, get_access_token
import os
app = Flask(__name__)
CORS(app)  # allows your website (different origin) to call this API


@app.route("/api/deals")
def get_deals():
    keyword = request.args.get("keyword", "vintage camera")
    limit = int(request.args.get("limit", 10))

    results = search_items(keyword, limit=limit)
    items = results.get("itemSummaries", [])
    usd_to_inr = get_usd_to_inr_rate()
    token = get_access_token()

    deals = []
    for item in items:
        bid_info = item.get("currentBidPrice") or item.get("price") or {}
        price = bid_info.get("value")
        currency = bid_info.get("currency")
        price_inr = float(price) * usd_to_inr if price else None

        try:
            details = get_item_details(item.get("itemId"), token)
            end_date = details.get("itemEndDate")
            bid_count = details.get("bidCount", "N/A")
            time_left = format_time_left(end_date)
        except Exception:
            time_left = "N/A"
            bid_count = "N/A"

        deals.append({
            "title": item.get("title"),
            "price_usd": price,
            "currency": currency,
            "price_inr": round(price_inr, 2) if price_inr else None,
            "time_left": time_left,
            "bid_count": bid_count,
            "url": item.get("itemWebUrl"),
            "image": item.get("image", {}).get("imageUrl")
        })

    return jsonify({"count": len(deals), "deals": deals})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)