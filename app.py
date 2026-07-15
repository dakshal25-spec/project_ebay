from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from datetime import timedelta
from functools import wraps
import os
import requests as requests_lib

from apscheduler.schedulers.background import BackgroundScheduler

from config import Config
from models import db
from extensions import limiter, migrate
from auth import auth_bp
from filters import filters_bp
from matching import run_matching_cycle
from search_items import search_items, get_usd_to_inr_rate, get_item_details, format_time_left, get_access_token

Config.validate()  # fail fast if required secrets are missing

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=Config.JWT_ACCESS_TOKEN_EXPIRES_HOURS)

# Restrict CORS to configured origins (comma-separated in CORS_ORIGINS env var).
# Defaults to "*" for local dev, but set this explicitly in production.
_cors_origins = Config.CORS_ORIGINS
if _cors_origins != "*":
    _cors_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
CORS(app, origins=_cors_origins)
db.init_app(app)
migrate.init_app(app, db)
jwt = JWTManager(app)

# Rate limiting — in-memory storage is fine for a single-process dev/small deployment.
# For multi-worker/production deployments, point storage_uri at Redis instead
# (e.g. "redis://localhost:6379") so limits are shared across processes.
app.config["RATELIMIT_STORAGE_URI"] = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
limiter.init_app(app)

app.register_blueprint(auth_bp)
app.register_blueprint(filters_bp)

# Schema is now managed by Flask-Migrate instead of db.create_all().
# Run `flask db upgrade` (see README/setup notes) to apply migrations —
# this must be done once before first run, and again after any model change.

# --- Background scheduler for the SMS matching engine ---
# WERKZEUG_RUN_MAIN guards against Flask's dev-server reloader starting this twice.
if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=lambda: run_matching_cycle(app),
        trigger="interval",
        minutes=Config.MATCH_INTERVAL_MINUTES,
        id="matching_cycle",
        replace_existing=True,
    )
    scheduler.start()
    print(f"Matching engine scheduled to run every {Config.MATCH_INTERVAL_MINUTES} minutes.")


MAX_DEALS_LIMIT = 50  # upper bound to stop abuse via ?limit=99999


def admin_required(f):
    """Requires a matching X-Admin-Key header for admin-only routes."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        provided = request.headers.get("X-Admin-Key", "")
        if not Config.ADMIN_API_KEY or provided != Config.ADMIN_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


@app.route("/api/deals")
def get_deals():
    keyword = request.args.get("keyword", "vintage camera")
    try:
        limit = int(request.args.get("limit", 10))
    except ValueError:
        return jsonify({"error": "limit must be an integer"}), 400
    limit = max(1, min(limit, MAX_DEALS_LIMIT))

    try:
        results = search_items(keyword, limit=limit)
        usd_to_inr = get_usd_to_inr_rate()
        token = get_access_token()
    except requests_lib.exceptions.RequestException as e:
        logger.error("eBay API call failed for /api/deals: %s", e)
        return jsonify({"error": "Could not reach eBay right now. Please try again shortly."}), 502

    items = results.get("itemSummaries", [])

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


@app.route("/api/admin/run-matching-cycle", methods=["POST"])
@admin_required
def trigger_matching_cycle():
    """
    Manually triggers one matching cycle immediately, instead of waiting for the
    scheduled interval. Handy for testing. Requires the X-Admin-Key header to
    match ADMIN_API_KEY.
    """
    run_matching_cycle(app)
    return jsonify({"message": "Matching cycle triggered"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)