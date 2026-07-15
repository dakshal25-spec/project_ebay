import re
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models import db, User, Subscription
from extensions import limiter

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# E.164 format: + followed by 10-15 digits (covers Indian numbers: +91XXXXXXXXXX)
PHONE_REGEX = re.compile(r"^\+\d{10,15}$")


# Signup: capped fairly low per IP since a real user only needs this once.
# Prevents scripted mass account creation.
@auth_bp.route("/signup", methods=["POST"])
@limiter.limit("5 per hour")
def signup():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    phone_number = (data.get("phone_number") or "").strip()
    sms_consent = data.get("sms_consent", False)

    if not email or not EMAIL_REGEX.match(email):
        return jsonify({"error": "A valid email is required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if phone_number and not PHONE_REGEX.match(phone_number):
        return jsonify({"error": "Phone number must be in E.164 format, e.g. +919876543210"}), 400
    if phone_number and not sms_consent:
        return jsonify({"error": "SMS consent is required to store a phone number"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists"}), 409

    user = User(email=email)
    user.set_password(password)
    if phone_number:
        user.set_phone_number(phone_number)
        user.give_sms_consent()

    db.session.add(user)
    db.session.flush()  # get user.id before commit

    # Every new user gets a free-tier subscription row by default
    subscription = Subscription(user_id=user.id, plan="free", status="active")
    db.session.add(subscription)

    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()}), 201


# Login: looser than signup since legitimate users log in repeatedly, but
# still tight enough to make password brute-forcing impractical.
@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401
    if not user.is_active:
        return jsonify({"error": "This account has been deactivated"}), 403

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()}), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_me():
    user = User.query.get_or_404(int(get_jwt_identity()))
    return jsonify(user.to_dict()), 200


@auth_bp.route("/me/phone", methods=["PUT"])
@jwt_required()
def update_phone():
    """Set or update phone number + SMS consent for the logged-in user."""
    user = User.query.get_or_404(int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}
    phone_number = (data.get("phone_number") or "").strip()
    sms_consent = data.get("sms_consent", False)

    if not phone_number or not PHONE_REGEX.match(phone_number):
        return jsonify({"error": "Phone number must be in E.164 format, e.g. +919876543210"}), 400
    if not sms_consent:
        return jsonify({"error": "SMS consent is required to save a phone number"}), 400

    user.set_phone_number(phone_number)
    user.give_sms_consent()
    db.session.commit()
    return jsonify(user.to_dict()), 200


@auth_bp.route("/me/sms-consent", methods=["DELETE"])
@jwt_required()
def withdraw_consent():
    """Lets a user withdraw SMS consent without deleting their whole account."""
    user = User.query.get_or_404(int(get_jwt_identity()))
    user.withdraw_sms_consent()
    db.session.commit()
    return jsonify({"message": "SMS consent withdrawn"}), 200


@auth_bp.route("/me", methods=["DELETE"])
@jwt_required()
def delete_account():
    """Required by DPDP Act — users must be able to have their data deleted."""
    user = User.query.get_or_404(int(get_jwt_identity()))
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Account and all associated data deleted"}), 200