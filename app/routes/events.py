# app/routes/events.py

from flask import Blueprint, request, jsonify, abort
from app.models.event import Event
from app.models.event_media import EventMedia, MediaType
from app.models.user_event import UserEvent, BookingStatus
from app.models.event_option import EventOption
from app.models.user_event_option import UserEventOption
from app.services.pricing import calculate_event_price

from app import db
from datetime import datetime
from app.utils.auth import clerk_auth_required
from app.services.blob import make_read_sas, make_write_sas
import uuid
import mimetypes
import json
from typing import List

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
    """
    Serialisiert ein Event-Objekt mit optionalen Media-Informationen
    und Teilnehmer-Daten (nur PAID-Teilnehmer).
    """
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
        # Nur PAID-Buchungen zählen als Teilnehmer
        paid_events: List[UserEvent] = (
            UserEvent.query.filter_by(event_id=event.id, status=BookingStatus.PAID)
            .order_by(UserEvent.timestamp.asc())
            .all()
        )

        participant_count = len(paid_events)
        result["participant_count"] = participant_count

        if event.max_participants:
            result["available_spots"] = max(
                0, event.max_participants - participant_count
            )
        else:
            result["available_spots"] = None  # unlimited

        result["participants"] = [
            {
                "user_id": ue.user_id,
                "registered_at": ue.timestamp.isoformat(),
            }
            for ue in paid_events
        ]

        result["participants_media"] = [
            {"url": ue.avatar_url} for ue in paid_events if ue.avatar_url
        ]

    if include_media:
        result["media"] = [_serialize_media(m) for m in event.media_items]

    return result


# ---------------------- EVENT LISTINGS ----------------------


@events_bp.route("/", methods=["GET"])
@clerk_auth_required
def get_unregistered_events():
    """
    Gibt alle Events zurück, für die der User KEINE AKTIVE Buchung hat.

    Aktiv sind: PENDING, PAID
    """
    user_id = request.clerk_user_id
    include_media = request.args.get("include_media", "false").lower() == "true"
    include_participants = (
        request.args.get("include_participants", "false").lower() == "true"
    )

    active_statuses = [BookingStatus.PENDING, BookingStatus.PAID]

    subquery = (
        db.session.query(UserEvent.event_id)
        .filter(
            UserEvent.user_id == user_id,
            UserEvent.status.in_(active_statuses),
        )
    )

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
    """
    Gibt alle Events zurück, für die der User eine AKTIVE Buchung hat.

    Aktiv sind: PENDING, PAID
    """
    user_id = request.clerk_user_id
    include_media = request.args.get("include_media", "false").lower() == "true"
    include_participants = (
        request.args.get("include_participants", "false").lower() == "true"
    )

    active_statuses = [BookingStatus.PENDING, BookingStatus.PAID]

    subquery = (
        db.session.query(UserEvent.event_id)
        .filter(
            UserEvent.user_id == user_id,
            UserEvent.status.in_(active_statuses),
        )
    )

    registered_events = Event.query.filter(Event.id.in_(subquery)).all()

    return jsonify(
        [
            _serialize_event(e, include_media, include_participants)
            for e in registered_events
        ]
    )


@events_bp.route("/all", methods=["GET"])
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


# ---------------------- EVENT OPTIONS (PRICING) ----------------------


@events_bp.route("/<int:event_id>/options", methods=["GET"])
def get_event_options(event_id: int):
    """
    Liefert alle aktiven Preis-Optionen für ein Event.

    Wird von der Mobile App und dem Cockpit verwendet,
    um Travel/Ticket/Club Fee inkl. Preis anzuzeigen.
    """
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    options: List[EventOption] = (
        EventOption.query.filter_by(event_id=event.id, is_active=True)
        .order_by(EventOption.sort_order.asc(), EventOption.id.asc())
        .all()
    )

    return jsonify(
        [
            {
                "id": opt.id,
                "type": opt.type,  # "TRAVEL" | "TICKET" | "CLUB_FEE"
                "label": opt.label,
                "price_cents": opt.price_cents,
                "is_required": opt.is_required,
                "is_selectable": opt.is_selectable,
                "is_active": opt.is_active,
            }
            for opt in options
        ]
    ), 200


