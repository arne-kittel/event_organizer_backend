import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from config import Config

from app.extensions import db
from app import models

# .env laden
load_dotenv()

# Globale Extension (wird in create_app eingebunden)
jwt = JWTManager()
oauth = OAuth()



def create_app():
    # App erstellen
    app = Flask(__name__)

    # Konfiguration laden
    app.config.from_object(Config)
    
    # Erweiterungen initialisieren
    jwt.init_app(app)
    db.init_app(app)
    oauth.init_app(app)
    CORS(app)                           # Für Frontend-Zugriff (z. B. von Next.js / Postman)

    with app.app_context():
        db.create_all()                 # Erzeugt die Tabellen in der Datenbank falls sie noch fehlen

    # OAuth Provider: Google
    oauth.register(
        name='google',
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )

    # ------ Mounting Blueprints --------- #

    # Blueprint für Events registrieren
    from app.routes.events import events_bp
    app.register_blueprint(events_bp, url_prefix="/api/events")

    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/api/auth")

    return app
