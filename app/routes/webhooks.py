# app/routes/webhooks.py
import os
import json
import stripe
from flask import Blueprint, request, jsonify
from datetime import datetime

from app import db
from app.models.user_event import UserEvent, BookingStatus
from app.models.event import Event

webhook_bp = Blueprint("webhook_bp", __name__)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


@webhook_bp.route("/stripe", methods=["POST"])
def stripe_webhook():
    """
    Stripe Webhook Handler:
    Reagiert auf Zahlungsereignisse und aktualisiert den Booking-Status.
    NICHT hinter Auth hängen!
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
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": "Invalid signature"}), 400

    event_type = event["type"]
    data_object = event["data"]["object"]

    print(f"🔔 Stripe Event: {event_type}")

    # ───────────────────────────────
    # 1️⃣ PAYMENT SUCCEEDED → booking = PAID
    # ───────────────────────────────
    if event_type == "payment_intent.succeeded":
        payment_intent_id = data_object.get("id")
        metadata = data_object.get("metadata", {}) or {}
        user_event_id = metadata.get("user_event_id")

        if not user_event_id:
            print("⚠️ Kein user_event_id in metadata — breche ab.")
            return jsonify({"status": "ignored"}), 200

        user_event = UserEvent.query.get(user_event_id)
        if not user_event:
            print(f"⚠️ UserEvent {user_event_id} nicht gefunden")
            return jsonify({"status": "ignored"}), 200

        amount = data_object.get("amount_received")
        currency = data_object.get("currency", "chf")

        user_event.status = BookingStatus.PAID
        user_event.amount_paid = amount
        user_event.currency = currency
        user_event.paid_at = datetime.utcnow()

        db.session.commit()

        print(f"💚 Buchung {user_event_id} erfolgreich bezahlt ({amount} {currency})")
        return jsonify({"status": "updated"}), 200

    # ───────────────────────────────
    # 2️⃣ PAYMENT FAILED → booking = FAILED
    # ───────────────────────────────
    elif event_type == "payment_intent.payment_failed":
        payment_intent_id = data_object.get("id")
        metadata = data_object.get("metadata", {}) or {}
        user_event_id = metadata.get("user_event_id")

        user_event = UserEvent.query.get(user_event_id) if user_event_id else None
        if user_event:
            user_event.status = BookingStatus.FAILED
            db.session.commit()

        print(f"❌ Zahlung fehlgeschlagen für {user_event_id}")
        return jsonify({"status": "updated"}), 200

    # ───────────────────────────────
    # 3️⃣ REFUND → booking = REFUNDED
    # ───────────────────────────────
    elif event_type == "charge.refunded":
        payment_intent_id = data_object.get("payment_intent")
        refund_amount = data_object.get("amount_refunded")

        user_event = UserEvent.query.filter_by(
            stripe_payment_intent_id=payment_intent_id
        ).first()

        if user_event:
            user_event.status = BookingStatus.REFUNDED
            db.session.commit()
            print(
                f"💸 Refund verarbeitet für Buchung {user_event.id} ({refund_amount} CHF-Rappen)"
            )

        return jsonify({"status": "updated"}), 200

    # ───────────────────────────────
    # Other events
    # ───────────────────────────────
    else:
        print(f"ℹ️ Unhandled event: {event_type}")
        return jsonify({"status": "ignored"}), 200
