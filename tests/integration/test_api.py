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

def test_class_student_policy_and_scores(client):
    c, _ = client
    h = auth(c)
    assert c.post('/classes', headers=h, json={"id":"FDA-01", "name":"Fundamental Data Analyst"}).status_code == 201
    assert c.post('/classes/FDA-01/students', headers=h, json={"id":"FDA-001","name":"Mahasiswa Baru"}).status_code == 201
    assert c.put('/classes/FDA-01/students/FDA-001', headers=h, json={"name":"Nama Baru"}).status_code == 200
    d = c.get('/classes/FDA-01/academic', headers=h).json()
    assert d['students'][0]['name'] == 'Nama Baru'
    policy = d['policy']
    assert c.put('/classes/FDA-01/policy', headers=h, json={"expected_revision":d['revision'],"policy":policy}).status_code == 200
    rows=[{"student_id":"FDA-001","assessment_id":"ASM-01","value":90}]
    assert c.put('/classes/FDA-01/scores', headers=h, json={"expected_revision":d['revision'],"rows":rows}).status_code == 409
    revision=c.get('/classes/FDA-01/academic', headers=h).json()['revision']
    assert c.put('/classes/FDA-01/scores', headers=h, json={"expected_revision":revision,"rows":rows}).status_code == 200
    assert c.get('/classes/FDA-01/academic',headers=h).json()['scores']['FDA-001']['ASM-01']==90
    outsider=auth(c,'outsider')
    assert c.get('/classes/FDA-01/academic',headers=outsider).status_code==403
    assert c.put('/classes/FDA-01/policy',headers=outsider,json={"expected_revision":revision,"policy":policy}).status_code==403

def test_csv_preview_and_atomic_import(client):
    c, _ = client
    h = auth(c)
    before=c.get('/classes/RPL-01/academic',headers=h).json()
    r=c.post('/classes/RPL-01/scores/preview',headers=h,json={"csv_text":"student_id,assessment_id,value\nSTD-003,ASM-02,80\nSTD-010,ASM-02,\n"}).json()
    assert r['valid'] and r['rows'][1]['value'] is None
    assert c.get('/classes/RPL-01/academic',headers=h).json()['revision']==before['revision']
    bad=c.post('/classes/RPL-01/scores/preview',headers=h,json={"csv_text":"student_id,assessment_id,value\nSTD-003,ASM-02,NaN\nSTD-003,ASM-02,80\nnot-here,ASM-01,50"}).json()
    assert not bad['valid'] and len(bad['errors'])==2
    invalid=r['rows']+[{'student_id':'STD-003','assessment_id':'ASM-03','value':999}]
    assert c.put('/classes/RPL-01/scores',headers=h,json={'expected_revision':r['expected_revision'],'rows':invalid}).status_code==422
    assert c.get('/classes/RPL-01/academic',headers=h).json()['scores']['STD-003']['ASM-02']==52
    assert c.put('/classes/RPL-01/scores',headers=h,json={'expected_revision':r['expected_revision'],'rows':r['rows']}).status_code==200
    assert c.put('/classes/RPL-01/scores',headers=h,json={'expected_revision':r['expected_revision'],'rows':r['rows']}).status_code==409

def test_followup_transitions_and_report(client):
    c, _ = client
    h=auth(c)
    iid=c.post('/classes/RPL-01/interventions',headers=h,json={'student_id':'STD-003','idempotency_key':'followup-003'}).json()['id']
    endpoint=f'/classes/RPL-01/interventions/{iid}/followup'
    assert c.post(endpoint,headers=h,json={'action':'complete','notes':'Belum disetujui'}).status_code==409
    assert c.post(f'/classes/RPL-01/interventions/{iid}/approve',headers=h).status_code==200
    assert c.post(endpoint,headers=h,json={'action':'complete','notes':'Latihan sudah dilakukan','result_score':85}).status_code==200
    assert c.post(f'/classes/RPL-01/interventions/{iid}/approve',headers=h).status_code==409
    dashboard=c.get('/classes/RPL-01/dashboard',headers=h).json()
    assert dashboard['interventions'][0]['followup']['result_score']==85
    c.put('/classes/RPL-01/students/STD-003',headers=h,json={'name':'=HYPERLINK("evil")'})
    report=c.get('/classes/RPL-01/report.csv',headers=h)
    assert report.status_code==200 and 'course_only' in report.text and "'=HYPERLINK" in report.text
    outsider=auth(c,'outsider')
    assert c.get('/classes/RPL-01/report.csv',headers=outsider).status_code==403
    assert c.get('/classes/RPL-01/audit',headers=outsider).status_code==403

def test_reject_and_roi_scenario(client):
    c, _ = client
    h=auth(c)
    iid=c.post('/classes/RPL-01/interventions',headers=h,json={'student_id':'STD-003','idempotency_key':'reject-003'}).json()['id']
    assert c.post(f'/classes/RPL-01/interventions/{iid}/followup',headers=h,json={'action':'reject','notes':'Latihan perlu disesuaikan'}).json()['status']=='rejected'
    assert c.post(f'/classes/RPL-01/interventions/{iid}/approve',headers=h).status_code==409
    body={'baseline_hours_month':50,'new_work_hours_month':12,'review_hours_month':6,'correction_hours_month':2,'value_per_hour':100000,'monthly_operating_cost':1500000,'initial_cost':12000000,'horizon_months':12}
    r=c.post('/classes/RPL-01/roi/scenario',headers=h,json=body)
    assert r.status_code==200 and r.json()['release_decision']=='HOLD'
    assert float(r.json()['metrics']['horizon_roi_pct'])==20
    assert c.post('/classes/RPL-01/roi/scenario',headers=h,json=body|{'value_per_hour':-1}).status_code==422
