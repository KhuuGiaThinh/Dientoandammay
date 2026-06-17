import os
import time

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

db = SQLAlchemy()


def configure_database(app):
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://user:pass@user-db:5432/userdb",
    )
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
