import logging
from datetime import datetime, timezone, timedelta

from models import db, NotificationFilter, NotifiedListing, User
from search_items import search_items, get_usd_to_inr_rate, get_item_details, format_time_left, get_access_token
from notifications import send_deal_alert_sms
from config import Config

logger = logging.getLogger(__name__)


def _build_listing(item, usd_to_inr, token):
    """Converts a raw eBay item summary into the normalized dict used across the app."""
    bid_info = item.get("currentBidPrice") or item.get("price") or {}
    price = bid_info.get("value")
    price_inr = round(float(price) * usd_to_inr, 2) if price else None

    try:
        details = get_item_details(item.get("itemId"), token)
        end_date = details.get("itemEndDate")
        bid_count = details.get("bidCount", "N/A")
        time_left = format_time_left(end_date)
    except Exception:
        time_left = "N/A"
        bid_count = "N/A"

    # eBay Browse API includes a "categories" list on item summaries when available
    categories = [c.get("categoryName", "") for c in item.get("categories", [])]

    # Some listings include a marketingPrice block with a discountPercentage —
    # this is only present for items eBay flags as on-sale; auctions often lack it.
    marketing_price = item.get("marketingPrice") or {}
    discount_pct = marketing_price.get("discountPercentage")

    return {
        "item_id": item.get("itemId"),
        "title": item.get("title", ""),
        "price_inr": price_inr,
        "time_left": time_left,
        "bid_count": bid_count,
        "url": item.get("itemWebUrl"),
        "categories": categories,
        "discount_pct": float(discount_pct) if discount_pct else None,
    }


def _matches_filter(listing, f: NotificationFilter):
    """Checks a normalized listing dict against a saved filter's criteria."""
    if f.keywords:
        keywords = [k.strip().lower() for k in f.keywords.split(",") if k.strip()]
        title_lower = listing["title"].lower()
        if keywords and not any(k in title_lower for k in keywords):
            return False

    if f.max_price_inr is not None:
        if listing["price_inr"] is None or listing["price_inr"] > f.max_price_inr:
            return False

    if f.min_discount_pct is not None:
        # If eBay didn't supply a discount figure for this listing, we can't verify
        # the criterion, so we conservatively skip it rather than falsely matching.
        if listing["discount_pct"] is None or listing["discount_pct"] < f.min_discount_pct:
            return False

    if f.category:
        cat_lower = f.category.strip().lower()
        if not any(cat_lower in c.lower() for c in listing["categories"]):
            return False

    return True


def _already_notified(filter_id, item_id):
    return NotifiedListing.query.filter_by(filter_id=filter_id, item_id=item_id).first() is not None


def _within_cooldown(f: NotificationFilter):
    if not f.last_notified_at:
        return False
    elapsed = datetime.now(timezone.utc) - f.last_notified_at.replace(tzinfo=timezone.utc)
    return elapsed < timedelta(minutes=Config.SMS_COOLDOWN_MINUTES)


def run_matching_cycle(app):
    """
    Runs one full pass: for every active filter belonging to a user with SMS
    consent and a phone number, searches eBay and sends alerts for new matches.
    Meant to be called on a schedule (see scheduler.py).
    """
    with app.app_context():
        active_filters = (
            NotificationFilter.query
            .filter_by(active=True)
            .join(User)
            .filter(User.sms_consent_given.is_(True))
            .filter(User.phone_number_encrypted.isnot(None))
            .filter(User.is_active.is_(True))
            .all()
        )

        if not active_filters:
            logger.info("Matching cycle: no active filters to check.")
            return

        logger.info("Matching cycle: checking %d active filter(s).", len(active_filters))

        # Cache the USD->INR rate and eBay token once per cycle rather than per filter
        usd_to_inr = get_usd_to_inr_rate()
        token = get_access_token()

        for f in active_filters:
            if _within_cooldown(f):
                logger.info("Filter %d skipped: still within cooldown window.", f.id)
                continue

            search_term = f.keywords.split(",")[0].strip() if f.keywords else "deals"
            try:
                results = search_items(search_term, limit=10)
            except Exception as e:
                logger.error("Filter %d: eBay search failed: %s", f.id, e)
                continue

            items = results.get("itemSummaries", [])
            sent_any = False

            for item in items:
                listing = _build_listing(item, usd_to_inr, token)
                if not listing["item_id"]:
                    continue
                if _already_notified(f.id, listing["item_id"]):
                    continue
                if not _matches_filter(listing, f):
                    continue

                user = f.user
                phone = user.get_phone_number()
                success = send_deal_alert_sms(phone, listing)

                if success:
                    db.session.add(NotifiedListing(filter_id=f.id, item_id=listing["item_id"]))
                    f.last_notified_at = datetime.now(timezone.utc)
                    sent_any = True
                    db.session.commit()
                    break  # respect cooldown: at most one SMS per filter per cycle

            if not sent_any:
                logger.info("Filter %d: no new matches this cycle.", f.id)