import requests
import jwt
from jwt import PyJWKClient
from flask import request, jsonify
from functools import wraps

CLERK_ISSUER = "https://popular-civet-81.clerk.accounts.dev"
CLERK_JWKS_URL = f"{CLERK_ISSUER}/.well-known/jwks.json"

jwk_client = PyJWKClient(CLERK_JWKS_URL)

def verify_clerk_token(token):
    signing_key = jwk_client.get_signing_key_from_jwt(token).key
    payload = jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        issuer=CLERK_ISSUER,
        options={'verify_audience': False}
    )
    return payload

def clerk_auth_required(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        print("➡️ Authorization Header:", auth_header)

        if not auth_header.startswith("Bearer "):
            print("⛔ Kein gültiger Bearer-Header")
            return jsonify({'error': 'Authorization header missing or invalid'}), 401

        token = auth_header.split(" ")[1]
        try:
            payload = verify_clerk_token(token)
            print("✅ Verifiziertes JWT Payload:", payload)
            request.clerk_user_id = payload["sub"]
            return func(*args, **kwargs)
        except Exception as e:
            print("❌ JWT Verifizierung fehlgeschlagen:", str(e))
            return jsonify({'error': 'Invalid or expired token', 'details': str(e)}), 401

    return decorated_function

