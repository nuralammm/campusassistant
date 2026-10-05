import json
import os
import secrets
import time
from collections import defaultdict, deque
from hashlib import sha256
from typing import Literal
from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from campus_assistant.api.db import SessionLocal, User, LoginSession, CourseClass, Membership, Student, Score, Intervention, Audit, Measurement
from campus_assistant.api.security import token_hash, verify_password
from campus_assistant.outcomes import OutcomeInput, evaluate
from campus_assistant.pilot.decision import Context, decide, Status

app = FastAPI(title="Campus Assistant", version="0.2.0")
bearer = HTTPBearer(auto_error=False)
attempts = defaultdict(lambda: deque(maxlen=10))

def get_db():
    with SessionLocal() as db:
        yield db

def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    session = db.get(LoginSession, token_hash(credentials.credentials)) if credentials else None
    if not session or session.expires <= time.time():
        raise HTTPException(401, "Sesi tidak valid atau kedaluwarsa")
    return db.get(User, session.user_id)

def allowed(db, user, cid, lock=False):
    if user.role != "lecturer" or not db.get(Membership, (user.id, cid)):
        raise HTTPException(403, "Akses kelas ditolak")
    query = select(CourseClass).where(CourseClass.id == cid)
    if lock:
        query = query.with_for_update()
    course = db.scalar(query)
    if not course:
        raise HTTPException(404, "Kelas tidak ditemukan")
    return course

def student_in(db, cid, sid):
    student = db.get(Student, sid)
    if not student or student.class_id != cid:
        raise HTTPException(404, "Mahasiswa tidak ditemukan di kelas")
    return student

def snapshot(db, course, sid):
    policy = json.loads(course.policy_json)
    scores = {s.assessment_id: s.value for s in db.scalars(select(Score).where(Score.student_id == sid))}
    data = {**policy, "assessments": [{**a, "score": scores.get(a["id"])} for a in policy["assessments"]]}
    digest = sha256(json.dumps({"data": data, "revision": course.revision, "student": sid}, sort_keys=True).encode()).hexdigest()
    return digest, evaluate(OutcomeInput.model_validate(data))

def audit(db, user, action, oid):
    db.add(Audit(id=str(uuid4()), actor=user.id, action=action, object_id=oid, created=int(time.time())))

class Login(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=200)

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.2.0", "mode": "synthetic-pilot"}

@app.post("/auth/login")
def login(body: Login, request: Request, db: Session = Depends(get_db)):
    key = request.client.host if request.client else "unknown"
    now = time.time()
    if sum(t > now - 60 for t in attempts[key]) >= 5:
        raise HTTPException(429, "Terlalu banyak percobaan; tunggu satu menit")
    attempts[key].append(now)
    user = db.get(User, body.username)
    # Equal-cost verification for unknown users to avoid trivial timing enumeration.
    dummy = "0" * 32 + ":" + "0" * 64
    verified = verify_password(body.password, user.password_hash if user else dummy)
    if not user or not verified:
        raise HTTPException(401, "Kredensial tidak valid")
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=token_hash(token), user_id=user.id, expires=int(now) + 28800))
    db.commit()
    return {"token": token, "expires_in": 28800, "username": user.id}

