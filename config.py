import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # --- Database ---
    # Defaults to a local SQLite file for dev; set DATABASE_URL in .env for Postgres in production
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///auction_deal_finder.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Auth ---
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")  # must be set in .env, no fallback for security
    JWT_ACCESS_TOKEN_EXPIRES_HOURS = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_HOURS", "24"))

    # --- Phone number encryption ---
    # Generate once with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    PHONE_ENCRYPTION_KEY = os.getenv("PHONE_ENCRYPTION_KEY")

    # --- Twilio (optional — only used if FAST2SMS_API_KEY isn't set) ---
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

    # --- Fast2SMS ---
    FAST2SMS_API_KEY = os.getenv("FAST2SMS_API_KEY")
    # "q" = Quick SMS route, works without DLT registration (testing/personal use only).
    # Switch to "dlt" once you've completed DLT registration for production use.
    FAST2SMS_ROUTE = os.getenv("FAST2SMS_ROUTE", "q")
    # Only required for the "dlt" route — your registered DLT template ID
    FAST2SMS_SENDER_ID = os.getenv("FAST2SMS_SENDER_ID")

    # --- Matching engine / scheduler ---
    MATCH_INTERVAL_MINUTES = int(os.getenv("MATCH_INTERVAL_MINUTES", "15"))
    SMS_COOLDOWN_MINUTES = int(os.getenv("SMS_COOLDOWN_MINUTES", "10"))

    # --- eBay (already in your .env from search_items.py) ---
    EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
    EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
    EBAY_ENV = os.getenv("EBAY_ENV")

    # --- Admin ---
    # Required to call admin-only routes (e.g. POST /api/admin/run-matching-cycle).
    # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

    # --- CORS ---
    # Comma-separated list of allowed origins, e.g. "https://myapp.com,https://www.myapp.com"
    # Defaults to "*" for local dev convenience, but you should set this explicitly in production.
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

    @staticmethod
    def validate():
        """Fail loudly at startup rather than silently later if required secrets are missing."""
        required = [
            "JWT_SECRET_KEY",
            "PHONE_ENCRYPTION_KEY",
            "EBAY_CLIENT_ID",
            "EBAY_CLIENT_SECRET",
            "ADMIN_API_KEY",
        ]
        missing = [key for key in required if not os.getenv(key)]
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                f"Check your .env file."
            )