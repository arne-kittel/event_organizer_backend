from flask import Blueprint, request, jsonify, abort
from app.models.event import Event
from app.models.event_media import EventMedia, MediaType
from app.models.user_event import UserEvent

# from app.models.user import User
from app import db
from datetime import datetime
from app.utils.auth import clerk_auth_required
from app.services.blob import make_read_sas, make_write_sas
import uuid
import mimetypes

# ⭐ Stripe-Integration
import os
import stripe
import requests

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
if not stripe.api_key:
    print(
        "⚠️ STRIPE_SECRET_KEY ist nicht gesetzt – Stripe Payments werden fehlschlagen."
    )

events_bp = Blueprint("events", __name__)


# ---------------------- HELPER FUNCTIONS ----------------------
def fetch_clerk_user_image(clerk_user_id: str) -> str | None:
    """
    Holt das Profilbild eines Clerk-Users über die Clerk Backend API.
    Wir verwenden direkt die Clerk-User-ID (z.B. 'user_363zYC2Ve5HZwsS7cwJY8AS9txk'),
    die in UserEvent.user_id gespeichert ist.
    Es wird NICHTS in der DB gespeichert – reiner Runtime-Lookup.
    """
    secret = os.getenv("CLERK_SECRET_KEY")
    if not secret:
        print("⚠️ CLERK_SECRET_KEY ist nicht gesetzt – kann Clerk-User nicht laden.")
        return None

    if not clerk_user_id:
        print("⚠️ fetch_clerk_user_image: clerk_user_id ist leer.")
        return None

    try:
        url = f"https://api.clerk.com/v1/users/{clerk_user_id}"
        print(f"🔎 Hole Clerk-User von {url}")
        resp = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {secret}",
            },
            timeout=5,
        )
        print(f"🔎 Clerk-Response {resp.status_code} für user_id={clerk_user_id}")

        if resp.status_code != 200:
            # ersten Teil der Antwort loggen, um Fehlermeldung zu sehen
            text_preview = resp.text[:300].replace("\n", " ")
            print(f"⚠️ Clerk API Fehler {resp.status_code}: {text_preview}")
            return None

        data = resp.json()
        image_url = data.get("image_url")
        print(f"✅ Clerk image_url für {clerk_user_id}: {image_url}")
        return image_url
    except Exception as e:
        print(f"⚠️ Fehler beim Laden des Clerk-Users {clerk_user_id}: {e}")
        return None


def _serialize_media(media: EventMedia) -> dict:
    """Serialisiert ein Media-Objekt mit SAS-URLs"""
    return {
        "id": media.id,
        "type": media.type.value,
        "mime": media.mime,
        "blobName": media.blob_name,
        "sasUrl": make_read_sas(media.blob_name),
        "posterSasUrl": make_read_sas(media.poster_blob) if media.poster_blob else None,
        "variants": {
            k: make_read_sas(v) for k, v in (media.variants_json or {}).items()
        },
        "sortOrder": media.sort_order,
        "width": media.width,
        "height": media.height,
        "durationSecs": media.duration_secs,
        "sizeBytes": media.size_bytes,
        "createdAt": media.created_at.isoformat(),
    }


def _serialize_event(
    event: Event, include_media: bool = False, include_participants: bool = False
) -> dict:
    """Serialisiert ein Event-Objekt mit optionalen Media-Informationen und Teilnehmer-Daten"""
    result = {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "location": event.location,
        "start_time": event.start_time.isoformat() if event.start_time else None,
        "end_time": event.end_time.isoformat() if event.end_time else None,
        "max_participants": event.max_participants,
    }

    if hasattr(event, "creator_id"):
        result["creator_id"] = event.creator_id
    if hasattr(event, "host_id"):
        result["host_id"] = event.host_id
    if hasattr(event, "is_online"):
        result["is_online"] = event.is_online

    if include_participants:
        user_events = (
            UserEvent.query.filter_by(event_id=event.id)
            .order_by(UserEvent.timestamp.asc())
            .all()
        )

        participant_count = len(user_events)
        result["participant_count"] = participant_count

        if event.max_participants:
            result["available_spots"] = max(
                0, event.max_participants - participant_count
            )
        else:
            result["available_spots"] = None  # unlimited

        # Teilnehmer-Liste (Clerk-User-ID + Zeitpunkt)
        result["participants"] = [
            {
                "user_id": ue.user_id,
                "registered_at": ue.timestamp.isoformat(),
            }
            for ue in user_events
        ]

        # 👉 hier kommen die Avatare aus user_event.avatar_url
        result["participants_media"] = [
            {"url": ue.avatar_url} for ue in user_events if ue.avatar_url
        ]

    if include_media:
        result["media"] = [_serialize_media(m) for m in event.media_items]

    return result


