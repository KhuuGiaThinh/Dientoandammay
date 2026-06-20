import os
import time

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

db = SQLAlchemy()


def configure_database(app):
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://user:pass@user-db:5432/userdb",
    )
    # Automatically convert postgres:// to postgresql+psycopg2:// for Railway/SQLAlchemy compatibility
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)


def init_db_with_retry(app, max_attempts=20, delay_seconds=2):
    last_error = None
    for _ in range(max_attempts):
        try:
            with app.app_context():
                db.session.execute(text("SELECT 1"))
                db.create_all()
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(delay_seconds)
    if last_error:
        raise last_error
