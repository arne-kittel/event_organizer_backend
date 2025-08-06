from flask import Blueprint, request, jsonify
from app.models.event import Event
from app.models.user_event import UserEvent
from app import db
from datetime import datetime
from app.utils.auth import clerk_auth_required

events_bp = Blueprint("events", __name__)

@events_bp.route("/", methods=["GET"])
@clerk_auth_required
def get_unregistered_events():
    user_id = request.clerk_user_id
    
    # Subquery: alle Event-IDs, bei denen der Nutzer bereits registriert ist
    subquery = db.session.query(UserEvent.event_id).filter_by(user_id=user_id)

    # Hauptquery: alle Events, bei denen die ID NICHT in der Subquery vorkommt
    unregistered_events = Event.query.filter(~Event.id.in_(subquery)).all()

    
    event_list = [
        {
            "id":               e.id,
            "title":            e.title,
            "description":      e.description,
            "location":         e.location,
            "start_time":       e.start_time.isoformat(),
            "end_time":         e.end_time.isoformat() if e.end_time else None,
        }
        for e in unregistered_events
    ]
    return jsonify(event_list)


@events_bp.route("/my-events", methods=["GET"])
@clerk_auth_required
def get_registered_events():
    user_id = request.clerk_user_id
    
    # Subquery: alle Event-IDs, bei denen der Nutzer bereits registriert ist
    subquery = db.session.query(UserEvent.event_id).filter_by(user_id=user_id)

    # Hauptquery: alle Events, bei denen die ID NICHT in der Subquery vorkommt
    registered_events = Event.query.filter(Event.id.in_(subquery)).all()

    
    event_list = [
        {
            "id":               e.id,
            "title":            e.title,
            "description":      e.description,
            "location":         e.location,
            "start_time":       e.start_time.isoformat(),
            "end_time":         e.end_time.isoformat() if e.end_time else None,
        }
        for e in registered_events
    ]
    return jsonify(event_list)

@clerk_auth_required
@events_bp.route("/all", methods=["GET"])
def get_all_events():
    events = Event.query.all()
    event_list = [
        {
            "id":               e.id,
            "title":            e.title,
            "description":      e.description,
            "location":         e.location,
            "start_time":       e.start_time.isoformat(),
            "end_time":         e.end_time.isoformat() if e.end_time else None,
        }
        for e in events
    ]
    return jsonify(event_list)


@events_bp.route("/", methods=["POST"])
def create_event():
    data = request.get_json()

    try:
        event = Event(
            title =                  data["title"],
            description =            data.get("description"),
            creator_id =             data.get("creator_id"),
            host_id =                data.get("host_id"),
            location =               data.get("location"),
            start_time =             datetime.fromisoformat(data["start_time"]),
            end_time =               datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            max_participants =       data.get("max_participants"),
        )
        db.session.add(event)
        db.session.commit()

        return jsonify({
            "id":                   event.id,
            "title":                event.title,
            "description":          event.description,
            "location":             event.location,
            "start_time":           event.start_time.isoformat(),
            "end_time":             event.end_time.isoformat() if event.end_time else None,
            "max_participants":     event.max_participants,
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@events_bp.route("/participate", methods=["POST"])
@clerk_auth_required
def participate_in_event():
    data = request.get_json()
    event_id = data.get("event_id")
    user_id = request.clerk_user_id
    
    print("Participating request", data)
    
    if not event_id:
        return jsonify({"error": "Missing event_id"}), 400
    
    # Verify if user already registered
    existing = UserEvent.query.filter_by(user_id=user_id, event_id=event_id).first()
    if existing:
        return jsonify({"message": "User already registered"}), 200
    
    # Save registration
    participation = UserEvent(user_id=user_id, event_id=event_id)
    db.session.add(participation)
    db.session.commit()
    
    return jsonify({"message": "Successfully registered for the event."})


@events_bp.route("/withdraw", methods=["DELETE"])
@clerk_auth_required
def withdraw_from_event():
    data = request.get_json()
    event_id = data.get("event_id")
    user_id = request.clerk_user_id
    
    print("Withdrawing request", data)
    
    if not event_id:
        return jsonify({"error": "Missing event_id"}), 400
    
    # Suche den passenden Eintrag
    user_event = UserEvent.query.filter_by(user_id=user_id, event_id=event_id).first()

    if not user_event:
        return jsonify({"message": "User was not registered for this event"}), 200

    # Lösche die Registrierung
    db.session.delete(user_event)
    db.session.commit()

    return jsonify({"message": "Successfully unregistered from event"}), 200