# ---------------------- EVENT LISTINGS ----------------------


@events_bp.route("/", methods=["GET"])
@clerk_auth_required
def get_unregistered_events():
    """Gibt alle Events zurück, für die der User nicht registriert ist"""
    user_id = request.clerk_user_id
    include_media = request.args.get("include_media", "false").lower() == "true"
    include_participants = (
        request.args.get("include_participants", "false").lower() == "true"
    )

    subquery = db.session.query(UserEvent.event_id).filter_by(user_id=user_id)
    unregistered_events = Event.query.filter(~Event.id.in_(subquery)).all()

    return jsonify(
        [
            _serialize_event(e, include_media, include_participants)
            for e in unregistered_events
        ]
    )


@events_bp.route("/my-events", methods=["GET"])
@clerk_auth_required
def get_registered_events():
    """Gibt alle Events zurück, für die der User registriert ist"""
    user_id = request.clerk_user_id
    include_media = request.args.get("include_media", "false").lower() == "true"
    include_participants = (
        request.args.get("include_participants", "false").lower() == "true"
    )

    subquery = db.session.query(UserEvent.event_id).filter_by(user_id=user_id)
    registered_events = Event.query.filter(Event.id.in_(subquery)).all()

    return jsonify(
        [
            _serialize_event(e, include_media, include_participants)
            for e in registered_events
        ]
    )


@events_bp.route("/all", methods=["GET"])
# @clerk_auth_required
def get_all_events():
    """Gibt alle Events zurück (Admin-Funktion)"""
    include_media = request.args.get("include_media", "false").lower() == "true"
    include_participants = (
        request.args.get("include_participants", "false").lower() == "true"
    )
    events = Event.query.all()

    return jsonify(
        [_serialize_event(e, include_media, include_participants) for e in events]
    )


# ---------------------- EVENT DETAIL ----------------------


@events_bp.route("/<int:event_id>", methods=["GET"])
def get_event_detail(event_id: int):
    """Gibt Details zu einem einzelnen Event inkl. Media und Teilnehmer-Info zurück"""
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    return jsonify(
        _serialize_event(event, include_media=True, include_participants=True)
    )


# ---------------------- CREATE & UPDATE EVENT ----------------------


