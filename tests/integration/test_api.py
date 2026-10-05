import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from campus_assistant.api.db import Base, make_engine, User, Audit, Intervention, LoginSession
from campus_assistant.api.main import app, get_db, attempts
from campus_assistant.api.seed import seed
from campus_assistant.api.security import hash_password

@pytest.fixture
def client(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        seed(db, "test-password-123")
        db.add(User(id="outsider", role="lecturer", password_hash=hash_password("test-password-123")))
        db.commit()
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    attempts.clear()
    with TestClient(app) as c:
        yield c, factory
    app.dependency_overrides.clear()
    engine.dispose()

def auth(c, name="dosen"):
    r = c.post('/auth/login', json={"username": name, "password": "test-password-123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}

def test_auth_and_class_isolation(client):
    c, _ = client
    assert c.get('/classes').status_code == 401
    outsider = auth(c, "outsider")
    assert c.get('/classes/RPL-01/dashboard', headers=outsider).status_code == 403
    assert c.post('/classes/RPL-01/interventions', headers=outsider, json={"student_id": "STD-003", "idempotency_key": "outside-001"}).status_code == 403
    h = auth(c)
    assert len(c.get('/classes/RPL-01/dashboard', headers=h).json()['students']) == 10
    assert c.post('/auth/logout', headers=h).status_code == 200
    assert c.get('/classes', headers=h).status_code == 401

def test_draft_approve_audit_and_idempotency(client):
    c, factory = client
    h = auth(c)
    body = {"student_id": "STD-003", "idempotency_key": "case-003-001"}
    r = c.post('/classes/RPL-01/interventions', headers=h, json=body)
    assert r.status_code == 201
    iid = r.json()['id']
    assert c.post('/classes/RPL-01/interventions', headers=h, json=body).json()['id'] == iid
    assert c.post(f'/classes/RPL-01/interventions/{iid}/approve', headers=h).json()['status'] == 'approved'
    c.post(f'/classes/RPL-01/interventions/{iid}/approve', headers=h)
    with factory() as db:
        assert len(db.scalars(select(Intervention)).all()) == 1
        assert len(db.scalars(select(Audit)).all()) == 2

def test_missing_stale_and_kill_switch(client, monkeypatch):
    c, _ = client
    h = auth(c)
    assert c.post('/classes/RPL-01/interventions', headers=h, json={"student_id": "STD-010", "idempotency_key": "missing-010"}).status_code == 409
    r = c.post('/classes/RPL-01/interventions', headers=h, json={"student_id": "STD-003", "idempotency_key": "stale-003"})
    iid = r.json()['id']
    assert c.put('/classes/RPL-01/students/STD-003/scores/ASM-02', headers=h, json={"value": 55}).status_code == 200
    assert c.post(f'/classes/RPL-01/interventions/{iid}/approve', headers=h).status_code == 409
    monkeypatch.setenv('AGENT_DISABLED', '1')
    assert c.post('/classes/RPL-01/interventions', headers=h, json={"student_id": "STD-004", "idempotency_key": "disabled-004"}).status_code == 409
    assert c.get('/classes/RPL-01/dashboard', headers=h).status_code == 200

def test_measurements_validation_duplicate_and_hold(client):
    c, _ = client
    h = auth(c)
    body = {"case_id": "CASE-001", "arm": "B", "minutes": 5, "review_minutes": 2, "correction_minutes": 1, "cost_idr": 0}
    assert c.post('/classes/RPL-01/measurements', headers=h, json=body).status_code == 201
    assert c.post('/classes/RPL-01/measurements', headers=h, json=body).status_code == 409
    assert c.post('/classes/RPL-01/measurements', headers=h, json=body | {"minutes": -1}).status_code == 422
    r = c.get('/classes/RPL-01/measurements', headers=h).json()
    assert r['release_decision'] == 'HOLD'
    assert r['records'][0]['total_minutes'] == 8

def test_unknown_student_and_rate_limit(client):
    c, _ = client
    h = auth(c)
    assert c.post('/classes/RPL-01/interventions', headers=h, json={"student_id": "not-here", "idempotency_key": "invalid-id"}).status_code == 404
    for _ in range(4):
        assert c.post('/auth/login', json={"username": "unknown", "password": "bad"}).status_code == 401
    assert c.post('/auth/login', json={"username": "unknown", "password": "bad"}).status_code == 429
