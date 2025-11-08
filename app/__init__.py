import os
from flask import Flask
from dotenv import load_dotenv
from config import Config

from flask_migrate import Migrate

from app.extensions import db, migrate, jwt, oauth
from flask_cors import CORS

# .env laden
load_dotenv()

def create_app(config_class=Config) -> Flask:
    # App erstellen
    app = Flask(__name__)

    # Konfiguration laden
    app.config.from_object(config_class)
    
    # Erweiterungen initialisieren
    CORS(app)                           # CORS aktiviieren für Frontend-Zugriff (z.B. von Next.js / Postman und Mobile App)
    db.init_app(app)                    # SQLAlchemy binden/initialisieren
    migrate.init_app(app, db)            # Migrate binden/initialisieren
    jwt.init_app(app)
    oauth.init_app(app)

    # OAuth Provider: Google
    oauth.register(
        name='google',
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )

    # Modelle laden, damit Alembic alle Tabelle sieht und die Migrationen erstellt
    # Wichtig: Diese Import muss im App-Kontext erfolgen, sonst funktioniert die Migration nicht.
    with app.app_context():
        from app import models

    # ------ Mounting Blueprints --------- #

    # Blueprint für Events registrieren
    from app.routes.events import events_bp
    app.register_blueprint(events_bp, url_prefix="/api/events")

    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/api/auth")

    return app