@events_bp.route("", methods=["POST"])
@events_bp.route("/", methods=["POST"])
def create_event():
    """Erstellt ein neues Event"""
    data = request.get_json(force=True) or {}

    try:
        event = Event(
            title=data["title"],
            description=data.get("description"),
            location=data.get("location"),
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"])
            if data.get("end_time")
            else None,
            max_participants=data.get("max_participants"),
        )

        # Optionale Felder nur setzen, wenn sie im Model existieren
        if hasattr(Event, "creator_id") and "creator_id" in data:
            event.creator_id = data["creator_id"]
        if hasattr(Event, "host_id") and "host_id" in data:
            event.host_id = data["host_id"]
        if hasattr(Event, "is_online") and "is_online" in data:
            event.is_online = bool(data["is_online"])

        db.session.add(event)
        db.session.commit()

        return jsonify(_serialize_event(event)), 201
    except KeyError as e:
        db.session.rollback()
        return jsonify({"error": f"Missing required field: {str(e)}"}), 400
    except ValueError as e:
        db.session.rollback()
        return jsonify({"error": f"Invalid value: {str(e)}"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@events_bp.route("/<int:event_id>", methods=["PUT"])
def update_event(event_id: int):
    """Aktualisiert ein bestehendes Event"""
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    data = request.get_json(force=True) or {}

    try:
        # Felder aktualisieren
        if "title" in data:
            event.title = data["title"]
        if "description" in data:
            event.description = data["description"]
        if "location" in data:
            event.location = data["location"]
        if "start_time" in data:
            event.start_time = (
                datetime.fromisoformat(data["start_time"])
                if data["start_time"]
                else None
            )
        if "end_time" in data:
            event.end_time = (
                datetime.fromisoformat(data["end_time"]) if data["end_time"] else None
            )
        if "max_participants" in data:
            event.max_participants = data["max_participants"]

        # Optionale Felder
        if "creator_id" in data and hasattr(event, "creator_id"):
            event.creator_id = data["creator_id"]
        if "host_id" in data and hasattr(event, "host_id"):
            event.host_id = data["host_id"]
        if "is_online" in data and hasattr(event, "is_online"):
            event.is_online = bool(data["is_online"])

        db.session.commit()
        return jsonify(
            _serialize_event(event, include_media=True, include_participants=True)
        ), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({"error": f"Invalid value: {str(e)}"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@events_bp.route("/<int:event_id>", methods=["DELETE"])
@clerk_auth_required
def delete_event(event_id: int):
    """Löscht ein Event (Admin-Funktion)"""
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    try:
        db.session.delete(event)
        db.session.commit()
        return jsonify({"message": "Event successfully deleted"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


# ---------------------- PARTICIPATION ----------------------


@events_bp.route("/participate", methods=["POST"])
@clerk_auth_required
def participate_event():
    """User nimmt an einem Event teil"""
    data = request.get_json() or {}
    event_id = data.get("event_id")
    avatar_url = data.get("avatar_url")
    user_id = request.clerk_user_id

    # 🔐 von der App mitgeschickt nach erfolgreicher Zahlung
    stripe_payment_intent_id = data.get("payment_intent_id")
    amount_paid = data.get("amount")  # in Rappen, z.B. 5000 = 50.00 CHF
    currency = data.get("currency")

    if not event_id:
        return jsonify({"error": "event_id is required"}), 400

    event = Event.query.get(event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404

    # Optional: prüfen, ob Event voll ist etc.

    existing = UserEvent.query.filter_by(user_id=user_id, event_id=event_id).first()
    if existing:
        return jsonify({"error": "User already registered for this event"}), 400

    user_event = UserEvent(
        user_id=user_id,
        event_id=event_id,
        avatar_url=avatar_url,
        stripe_payment_intent_id=stripe_payment_intent_id,
        amount_paid=amount_paid,
        currency=currency,
    )
    
    print(user_event)

    try:
        db.session.add(user_event)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok"}), 200


@events_bp.route("/withdraw", methods=["DELETE"])
@clerk_auth_required
def withdraw_from_event():
    """Meldet einen User von einem Event ab"""
    data = request.get_json(force=True) or {}
    event_id = data.get("event_id")
    user_id = request.clerk_user_id

    if not event_id:
        return jsonify({"error": "Missing event_id"}), 400

    user_event = UserEvent.query.filter_by(user_id=user_id, event_id=event_id).first()
    if not user_event:
        return jsonify({"error": "User was not registered for this event"}), 404

    try:
        db.session.delete(user_event)
        db.session.commit()
        return jsonify(
            {"message": "Successfully unregistered from event", "event_id": event_id}
        ), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@events_bp.route("/<int:event_id>/participants", methods=["GET"])
@clerk_auth_required
def get_event_participants(event_id: int):
    """Gibt alle Teilnehmer eines Events zurück"""
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    participants = UserEvent.query.filter_by(event_id=event_id).all()

    return jsonify(
        {
            "event_id": event_id,
            "participant_count": len(participants),
            "max_participants": event.max_participants,
            "available_spots": max(0, event.max_participants - len(participants))
            if event.max_participants
            else None,
            "participants": [
                {"user_id": p.user_id, "registered_at": p.timestamp.isoformat()}
                for p in participants
            ],
        }
    )


# ---------------------- PAYMENTS / STRIPE ----------------------


@events_bp.route("/create-payment-intent", methods=["POST"])
@clerk_auth_required
def create_event_payment_intent():
    """
    Erstellt einen Stripe PaymentIntent für ein Event.

    Erwartet JSON:
    {
      "event_id": 123,
      // optional: "amount": 5000  (in Rappen)
      // optional: "currency": "chf"
    }

    Falls kein amount übergeben wird → Default: 50 CHF (5000 Rappen).
    """
    if not stripe.api_key:
        return jsonify({"error": "Stripe is not configured on the server"}), 500

    data = request.get_json(force=True) or {}
    event_id = data.get("event_id")
    user_id = request.clerk_user_id

    if not event_id:
        return jsonify({"error": "Missing event_id"}), 400

    # Sicherstellen, dass das Event existiert
    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404

    # Betrag bestimmen – Default 5000 Rappen (50 CHF)
    amount = data.get("amount", 5000)
    currency = data.get("currency", "chf")

    try:
        # Stripe PaymentIntent erstellen
        payment_intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            automatic_payment_methods={"enabled": True},
            metadata={
                "event_id": str(event_id),
                "user_id": str(user_id),
            },
        )

        # ⭐ WICHTIG: payment_intent.id mitgeben
        return jsonify(
            {
                "clientSecret": payment_intent.client_secret,
                "paymentIntentId": payment_intent.id,  # <-- neu
                "amount": amount,
                "currency": currency,
            }
        ), 200

    except stripe.error.StripeError as e:
        return jsonify(
            {
                "error": str(e),
                "type": getattr(e, "error", {}).get("type", "stripe_error"),
            }
        ), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ---------------------- MEDIA MANAGEMENT ----------------------


@events_bp.route("/<int:event_id>/media", methods=["GET"])
def list_event_media(event_id: int):
    """Gibt alle Media-Items eines Events zurück"""
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    return jsonify([_serialize_media(m) for m in event.media_items])


@events_bp.route("/<int:event_id>/media/sas-upload", methods=["POST"])
def get_media_upload_sas(event_id: int):
    """Generiert eine SAS-URL zum Upload eines Media-Files"""
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    data = request.get_json(force=True) or {}
    ext = (data.get("ext") or "").lstrip(".").lower()
    media_type = data.get("type") or "image"

    if media_type not in [t.value for t in MediaType]:
        return jsonify({"error": "invalid media type"}), 400

    content_type = data.get("contentType") or mimetypes.types_map.get(
        f".{ext}", "application/octet-stream"
    )
    now = datetime.utcnow()
    blob_name = f"events/{now:%Y/%m}/{event_id}/{uuid.uuid4()}.{ext or 'bin'}"
    upload_url = make_write_sas(blob_name, content_type=content_type)

    return jsonify(
        {"uploadUrl": upload_url, "blobName": blob_name, "contentType": content_type}
    )


@events_bp.route("/<int:event_id>/media", methods=["POST"])
def attach_media_after_upload(event_id: int):
    """Verknüpft ein hochgeladenes Media-File mit einem Event"""
    data = request.get_json(force=True) or {}

    # Pflichtfelder prüfen
    for field in ("type", "mime", "blobName"):
        if field not in data:
            return jsonify({"error": f"missing field: {field}"}), 400

    # MediaType validieren
    try:
        media_type = MediaType(data["type"])
    except ValueError:
        return jsonify({"error": f"invalid media type: {data.get('type')}"}), 400

    # Event existiert?
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    try:
        media = EventMedia(
            event_id=event_id,
            type=media_type,
            mime=data["mime"],
            blob_name=data["blobName"],
            poster_blob=data.get("posterBlob"),
            variants_json=data.get("variants"),
            width=data.get("width"),
            height=data.get("height"),
            duration_secs=data.get("durationSecs"),
            size_bytes=data.get("sizeBytes"),
            sort_order=data.get("sortOrder", 0),
        )
        db.session.add(media)
        db.session.commit()

        return jsonify(_serialize_media(media)), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@events_bp.route("/media/<int:media_id>", methods=["DELETE"])
def delete_media(media_id: int):
    """Löscht ein Media-Item"""
    media = db.session.get(EventMedia, media_id)
    if not media:
        abort(404)

    try:
        db.session.delete(media)
        db.session.commit()
        return "", 204
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@events_bp.route("/<int:event_id>/media/<int:media_id>", methods=["PUT"])
def update_media(event_id: int, media_id: int):
    """Aktualisiert ein Media-Item (z.B. sortOrder)"""
    media = db.session.get(EventMedia, media_id)
    if not media or media.event_id != event_id:
        abort(404)

    data = request.get_json(force=True) or {}

    try:
        if "sortOrder" in data:
            media.sort_order = data["sortOrder"]
        if "posterBlob" in data:
            media.poster_blob = data["posterBlob"]
        if "variants" in data:
            media.variants_json = data["variants"]

        db.session.commit()
        return jsonify(_serialize_media(media)), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400

        CANCELLATION_FEE_FIXED = 1000  # 10 CHF in Rappen (anpassbar)


# oder alternativ prozentuale Gebühr nutzen


@events_bp.route("/cancel-participation", methods=["POST"])
@clerk_auth_required
def cancel_participation_with_fee():
    """
    Storniert eine Event-Buchung und erstattet den Betrag abzüglich Storno-Gebühr.
    Erwartet JSON:
    {
        "event_id": 123
        // optional: "cancellation_fee": 1000  (in Rappen)
    }
    """
    if not stripe.api_key:
        return jsonify({"error": "Stripe is not configured on the server"}), 500

    data = request.get_json() or {}
    event_id = data.get("event_id")
    user_id = request.clerk_user_id

    if not event_id:
        return jsonify({"error": "Missing event_id"}), 400

    user_event = UserEvent.query.filter_by(user_id=user_id, event_id=event_id).first()
    if not user_event:
        return jsonify({"error": "User was not registered for this event"}), 404

    # Event laden (z.B. um zu prüfen, ob Storno noch erlaubt ist)
    event = Event.query.get(event_id)
    if event and getattr(event, "start_datetime", None):
        # Beispiel: Storno nur vor Event-Beginn erlauben
        if event.start_datetime <= datetime.utcnow():
            return jsonify({"error": "Event already started or in the past"}), 400

    # Falls keine Stripe-Daten vorhanden → einfach wie bisher abmelden
    if not user_event.stripe_payment_intent_id or not user_event.amount_paid:
        try:
            db.session.delete(user_event)
            db.session.commit()
            return jsonify(
                {"message": "Booking canceled (no payment info, no refund issued)"}
            ), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    amount_paid = user_event.amount_paid  # in Rappen
    currency = user_event.currency or "chf"

    # Storno-Gebühr (entweder aus Request oder Default)
    cancellation_fee = data.get("cancellation_fee")
    if cancellation_fee is None:
        cancellation_fee = int(amount_paid * 0.1)

    if cancellation_fee < 0 or cancellation_fee > amount_paid:
        return jsonify({"error": "Invalid cancellation fee"}), 400

    refund_amount = amount_paid - cancellation_fee

    try:
        # 💸 Teilrefund bei Stripe
        if refund_amount > 0:
            stripe.Refund.create(
                payment_intent=user_event.stripe_payment_intent_id,
                amount=refund_amount,
            )

        # Buchung aus deiner DB entfernen (oder als "canceled" markieren)
        db.session.delete(user_event)
        db.session.commit()

        return jsonify(
            {
                "message": "Booking canceled with cancellation fee",
                "event_id": event_id,
                "refund_amount": refund_amount,
                "cancellation_fee": cancellation_fee,
                "currency": currency,
            }
        ), 200

    except stripe.error.StripeError as e:
        db.session.rollback()
        return jsonify(
            {
                "error": str(e),
                "type": getattr(e, "error", {}).get("type", "stripe_error"),
            }
        ), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