@events_bp.route("/<int:event_id>/options", methods=["PUT"])
def update_event_options(event_id: int):
    """
    Aktualisiert die Preis-Optionen eines Events (Travel / Ticket / Club Fee).

    Erwartet JSON:
    {
      "options": [
        {
          "type": "TRAVEL" | "TICKET" | "CLUB_FEE",
          "label": "string",
          "price_cents": 2500,
          "is_required": bool,
          "is_selectable": bool,
          "is_active": bool
        },
        ...
      ]
    }

    Logik:
    - Pro Event & Type genau EIN EventOption-Eintrag (per UniqueConstraint gesichert).
    - TRAVEL/TICKET: is_required=False, is_selectable=True.
    - CLUB_FEE: is_required=True, is_selectable=False, is_active=True.
    - Optionen, die nicht im Payload vorkommen, werden deaktiviert (is_active=False).
    """
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    data = request.get_json(force=True) or {}
    options_data = data.get("options")

    if not isinstance(options_data, list):
        return jsonify({"error": "'options' muss ein Array sein"}), 400

    allowed_types = {"TRAVEL", "TICKET", "CLUB_FEE"}
    payload_types = set()

    try:
        existing_options: List[EventOption] = EventOption.query.filter_by(
            event_id=event.id
        ).all()
        existing_by_type = {opt.type: opt for opt in existing_options}

        sort_order_defaults = {
            "TRAVEL": 10,
            "TICKET": 20,
            "CLUB_FEE": 30,
        }

        for opt_data in options_data:
            opt_type = opt_data.get("type")
            if opt_type not in allowed_types:
                return jsonify({"error": f"Ungültiger Optionstyp: {opt_type}"}), 400

            payload_types.add(opt_type)

            label = (opt_data.get("label") or "").strip() or opt_type.title()
            price_cents = opt_data.get("price_cents")

            if price_cents is None or not isinstance(price_cents, int) or price_cents < 0:
                return jsonify({"error": f"Ungültiger price_cents für {opt_type}"}), 400

            is_active = bool(opt_data.get("is_active", True))

            if opt_type == "CLUB_FEE":
                is_required = True
                is_selectable = False
                is_active = True
            else:
                is_required = False
                is_selectable = True

            existing = existing_by_type.get(opt_type)

            if existing:
                existing.label = label
                existing.price_cents = price_cents
                existing.is_required = is_required
                existing.is_selectable = is_selectable
                existing.is_active = is_active
                if existing.sort_order == 0:
                    existing.sort_order = sort_order_defaults.get(opt_type, 0)
            else:
                new_opt = EventOption(
                    event_id=event.id,
                    type=opt_type,
                    label=label,
                    price_cents=price_cents,
                    is_required=is_required,
                    is_selectable=is_selectable,
                    is_active=is_active,
                    sort_order=sort_order_defaults.get(opt_type, 0),
                )
                db.session.add(new_opt)

        # Optionen, die nicht im Payload sind, deaktivieren
        for opt in existing_options:
            if opt.type not in payload_types:
                opt.is_active = False

        db.session.commit()

        updated_options: List[EventOption] = EventOption.query.filter_by(
            event_id=event.id
        ).order_by(EventOption.sort_order.asc(), EventOption.id.asc()).all()

        return jsonify(
            [
                {
                    "id": opt.id,
                    "type": opt.type,
                    "label": opt.label,
                    "price_cents": opt.price_cents,
                    "is_required": opt.is_required,
                    "is_selectable": opt.is_selectable,
                    "is_active": opt.is_active,
                }
                for opt in updated_options
            ]
        ), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ---------------------- CREATE BOOKING WITH OPTIONS + STRIPE ----------------------


