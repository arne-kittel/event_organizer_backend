from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from authlib.integrations.flask_client import OAuth
from app.models import User
from app import db, oauth

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# =============================
# 🚀 Registrierung
# =============================
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()

    email = data.get("email")
    password = data.get("password")
    role = "member"

    if not email or not password:
        return jsonify({"msg": "Email und Passwort erforderlich"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "User existiert bereits"}), 409

    hashed_pw = generate_password_hash(password)
    user = User(email=email, password_hash=hashed_pw, role=role)
    db.session.add(user)
    db.session.commit()

    return jsonify({"msg": "User erfolgreich registriert"}), 201

# =============================
# 🔐 Login
# =============================
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"msg": "Ungültige Zugangsdaten"}), 401

    token = create_access_token(identity=str(user.id))
    return jsonify(access_token=token), 200

# =============================
# 👤 Aktuellen Benutzer abrufen
# =============================
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User nicht gefunden"}), 404

    return jsonify({
        "id": user.id,
        "email": user.email,
    }), 200

# =============================
# 🌐 Google Login (Token von Frontend)
# =============================
@auth_bp.route("/google", methods=["POST"])
def google_login():
    token = request.json.get("token")
    if not token:
        return jsonify({"msg": "Token erforderlich"}), 400

    try:
        user_info = oauth.google.parse_id_token(token)
    except Exception as e:
        return jsonify({"msg": "Token konnte nicht verifiziert werden", "error": str(e)}), 401

    if not user_info or "sub" not in user_info:
        return jsonify({"msg": "Ungültige Benutzerinformationen"}), 401

    # Suche nach bestehendem User
    user = User.query.filter_by(provider="google", provider_id=user_info["sub"]).first()

    if not user:
        user = User(
            email=user_info["email"],
            provider="google",
            provider_id=user_info["sub"]
        )
        db.session.add(user)
        db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify(access_token=token), 200
