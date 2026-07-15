from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import generate_password_hash, check_password_hash
from datetime import datetime, timezone
from crypto_utils import encrypt_phone, decrypt_phone

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # Phone number is stored encrypted at rest (DPDP Act / general good practice for PII)
    phone_number_encrypted = db.Column(db.String(255), nullable=True)

    # Consent tracking — required for DPDP compliance since we're processing personal data
    sms_consent_given = db.Column(db.Boolean, default=False)
    sms_consent_timestamp = db.Column(db.DateTime, nullable=True)

    # Terms & Conditions / Privacy Policy acceptance — recorded at signup so we
    # have a proper legal record (not just a frontend-only checkbox).
    terms_accepted_at = db.Column(db.DateTime, nullable=True)
    terms_version = db.Column(db.String(20), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)  # soft-delete / deactivate flag

    filters = db.relationship("NotificationFilter", backref="user", cascade="all, delete-orphan")
    subscription = db.relationship("Subscription", backref="user", uselist=False, cascade="all, delete-orphan")

    def set_password(self, plain_password):
        self.password_hash = generate_password_hash(plain_password).decode("utf-8")

    def check_password(self, plain_password):
        return check_password_hash(self.password_hash, plain_password)

    def set_phone_number(self, plain_phone):
        """Expects E.164 format, e.g. +919876543210"""
        self.phone_number_encrypted = encrypt_phone(plain_phone)

    def get_phone_number(self):
        if not self.phone_number_encrypted:
            return None
        return decrypt_phone(self.phone_number_encrypted)

    def give_sms_consent(self):
        self.sms_consent_given = True
        self.sms_consent_timestamp = datetime.now(timezone.utc)

    def withdraw_sms_consent(self):
        self.sms_consent_given = False

    def accept_terms(self, version="v1"):
        """Records that the user accepted the Terms & Conditions and Privacy
        Policy. Called at signup so acceptance is backed by a server-side
        timestamp, not just a frontend checkbox."""
        self.terms_accepted_at = datetime.now(timezone.utc)
        self.terms_version = version

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "phone_number": self.get_phone_number(),
            "sms_consent_given": self.sms_consent_given,
            "terms_accepted": self.terms_accepted_at is not None,
            "terms_accepted_at": self.terms_accepted_at.isoformat() if self.terms_accepted_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class NotificationFilter(db.Model):
    __tablename__ = "notification_filters"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    name = db.Column(db.String(100), nullable=False, default="My Filter")
    keywords = db.Column(db.String(255), nullable=True)       # comma-separated
    max_price_inr = db.Column(db.Float, nullable=True)
    min_discount_pct = db.Column(db.Float, nullable=True)
    category = db.Column(db.String(100), nullable=True)

    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Tracks the last time an SMS was sent for this filter, to support rate-limiting/cooldown
    last_notified_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "keywords": self.keywords,
            "max_price_inr": self.max_price_inr,
            "min_discount_pct": self.min_discount_pct,
            "category": self.category,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class NotifiedListing(db.Model):
    """Tracks which eBay listings have already triggered an SMS for a given filter,
    so the same auction item doesn't re-notify on every scheduler cycle."""
    __tablename__ = "notified_listings"
    __table_args__ = (db.UniqueConstraint("filter_id", "item_id", name="uq_filter_item"),)

    id = db.Column(db.Integer, primary_key=True)
    filter_id = db.Column(db.Integer, db.ForeignKey("notification_filters.id"), nullable=False)
    item_id = db.Column(db.String(100), nullable=False)
    notified_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)

    plan = db.Column(db.String(50), default="free")  # free / basic / pro, etc.
    status = db.Column(db.String(20), default="inactive")  # active / inactive / cancelled
    razorpay_subscription_id = db.Column(db.String(100), nullable=True)
    current_period_end = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def is_active(self):
        if self.status != "active":
            return False
        if self.current_period_end and self.current_period_end < datetime.now(timezone.utc):
            return False
        return True

    def to_dict(self):
        return {
            "plan": self.plan,
            "status": self.status,
            "current_period_end": self.current_period_end.isoformat() if self.current_period_end else None,
        }