@events_bp.route("/<int:event_id>/book", methods=["POST"])
@clerk_auth_required
def book_event(event_id: int):
    """
    Erzeugt oder aktualisiert eine Buchung (UserEvent) mit Preisberechnung
    und Stripe PaymentIntent.

    State Machine:
    - Neu oder Re-Try → status = PENDING
    - PAID           → 409 (bereits gebucht und bezahlt)
    """
    if not stripe.api_key:
        return jsonify({"error": "Stripe is not configured on the server"}), 500

    user_id = request.clerk_user_id
    data = request.get_json(silent=True) or {}
    selected_option_ids = data.get("selected_option_ids", [])

    if not isinstance(selected_option_ids, list):
        abort(400, description="'selected_option_ids' muss eine Liste von IDs sein.")

    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    all_options: List[EventOption] = EventOption.query.filter_by(
        event_id=event.id, is_active=True
    ).all()

    if not all_options:
        abort(400, description="Für dieses Event sind keine Preis-Optionen konfiguriert.")

    if not any(o.is_required for o in all_options):
        abort(
            400,
            description=(
                "Event ist nicht korrekt konfiguriert: es gibt keine Pflicht-Gebühr (is_required=True)."
            ),
        )

    valid_option_ids = {opt.id for opt in all_options}
    invalid_ids = {int(o_id) for o_id in selected_option_ids} - valid_option_ids
    if invalid_ids:
        abort(
            400,
            description=f"Ungültige selected_option_ids für dieses Event: {sorted(invalid_ids)}",
        )

    # Kapazität nur anhand PAID-Buchungen
    if event.max_participants:
        paid_count = UserEvent.query.filter_by(
            event_id=event.id,
            status=BookingStatus.PAID,
        ).count()
        if paid_count >= event.max_participants:
            abort(400, description="Event ist bereits voll.")

    total_price_cents, charged_options = calculate_event_price(
        all_options=all_options,
        selected_option_ids=selected_option_ids,
    )

    if total_price_cents <= 0:
        abort(
            400,
            description="Berechneter Preis ist 0 oder negativ. Bitte Event-Optionen prüfen.",
        )

    try:
        existing = UserEvent.query.filter_by(
            user_id=user_id,
            event_id=event.id,
        ).first()

        if existing:
            # Bereits bezahlte Buchung → kein Re-Booking
            if existing.status == BookingStatus.PAID:
                abort(409, description="Dieser User hat dieses Event bereits gebucht und bezahlt.")

            # alten PaymentIntent ggf. canceln
            if existing.stripe_payment_intent_id:
                try:
                    pi = stripe.PaymentIntent.retrieve(existing.stripe_payment_intent_id)
                    if pi.status in [
                        "requires_payment_method",
                        "requires_confirmation",
                        "requires_action",
                        "processing",
                    ]:
                        stripe.PaymentIntent.cancel(existing.stripe_payment_intent_id)
                        print(f"✅ Alter PaymentIntent {existing.stripe_payment_intent_id} gecancelt")
                except stripe.error.StripeError as e:
                    print(f"⚠️ Konnte alten PaymentIntent nicht canceln: {str(e)}")

            # verknüpfte Optionen löschen
            UserEventOption.query.filter_by(user_event_id=existing.id).delete()

            existing.status = BookingStatus.PENDING
            existing.amount_paid = None
            existing.paid_at = None
            existing.currency = "chf"
            existing.stripe_payment_intent_id = None

            user_event = existing

        else:
            avatar_url = fetch_clerk_user_image(user_id)
            user_event = UserEvent(
                user_id=user_id,
                event_id=event.id,
                currency="chf",
                amount_paid=None,
                status=BookingStatus.PENDING,
                avatar_url=avatar_url,
            )
            db.session.add(user_event)
            db.session.flush()

        # neue Optionen anhängen
        for opt in charged_options:
            ueo = UserEventOption(
                user_event_id=user_event.id,
                event_option_id=opt.id,
                price_cents=opt.price_cents,
            )
            db.session.add(ueo)

        payment_intent = stripe.PaymentIntent.create(
            amount=total_price_cents,
            currency=user_event.currency,
            automatic_payment_methods={"enabled": True},
            metadata={
                "event_id": str(event.id),
                "user_id": str(user_id),
                "user_event_id": str(user_event.id),
                "selected_option_ids": json.dumps(selected_option_ids),
            },
        )

        user_event.stripe_payment_intent_id = payment_intent.id

        db.session.commit()

        return jsonify(
            {
                "user_event_id": user_event.id,
                "event_id": event.id,
                "amount_to_pay_cents": total_price_cents,
                "currency": user_event.currency,
                "stripe_payment_intent_id": payment_intent.id,
                "stripe_client_secret": payment_intent.client_secret,
                "charged_options": [
                    {
                        "id": opt.id,
                        "type": opt.type,
                        "label": opt.label,
                        "price_cents": opt.price_cents,
                    }
                    for opt in charged_options
                ],
            }
        ), 201

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


