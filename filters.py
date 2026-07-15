from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, NotificationFilter, User

filters_bp = Blueprint("filters", __name__, url_prefix="/api/filters")

MAX_FILTERS_FREE_PLAN = 3  # keep this here so plan limits are easy to find/change later


@filters_bp.route("", methods=["GET"])
@jwt_required()
def list_filters():
    user_id = int(get_jwt_identity())
    filters = NotificationFilter.query.filter_by(user_id=user_id).all()
    return jsonify([f.to_dict() for f in filters]), 200


@filters_bp.route("", methods=["POST"])
@jwt_required()
def create_filter():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)

    if not user.phone_number_encrypted or not user.sms_consent_given:
        return jsonify({"error": "Add a phone number and SMS consent before creating filters"}), 400

    existing_count = NotificationFilter.query.filter_by(user_id=user_id).count()
    plan = user.subscription.plan if user.subscription else "free"
    if plan == "free" and existing_count >= MAX_FILTERS_FREE_PLAN:
        return jsonify({
            "error": f"Free plan is limited to {MAX_FILTERS_FREE_PLAN} filters. Upgrade to add more."
        }), 403

    data = request.get_json(silent=True) or {}
    new_filter = NotificationFilter(
        user_id=user_id,
        name=data.get("name", "My Filter"),
        keywords=data.get("keywords"),
        max_price_inr=data.get("max_price_inr"),
        min_discount_pct=data.get("min_discount_pct"),
        category=data.get("category"),
        active=data.get("active", True),
    )
    db.session.add(new_filter)
    db.session.commit()
    return jsonify(new_filter.to_dict()), 201


@filters_bp.route("/<int:filter_id>", methods=["PUT"])
@jwt_required()
def update_filter(filter_id):
    user_id = int(get_jwt_identity())
    f = NotificationFilter.query.filter_by(id=filter_id, user_id=user_id).first_or_404()

    data = request.get_json(silent=True) or {}
    for field in ["name", "keywords", "max_price_inr", "min_discount_pct", "category", "active"]:
        if field in data:
            setattr(f, field, data[field])

    db.session.commit()
    return jsonify(f.to_dict()), 200


@filters_bp.route("/<int:filter_id>", methods=["DELETE"])
@jwt_required()
def delete_filter(filter_id):
    user_id = int(get_jwt_identity())
    f = NotificationFilter.query.filter_by(id=filter_id, user_id=user_id).first_or_404()
    db.session.delete(f)
    db.session.commit()
    return jsonify({"message": "Filter deleted"}), 200