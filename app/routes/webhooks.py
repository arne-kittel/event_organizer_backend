# app/routes/webhooks.py

import os
import stripe
from flask import Blueprint, request, jsonify
from app import db
from app.models.user_event import UserEvent
from app.models.event import Event  # falls du evtl. was updaten willst

webhook_bp = Blueprint("webhook_bp", __name__)

# Wichtig: Setze das Stripe-API-Key woanders global oder hier
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


@webhook_bp.route("/stripe", methods=["POST"])
def stripe_webhook():
    """
    Stripe Webhook Handler.
    Diese Route DARF NICHT hinter Auth (Clerk) hängen!
    Authentifizierung erfolgt über das Stripe-Signatur-Secret.
    """
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")

    if not STRIPE_WEBHOOK_SECRET:
        return jsonify({"error": "Missing STRIPE_WEBHOOK_SECRET"}), 500

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        # Invalid payload
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        return jsonify({"error": "Invalid signature"}), 400

    event_type = event["type"]
    data_object = event["data"]["object"]

    # Optional zum Debuggen:
    # print("🔔 Stripe Webhook Event:", event_type)

    # 1️⃣ Zahlung erfolgreich
    if event_type == "payment_intent.succeeded":
        payment_intent_id = data_object.get("id")
        metadata = data_object.get("metadata", {}) or {}
        event_id = metadata.get("event_id")
        user_id = metadata.get("user_id")

        # Hier könntest du z.B. Logging machen
        # oder sicherstellen, dass UserEvent existiert.
        # (In deinem Flow legst du das UserEvent nach erfolgreicher Zahlung an.)
        print(f"✅ payment_intent.succeeded: {payment_intent_id} for user {user_id} / event {event_id}")

    # 2️⃣ Zahlung fehlgeschlagen
    elif event_type == "payment_intent.payment_failed":
        payment_intent_id = data_object.get("id")
        metadata = data_object.get("metadata", {}) or {}
        event_id = metadata.get("event_id")
        user_id = metadata.get("user_id")

        print(f"❌ payment_intent.payment_failed: {payment_intent_id} for user {user_id} / event {event_id}")

        # Du könntest z.B. hier sicherstellen, dass keine UserEvent-Registrierung ohne erfolgreiche Zahlung hängt.

    # 3️⃣ Refund (auch Teilrefund)
    elif event_type == "charge.refunded":
        charge_id = data_object.get("id")
        payment_intent_id = data_object.get("payment_intent")
        refunded_amount = data_object.get("amount_refunded")

        print(f"💸 charge.refunded: {charge_id}, payment_intent={payment_intent_id}, refunded={refunded_amount}")

        # Optional: In deiner DB z.B. ein "canceled" Flag setzen,
        # falls du für diesen PaymentIntent noch ein UserEvent findest.

        if payment_intent_id:
            user_event = UserEvent.query.filter_by(
                stripe_payment_intent_id=payment_intent_id
            ).first()

            if user_event:
                # Falls du hier z.B. ein Statusfeld hast:
                # user_event.status = "refunded"
                # oder Logging, Auditing etc.
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()

    # 4️⃣ Chargeback / Dispute (optional, aber gut zu wissen)
    elif event_type == "charge.dispute.created":
        charge_id = data_object.get("charge")
        print(f"⚠️ Dispute created for charge {charge_id}")
        # Hier könntest du dir z.B. ein Flag setzen und manuell schauen.

    # Unhandled event
    else:
        print(f"ℹ️ Unhandled Stripe event type: {event_type}")

    return jsonify({"status": "success"}), 200