@app.post("/auth/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer), user=Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(credentials.credentials)))
    db.commit()
    return {"ok": True}

@app.get("/classes")
def classes(user=Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "lecturer":
        raise HTTPException(403, "Peran tidak didukung pada pilot")
    return [{"id": c.id, "name": c.name} for c in db.scalars(select(CourseClass).join(Membership).where(Membership.user_id == user.id))]

@app.get("/classes/{cid}/dashboard")
def dashboard(cid: str, user=Depends(current_user), db: Session = Depends(get_db)):
    course = allowed(db, user, cid)
    rows = []
    for student in db.scalars(select(Student).where(Student.class_id == cid).order_by(Student.id)):
        digest, outcome = snapshot(db, course, student.id)
        rows.append({"id": student.id, "name": student.name, "snapshot": digest, **outcome})
    interventions = db.scalars(select(Intervention).where(Intervention.class_id == cid)).all()
    return {"id": cid, "name": course.name, "students": rows,
            "interventions": [{"id": i.id, "student_id": i.student_id, "status": i.status,
                               "content": json.loads(i.content_json)} for i in interventions],
            "roi_status": "HOLD", "draft_method": "rule-based", "synthetic": True}

class DraftRequest(BaseModel):
    student_id: str = Field(max_length=40)
    idempotency_key: str = Field(min_length=8, max_length=80)

@app.post("/classes/{cid}/interventions", status_code=201)
def draft(cid: str, body: DraftRequest, user=Depends(current_user), db: Session = Depends(get_db)):
    course = allowed(db, user, cid, lock=True)
    student_in(db, cid, body.student_id)
    existing = db.scalar(select(Intervention).where(Intervention.class_id == cid, Intervention.key == body.idempotency_key))
    if existing:
        if existing.student_id != body.student_id:
            raise HTTPException(409, "Idempotency key digunakan untuk kasus lain")
        return {"id": existing.id, "status": existing.status}
    digest, outcome = snapshot(db, course, body.student_id)
    complete = all(c["complete"] for c in outcome["cpmks"])
    gaps = [c for c in outcome["cpmks"] if c["status"] == "gap"]
    if not gaps:
        raise HTTPException(409, "Tidak ada gap lengkap yang dapat ditindaklanjuti")
    evidence = tuple(a for c in gaps for a in c["evidence_ids"])
    result = decide(Context(True, "draft_intervention", evidence, digest, digest,
                            missing_required=not complete, kill_switch=os.getenv("AGENT_DISABLED") == "1", mode="reviewed"))
    if result.status != Status.PROCEED:
        raise HTTPException(409, {"decision": result.status.value, "reason": result.reason})
    content = {"method": "rule-based", "formula_version": outcome["formula_version"],
               "activities": [{"cpmk_id": g["id"], "evidence_ids": g["evidence_ids"],
                               "gap": g["gap"], "task": f"Latihan terarah {g['id']}: telaah kembali assessment, perbaiki jawaban, dan diskusikan dengan dosen.",
                               "duration_minutes": 30, "assessment_plan": "Dosen menilai ulang memakai rubrik CPMK yang sama."} for g in gaps]}
    item = Intervention(id=str(uuid4()), class_id=cid, student_id=body.student_id, snapshot_hash=digest,
                        content_json=json.dumps(content), status="draft", key=body.idempotency_key)
    db.add(item)
    audit(db, user, "draft_created", item.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Intervention).where(Intervention.class_id == cid, Intervention.key == body.idempotency_key))
        if not existing or existing.student_id != body.student_id:
            raise HTTPException(409, "Konflik idempotency")
        return {"id": existing.id, "status": existing.status}
    return {"id": item.id, "status": item.status}

@app.post("/classes/{cid}/interventions/{iid}/approve")
def approve(cid: str, iid: str, user=Depends(current_user), db: Session = Depends(get_db)):
    course = allowed(db, user, cid, lock=True)
    item = db.scalar(select(Intervention).where(Intervention.id == iid, Intervention.class_id == cid).with_for_update())
    if not item:
        raise HTTPException(404, "Intervensi tidak ditemukan")
    digest, outcome = snapshot(db, course, item.student_id)
    evidence = tuple(a for c in outcome["cpmks"] for a in c["evidence_ids"])
    result = decide(Context(True, "publish_intervention", evidence, item.snapshot_hash, digest,
                            missing_required=not all(c["complete"] for c in outcome["cpmks"]),
                            kill_switch=os.getenv("AGENT_DISABLED") == "1", approval_valid_for_snapshot=True, mode="reviewed"))
    if result.status != Status.PROCEED:
        raise HTTPException(409, {"decision": result.status.value, "reason": result.reason})
    # Content is immutable: approval+publication is one atomic lecturer action.
    if item.status == "draft":
        item.status = "approved"
        item.approved_by = user.id
        audit(db, user, "intervention_approved", item.id)
        db.commit()
    return {"id": item.id, "status": item.status}

class ScoreUpdate(BaseModel):
    value: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)

@app.put("/classes/{cid}/students/{sid}/scores/{aid}")
def update_score(cid: str, sid: str, aid: str, body: ScoreUpdate, user=Depends(current_user), db: Session = Depends(get_db)):
    course = allowed(db, user, cid, lock=True)
    student_in(db, cid, sid)
    if aid not in {a["id"] for a in json.loads(course.policy_json)["assessments"]}:
        raise HTTPException(404, "Assessment tidak dikenal")
    score = db.get(Score, (sid, aid))
    if score:
        score.value = body.value
    else:
        db.add(Score(student_id=sid, assessment_id=aid, value=body.value))
    course.revision += 1
    audit(db, user, "synthetic_score_updated", f"{sid}:{aid}")
    db.commit()
    return {"revision": course.revision}

class MeasurementInput(BaseModel):
    case_id: str = Field(min_length=1, max_length=80)
    arm: Literal["A", "B", "C"]
    minutes: float = Field(ge=0, le=10000, allow_inf_nan=False)
    review_minutes: float = Field(ge=0, le=10000, allow_inf_nan=False)
    correction_minutes: float = Field(ge=0, le=10000, allow_inf_nan=False)
    cost_idr: float = Field(ge=0, le=100000000, allow_inf_nan=False)

@app.post("/classes/{cid}/measurements", status_code=201)
def measure(cid: str, body: MeasurementInput, user=Depends(current_user), db: Session = Depends(get_db)):
    allowed(db, user, cid)
    item = Measurement(id=str(uuid4()), class_id=cid, **body.model_dump())
    db.add(item)
    audit(db, user, "measurement_created", item.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Kasus dan arm sudah tercatat")
    return {"id": item.id}

@app.get("/classes/{cid}/measurements")
def measurements(cid: str, user=Depends(current_user), db: Session = Depends(get_db)):
    allowed(db, user, cid)
    rows = db.scalars(select(Measurement).where(Measurement.class_id == cid)).all()
    return {"release_decision": "HOLD", "reason": "TCO, quality review, security sign-off dan paired analysis belum lengkap",
            "records": [{"case_id": r.case_id, "arm": r.arm, "total_minutes": r.minutes + r.review_minutes + r.correction_minutes,
                         "cost_idr": r.cost_idr} for r in rows]}