# ---------------------- CANCEL WITH STATE MACHINE ----------------------


@events_bp.route("/cancel-participation", methods=["POST"])
@clerk_auth_required
def cancel_participation():
    """
    Storniert eine Buchung für den eingeloggten User per State Machine.

    Erwartet JSON:
    {
        "event_id": 123,
        // optional: "cancellation_fee": 1000  (in Rappen)
    }

    Verhalten:
    - status == PENDING  → PaymentIntent ggf. canceln, status -> CANCELED (kein Refund)
    - status == PAID     → optional Refund (cancellation_fee), status -> REFUNDED
    - status in {CANCELED, REFUNDED, FAILED} → Fehler zurück
    """
    if not stripe.api_key:
        return jsonify({"error": "Stripe is not configured on the server"}), 500

    data = request.get_json() or {}
    event_id = data.get("event_id")
    user_id = request.clerk_user_id

    if not event_id:
        return jsonify({"error": "Missing event_id"}), 400

    user_event = UserEvent.query.filter_by(
        user_id=user_id,
        event_id=event_id,
    ).first()

    if not user_event:
        return jsonify({"error": "User was not registered for this event"}), 404

    # Optional: Storno nach Eventstart verbieten
    event = Event.query.get(event_id)
    if event and event.start_time and event.start_time <= datetime.utcnow():
        return jsonify({"error": "Event already started or in the past"}), 400

    try:
        # Fall 1: Noch nicht bezahlt → einfach canceln
        if user_event.status == BookingStatus.PENDING or user_event.amount_paid is None:
            if user_event.stripe_payment_intent_id:
                try:
                    pi = stripe.PaymentIntent.retrieve(user_event.stripe_payment_intent_id)
                    if pi.status in [
                        "requires_payment_method",
                        "requires_confirmation",
                        "requires_action",
                        "processing",
                    ]:
                        stripe.PaymentIntent.cancel(user_event.stripe_payment_intent_id)
                        print(f"✅ PaymentIntent {user_event.stripe_payment_intent_id} gecancelt")
                except stripe.error.StripeError as e:
                    print(f"⚠️ Stripe Fehler beim Canceln des PaymentIntents: {str(e)}")

            UserEventOption.query.filter_by(user_event_id=user_event.id).delete()

            user_event.status = BookingStatus.CANCELED
            user_event.amount_paid = None
            user_event.paid_at = None
            user_event.stripe_payment_intent_id = None

            db.session.commit()

            return jsonify(
                {
                    "message": "Booking canceled (no payment/refund involved)",
                    "event_id": event_id,
                    "status": user_event.status.value,
                }
            ), 200

        # Fall 2: Bereits bezahlt → optional Refund
        if user_event.status == BookingStatus.PAID and user_event.amount_paid:
            amount_paid = user_event.amount_paid
            currency = user_event.currency or "chf"

            cancellation_fee = data.get("cancellation_fee")
            if cancellation_fee is None:
                cancellation_fee = int(amount_paid * 0.1)  # z.B. 10% Fee

            if cancellation_fee < 0 or cancellation_fee > amount_paid:
                return jsonify({"error": "Invalid cancellation fee"}), 400

            refund_amount = amount_paid - cancellation_fee

            if refund_amount > 0 and user_event.stripe_payment_intent_id:
                try:
                    stripe.Refund.create(
                        payment_intent=user_event.stripe_payment_intent_id,
                        amount=refund_amount,
                    )
                except stripe.error.StripeError as e:
                    return jsonify(
                        {
                            "error": str(e),
                            "type": getattr(e, "error", {}).get("type", "stripe_error"),
                        }
                    ), 400

            UserEventOption.query.filter_by(user_event_id=user_event.id).delete()

            user_event.status = BookingStatus.REFUNDED
            # optional: paid_at stehen lassen oder anpassen
            db.session.commit()

            return jsonify(
                {
                    "message": "Booking canceled with refund",
                    "event_id": event_id,
                    "refund_amount": refund_amount,
                    "cancellation_fee": cancellation_fee,
                    "currency": currency,
                    "status": user_event.status.value,
                }
            ), 200

        # Alle anderen Status
        return jsonify(
            {
                "error": f"Cannot cancel booking in status {user_event.status.value}",
            }
        ), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


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

        if hasattr(Event, "creator_id") and "creator_id" in data:
            event.creator_id = data["creator_id"]
        if hasattr(Event, "host_id") and "host_id" in data:
            event.host_id = data["host_id"]
        if hasattr(Event, "is_online") and "is_online" in data:
            event.is_online = bool(data["is_online"])

        db.session.commit()
        return jsonify(_serialize_event(event)), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({"error": f"Invalid value: {str(e)}"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@events_bp.route("/<int:event_id>", methods=["DELETE"])
def delete_event(event_id: int):
    """Löscht ein Event"""
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    try:
        db.session.delete(event)
        db.session.commit()
        return "", 204
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


# ---------------------- LEGACY PARTICIPATION (ohne Payment) ----------------------


@events_bp.route("/<int:event_id>/participate", methods=["POST"])
@clerk_auth_required
def participate_in_event(event_id: int):
    """
    Legacy-Endpoint: registriert den User ohne Payment-Flow.
    Eigentlich durch /<event_id>/book ersetzt.
    """
    user_id = request.clerk_user_id

    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    existing = UserEvent.query.filter_by(user_id=user_id, event_id=event.id).first()
    if existing:
        return jsonify({"error": "Already registered"}), 409

    if event.max_participants:
        current_count = UserEvent.query.filter_by(
            event_id=event.id, status=BookingStatus.PAID
        ).count()
        if current_count >= event.max_participants:
            return jsonify({"error": "Event is full"}), 400

    avatar_url = fetch_clerk_user_image(user_id)

    user_event = UserEvent(
        user_id=user_id,
        event_id=event.id,
        avatar_url=avatar_url,
        status=BookingStatus.PAID,  # ohne Payment direkt als bezahlt markieren
    )
    db.session.add(user_event)

    try:
        db.session.commit()
        return jsonify(
            {
                "message": "Successfully registered (legacy)",
                "event_id": event.id,
                "user_id": user_id,
            }
        ), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@events_bp.route("/<int:event_id>/leave", methods=["POST"])
@clerk_auth_required
def leave_event(event_id: int):
    """
    Legacy-Endpoint: meldet den User von einem Event ab, indem der UserEvent-Eintrag gelöscht wird.
    In der neuen Welt wird stattdessen /cancel-participation empfohlen.
    """
    user_id = request.clerk_user_id

    user_event = UserEvent.query.filter_by(user_id=user_id, event_id=event_id).first()

    if not user_event:
        return jsonify({"error": "Not registered for this event"}), 404

    try:
        db.session.delete(user_event)
        db.session.commit()
        return jsonify({"message": "Successfully left the event (legacy)"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


# ---------------------- PAYMENT INTENT (TEST) ----------------------


@events_bp.route("/<int:event_id>/payment-intent", methods=["POST"])
@clerk_auth_required
def create_payment_intent(event_id: int):
    """Erstellt einen Stripe PaymentIntent für ein Event (TEST)"""
    if not stripe.api_key:
        return jsonify({"error": "Stripe is not configured on the server"}), 500

    data = request.get_json(force=True) or {}
    user_id = request.clerk_user_id

    if not event_id:
        return jsonify({"error": "Missing event_id"}), 400

    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404

    amount = data.get("amount", 5000)
    currency = data.get("currency", "chf")

    try:
        payment_intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            automatic_payment_methods={"enabled": True},
            metadata={
                "event_id": str(event_id),
                "user_id": str(user_id),
            },
        )

        return jsonify(
            {
                "clientSecret": payment_intent.client_secret,
                "paymentIntentId": payment_intent.id,
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

    for field in ("type", "mime", "blobName"):
        if field not in data:
            return jsonify({"error": f"missing field: {field}"}), 400

    try:
        media_type = MediaType(data["type"])
    except ValueError:
        return jsonify({"error": f"invalid media type: {data.get('type')}"}), 400

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
