from app import create_app
from dotenv import load_dotenv
import os

# .env laden
load_dotenv()

# App erzeugen über Factory
app = create_app()

# Server starten (mit Port aus .env oder Fallback 5000)
if __name__ == "__main__":
    print("📦 DB-URL:", app.config["SQLALCHEMY_DATABASE_URI"])
    port = int(os.getenv("PORT", 5050))
    app.run(debug=True, host="0.0.0.0", port=port)
