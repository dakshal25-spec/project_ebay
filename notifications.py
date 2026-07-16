import logging
import requests
from config import Config

logger = logging.getLogger(__name__)

FAST2SMS_URL = "https://www.fast2sms.com/dev/bulkV2"

_fast2sms_available = bool(Config.FAST2SMS_API_KEY)


def _to_indian_number(phone_number: str) -> str:
    """
    Fast2SMS expects a bare 10-digit Indian number (no +91 prefix).
    Our stored numbers are in E.164 format (+919876543210), so strip the prefix.
    """
    number = phone_number.strip()
    if number.startswith("+91"):
        return number[3:]
    if number.startswith("91") and len(number) == 12:
        return number[2:]
    return number  # fall back to as-is if it's already bare 10 digits


def send_deal_alert_sms(phone_number: str, listing: dict) -> bool:
    """
    Sends an SMS alert for a matched listing via Fast2SMS.
    Returns True if sent (or would-be-sent in dry-run mode), False on failure.

    If FAST2SMS_API_KEY isn't set, this logs what WOULD be sent instead of
    failing — lets you test the matching logic before Fast2SMS is set up.
    """
    body = (
        f"Deal alert: {listing['title'][:80]} "
        f"at Rs.{listing['price_inr']} "
        f"({listing.get('bid_count', 'N/A')} bids, {listing.get('time_left', 'N/A')} left). "
        f"{listing['url']}"
    )

    if not _fast2sms_available:
        logger.warning(
            "[DRY RUN - Fast2SMS not configured] Would send SMS to %s: %s",
            phone_number, body
        )
        return True

    indian_number = _to_indian_number(phone_number)

    payload = {
        "route": Config.FAST2SMS_ROUTE,
        "message": body,
        "language": "english",
        "flash": 0,
        "numbers": indian_number,
    }
    # The DLT route requires a registered sender_id + message template;
    # the Quick ("q") route doesn't use these fields at all.
    if Config.FAST2SMS_ROUTE == "dlt" and Config.FAST2SMS_SENDER_ID:
        payload["sender_id"] = Config.FAST2SMS_SENDER_ID

    headers = {
        "authorization": Config.FAST2SMS_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
       response = requests.post(FAST2SMS_URL, data=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.error("Fast2SMS returned %s: %s", response.status_code, response.text)
        response.raise_for_status()
        result = response.json()

        if result.get("return") is True:
            logger.info("SMS sent to %s via Fast2SMS.", phone_number)
            return True
        else:
            # Fast2SMS returns HTTP 200 even on logical failures (e.g. bad number,
            # insufficient balance) — the real status is in the "return" field.
            logger.error("Fast2SMS rejected the message for %s: %s", phone_number, result)
            return False

    except requests.exceptions.RequestException as e:
        logger.error("Fast2SMS request failed for %s: %s", phone_number, e)
        return False
