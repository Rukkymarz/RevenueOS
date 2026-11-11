import os
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["OIDC_JWKS_URL"] = "http://localhost:9999/jwks"  # never queried in tests

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from revenueos.db import Base, get_db
from revenueos.main import app
from revenueos.security import Context, Principal, get_context, authenticate
from revenueos.models import Business, Membership

@pytest.fixture()
def harness():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as db:
        first = Business(name="First Co", industry="cleaning")
        second = Business(name="Second Co", industry="hvac")
        db.add_all([first, second]); db.flush()
        first_id, second_id = first.id, second.id
        db.add_all([
            Membership(business_id=first_id, subject="owner", email="owner@example.com", role="admin"),
            Membership(business_id=second_id, subject="other", email="other@example.com", role="admin"),
        ])
        db.commit()

    state = {"business_id": first_id, "role": "admin", "subject": "owner", "email": "owner@example.com"}
    def current_context():
        return Context(subject=state["subject"], email=state["email"], business_id=state["business_id"], role=state["role"])
    def principal():
        return Principal(subject=state["subject"], email=state["email"], email_verified=True)
    def db_session():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = db_session
    app.dependency_overrides[get_context] = current_context
    app.dependency_overrides[authenticate] = principal
    with TestClient(app) as client:
        yield client, Session, state, first_id, second_id
    app.dependency_overrides.clear()
    engine.dispose()
