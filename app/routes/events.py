from flask import Blueprint, request, jsonify
from app.models.event import Event
from app import db
from datetime import datetime
from app.utils.auth import clerk_auth_required

events_bp = Blueprint("events", __name__)

@clerk_auth_required
@events_bp.route("/", methods=["GET"])
def get_events():
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
