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
        query = query.with_for_update().execution_options(populate_existing=True)
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
    return {"token": token, "expires_in": 28800, "username": user.id, "role": user.role}

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
    return {"id": cid, "name": course.name, "cpmk_ids": [c["id"] for c in json.loads(course.policy_json)["cpmks"]], "students": rows,
            "interventions": [{"id": i.id, "student_id": i.student_id, "status": i.status,
                               "submission": db.get(StudentSubmission,i.id).notes if db.get(StudentSubmission,i.id) else None, "followup": json.loads(i.followup_json), "content": json.loads(i.content_json)} for i in interventions],
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
    if item.status not in {"draft", "approved"}:
        raise HTTPException(409, "Status intervensi tidak dapat disetujui")
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

# Academic administration: all operations are scoped to server membership.
import csv
import io
from decimal import Decimal, InvalidOperation
from fastapi.responses import Response

class ClassCreate(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    name: str = Field(min_length=3, max_length=120)

@app.post("/classes", status_code=201)
def create_class(body: ClassCreate, user=Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "lecturer":
        raise HTTPException(403, "Hanya dosen dapat membuat kelas")
    from campus_assistant.api.seed import POLICY
    if db.get(CourseClass, body.id):
        raise HTTPException(409, "ID kelas sudah digunakan")
    db.add(CourseClass(id=body.id, name=body.name, revision=1, policy_json=json.dumps(POLICY)))
    db.flush()
    db.add(Membership(user_id=user.id, class_id=body.id))
    audit(db, user, "class_created", body.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "ID kelas sudah digunakan")
    return {"id": body.id}

class StudentInput(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    name: str = Field(min_length=2, max_length=120)

@app.post("/classes/{cid}/students", status_code=201)
def add_student(cid: str, body: StudentInput, user=Depends(current_user), db: Session = Depends(get_db)):
    course = allowed(db, user, cid, lock=True)
    if db.get(Student, body.id):
        raise HTTPException(409, "ID mahasiswa sudah digunakan")
    db.add(Student(id=body.id, name=body.name, class_id=cid))
    course.revision += 1
    audit(db, user, "student_created", body.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "ID mahasiswa sudah digunakan")
    return {"id": body.id}

class StudentRename(BaseModel):
    name: str = Field(min_length=2, max_length=120)

@app.put("/classes/{cid}/students/{sid}")
def rename_student(cid: str, sid: str, body: StudentRename, user=Depends(current_user), db: Session = Depends(get_db)):
    allowed(db, user, cid, lock=True)
    student = student_in(db, cid, sid)
    student.name = body.name
    audit(db, user, "student_renamed", sid)
    db.commit()
    return {"id": sid}

@app.get("/classes/{cid}/academic")
def academic(cid: str, user=Depends(current_user), db: Session = Depends(get_db)):
    course = allowed(db, user, cid)
    students = db.scalars(select(Student).where(Student.class_id == cid).order_by(Student.id)).all()
    scores = db.scalars(select(Score).join(Student).where(Student.class_id == cid)).all()
    return {"id": cid, "name": course.name, "revision": course.revision, "policy": json.loads(course.policy_json),
            "students": [{"id": s.id, "name": s.name} for s in students],
            "scores": {s.id: {v.assessment_id: v.value for v in scores if v.student_id == s.id} for s in students}}

class PolicyUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    policy: OutcomeInput

@app.put("/classes/{cid}/policy")
def update_policy(cid: str, body: PolicyUpdate, user=Depends(current_user), db: Session = Depends(get_db)):
    course = allowed(db, user, cid, lock=True)
    if body.expected_revision != course.revision:
        raise HTTPException(409, "Data berubah; muat ulang sebelum menyimpan")
    # Policy never stores a student's score. Preserve existing assessment IDs
    # once scores exist so editing cannot silently orphan historical evidence.
    new_ids = {a.id for a in body.policy.assessments}
    used_ids = set(db.scalars(select(Score.assessment_id).join(Student).where(Student.class_id == cid)).all())
    if used_ids - new_ids:
        raise HTTPException(409, "Assessment dengan data nilai tidak boleh dihapus dari pemetaan")
    policy = body.policy.model_dump(mode="json")
    for a in policy["assessments"]:
        a.pop("score", None)
    course.policy_json = json.dumps(policy)
    course.revision += 1
    audit(db, user, "policy_updated", cid)
    db.commit()
    return {"revision": course.revision}

class ScoreBatch(BaseModel):
    expected_revision: int = Field(ge=1)
    rows: list[dict] = Field(min_length=1, max_length=2000)

class ScoreRow(BaseModel):
    student_id: str = Field(max_length=40)
    assessment_id: str = Field(max_length=40)
    value: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)


def validate_rows(db, course, rows):
    from pydantic import ValidationError
    students = set(db.scalars(select(Student.id).where(Student.class_id == course.id)).all())
    assessments = {a["id"] for a in json.loads(course.policy_json)["assessments"]}
    errors, valid, seen = [], [], set()
    for n, row in enumerate(rows, 1):
        try:
            parsed = ScoreRow.model_validate(row)
            key = (parsed.student_id, parsed.assessment_id)
            if parsed.student_id not in students or parsed.assessment_id not in assessments:
                raise ValueError("Mahasiswa/assessment tidak terdaftar dalam kelas")
            if key in seen:
                raise ValueError("Duplikasi mahasiswa dan assessment")
            seen.add(key)
            valid.append(parsed)
        except (ValidationError, ValueError) as exc:
            errors.append({"row": n, "message": "Nilai harus kosong atau 0–100; periksa ID dan duplikasi" if isinstance(exc, ValidationError) else str(exc)})
    return valid, errors

@app.put("/classes/{cid}/scores")
def batch_scores(cid: str, body: ScoreBatch, user=Depends(current_user), db: Session = Depends(get_db)):
    course = allowed(db, user, cid, lock=True)
    if course.revision != body.expected_revision:
        raise HTTPException(409, "Data berubah; preview/muat ulang diperlukan")
    rows, errors = validate_rows(db, course, body.rows)
    if errors:
        raise HTTPException(422, errors)
    for row in rows:
        score = db.get(Score, (row.student_id, row.assessment_id))
        if score:
            score.value = row.value
        else:
            db.add(Score(student_id=row.student_id, assessment_id=row.assessment_id, value=row.value))
    course.revision += 1
    audit(db, user, "scores_batch_updated", cid)
    db.commit()
    return {"saved": len(rows), "revision": course.revision}

class CSVPreview(BaseModel):
    csv_text: str = Field(min_length=1, max_length=200000)

@app.post("/classes/{cid}/scores/preview")
def preview_csv(cid: str, body: CSVPreview, user=Depends(current_user), db: Session = Depends(get_db)):
    course = allowed(db, user, cid)
    reader = csv.DictReader(io.StringIO(body.csv_text.lstrip('\ufeff')))
    if reader.fieldnames != ["student_id", "assessment_id", "value"]:
        raise HTTPException(422, "Header CSV: student_id,assessment_id,value")
    rows = []
    for n, row in enumerate(reader):
        if n >= 2000:
            raise HTTPException(422, "Maksimal 2000 baris per impor")
        raw = row.get("value")
        rows.append({"student_id": row.get("student_id"), "assessment_id": row.get("assessment_id"),
                     "value": None if raw is not None and not raw.strip() else raw})
    parsed, errors = validate_rows(db, course, rows)
    if not rows:
        errors.append({"row": 0, "message": "CSV tidak berisi data"})
    return {"expected_revision": course.revision, "valid": not errors,
            "rows": [r.model_dump() for r in parsed], "errors": errors}

class FollowupInput(BaseModel):
    action: Literal["reject", "complete"]
    notes: str = Field(min_length=3, max_length=2000)
    result_score: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)

@app.post("/classes/{cid}/interventions/{iid}/followup")
def followup(cid: str, iid: str, body: FollowupInput, user=Depends(current_user), db: Session = Depends(get_db)):
    allowed(db, user, cid, lock=True)
    item = db.scalar(select(Intervention).where(Intervention.id == iid, Intervention.class_id == cid).with_for_update())
    if not item:
        raise HTTPException(404, "Intervensi tidak ditemukan")
    if (body.action == "reject" and item.status != "draft") or (body.action == "complete" and item.status != "approved"):
        raise HTTPException(409, "Transisi status tidak diizinkan")
    item.status = "rejected" if body.action == "reject" else "completed"
    item.followup_json = json.dumps({**body.model_dump(), "recorded_by": user.id, "recorded_at": int(time.time())})
    audit(db, user, "intervention_" + item.status, iid)
    db.commit()
    return {"status": item.status}

@app.get("/classes/{cid}/audit")
def class_audit(cid: str, user=Depends(current_user), db: Session = Depends(get_db)):
    allowed(db, user, cid)
    # Audit ownership follows actor, without exposing other users' records.
    student_ids = set(db.scalars(select(Student.id).where(Student.class_id == cid)).all())
    intervention_ids = set(db.scalars(select(Intervention.id).where(Intervention.class_id == cid)).all())
    measurement_ids = set(db.scalars(select(Measurement.id).where(Measurement.class_id == cid)).all())
    objects = {cid} | student_ids | intervention_ids | measurement_ids
    records = db.scalars(select(Audit).where(Audit.actor == user.id).order_by(Audit.created.desc())).all()
    return [{"action": r.action, "object_id": r.object_id, "created": r.created} for r in records
            if r.object_id in objects or r.object_id.split(':')[0] in student_ids][:100]

@app.get("/classes/{cid}/report.csv")
def report_csv(cid: str, user=Depends(current_user), db: Session = Depends(get_db)):
    course = allowed(db, user, cid)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["student_id", "name", "scope", "outcome", "score", "target", "status"])
    def safe(value):
        value = str(value)
        return "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
    for student in db.scalars(select(Student).where(Student.class_id == cid)):
        _, outcome = snapshot(db, course, student.id)
        for c in outcome['cpmks'] + outcome['cpls']:
            writer.writerow([safe(student.id), safe(student.name), "course_only", safe(c['id']),
                             c['score'] if c['score'] is not None else '', c['target'], c['status']])
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="campus-outcomes.csv"'})

class ROIScenario(BaseModel):
    baseline_hours_month: Decimal = Field(ge=0, le=100000)
    new_work_hours_month: Decimal = Field(ge=0, le=100000)
    review_hours_month: Decimal = Field(ge=0, le=100000)
    correction_hours_month: Decimal = Field(ge=0, le=100000)
    value_per_hour: Decimal = Field(ge=0, le=100000000)
    monthly_operating_cost: Decimal = Field(ge=0, le=100000000000)
    initial_cost: Decimal = Field(ge=0, le=100000000000)
    horizon_months: int = Field(ge=1, le=120)

@app.post("/classes/{cid}/roi/scenario")
def roi_scenario(cid: str, body: ROIScenario, user=Depends(current_user), db: Session = Depends(get_db)):
    allowed(db, user, cid)
    from campus_assistant.pilot.roi import ROIInput, calculate
    return {"scenario_only": True, "release_decision": "HOLD", "metrics": calculate(ROIInput(**body.model_dump()))}

from campus_assistant.api.db import StudentAccount, StudentSubmission, AIBudget, AIRun
from campus_assistant.api.security import hash_password

@app.get('/auth/me')
def me(user=Depends(current_user)):
    return {'username':user.id,'role':user.role}

class AccountCreate(BaseModel):
    username: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    password: str = Field(min_length=12,max_length=200)
    role: Literal['student','prodi']
    student_id: str | None = Field(default=None,max_length=40)

@app.post('/classes/{cid}/accounts',status_code=201)
def provision_account(cid: str,body: AccountCreate,user=Depends(current_user),db: Session=Depends(get_db)):
    allowed(db,user,cid,lock=True)
    if db.get(User,body.username):
        raise HTTPException(409,'Username sudah digunakan; akun tidak ditimpa')
    if body.role=='student':
        student_in(db,cid,body.student_id)
        if db.scalar(select(StudentAccount).where(StudentAccount.student_id==body.student_id)):
            raise HTTPException(409,'Mahasiswa sudah memiliki akun')
    db.add(User(id=body.username,role=body.role,password_hash=hash_password(body.password)))
    db.flush()
    if body.role=='student':
        db.add(StudentAccount(user_id=body.username,student_id=body.student_id))
    else:
        db.add(Membership(user_id=body.username,class_id=cid))
    audit(db,user,'portal_account_created',cid)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'Identitas akun sudah digunakan')
    return {'username':body.username,'role':body.role}

@app.get('/portal/student')
def student_portal(user=Depends(current_user),db: Session=Depends(get_db)):
    if user.role!='student':
        raise HTTPException(403,'Portal ini khusus mahasiswa')
    account=db.get(StudentAccount,user.id)
    if not account:
        raise HTTPException(403,'Akun belum terhubung ke mahasiswa')
    student=db.get(Student,account.student_id)
    course=db.get(CourseClass,student.class_id)
    _,outcome=snapshot(db,course,student.id)
    plans=db.scalars(select(Intervention).where(Intervention.student_id==student.id,Intervention.status.in_(['approved','completed']))).all()
    return {'student':{'id':student.id,'name':student.name},'class':{'id':course.id,'name':course.name},
            'outcome':outcome,'interventions':[{'id':i.id,'status':i.status,'content':json.loads(i.content_json),
                'followup':json.loads(i.followup_json),'submission':db.get(StudentSubmission,i.id).notes if db.get(StudentSubmission,i.id) else None} for i in plans]}

class SubmissionInput(BaseModel):
    notes: str = Field(min_length=5,max_length=2000)

@app.post('/portal/student/interventions/{iid}/submit',status_code=201)
def student_submit(iid: str,body: SubmissionInput,user=Depends(current_user),db: Session=Depends(get_db)):
    if user.role!='student':
        raise HTTPException(403,'Portal ini khusus mahasiswa')
    account=db.get(StudentAccount,user.id)
    item=db.get(Intervention,iid)
    if not account or not item or item.student_id!=account.student_id or item.status!='approved':
        raise HTTPException(404,'Rencana aktif tidak ditemukan')
    if db.get(StudentSubmission,iid):
        raise HTTPException(409,'Laporan pelaksanaan sudah dikirim')
    db.add(StudentSubmission(intervention_id=iid,student_id=account.student_id,notes=body.notes,created=int(time.time())))
    audit(db,user,'student_submission',iid)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'Laporan pelaksanaan sudah dikirim')
    return {'status':'submitted','message':'Dosen akan meninjau; capaian dan nilai tidak diubah'}

@app.get('/portal/prodi')
def prodi_portal(user=Depends(current_user),db: Session=Depends(get_db)):
    if user.role!='prodi':
        raise HTTPException(403,'Portal ini khusus prodi')
    courses=db.scalars(select(CourseClass).join(Membership).where(Membership.user_id==user.id)).all()
    results=[]
    for course in courses:
        students=db.scalars(select(Student).where(Student.class_id==course.id)).all()
        outcomes=[snapshot(db,course,s.id)[1] for s in students]
        # Suppress outcome distributions for very small cohorts; no PII returned.
        if len(students)<5:
            results.append({'id':course.id,'name':course.name,'students':len(students),'suppressed':True,'cpls':[]})
            continue
        cpls=[]
        for target in json.loads(course.policy_json)['cpl_targets']:
            rows=[next(c for c in o['cpls'] if c['id']==target) for o in outcomes]
            scores=[r['score'] for r in rows if r['score'] is not None]
            cpls.append({'id':target,'mean':round(sum(scores)/len(scores),2) if scores else None,
                         'complete':len(scores),'total':len(rows),'achieved':sum(r['status']=='achieved' for r in rows),
                         'gap':sum(r['status']=='gap' for r in rows),'incomplete':sum(r['status']=='incomplete' for r in rows)})
        results.append({'id':course.id,'name':course.name,'students':len(students),'suppressed':False,'cpls':cpls})
    return {'scope':'course_only','classes':results,'release_decision':'HOLD'}

@app.get('/classes/{cid}/ai')
def ai_status(cid: str,user=Depends(current_user),db: Session=Depends(get_db)):
    allowed(db,user,cid)
    from campus_assistant.providers.llm import Settings,ProviderError
    try:
        settings=Settings.load()
        config={'configured':True,'provider':settings.provider,'model':settings.model,'max_run_idr':settings.max_run_idr,'monthly_idr':settings.monthly_idr}
    except ProviderError:
        config={'configured':False,'provider':os.getenv('AI_PROVIDER','disabled'),'model':'','max_run_idr':0,'monthly_idr':0}
    runs=db.scalars(select(AIRun).where(AIRun.class_id==cid).order_by(AIRun.created.desc()).limit(30)).all()
    return {**config,'disabled':os.getenv('AGENT_DISABLED')=='1','runs':[{'id':r.id,'student_id':r.student_id,'status':r.status,'provider':r.provider,'model':r.model,'cost_idr':r.cost_idr,'latency_ms':r.latency_ms,'input_tokens':r.input_tokens,'output_tokens':r.output_tokens,'intervention_id':r.intervention_id} for r in runs]}

@app.post('/classes/{cid}/interventions/ai',status_code=201)
def ai_draft(cid: str,body: DraftRequest,user=Depends(current_user),db: Session=Depends(get_db)):
    from campus_assistant.providers.llm import Settings,ProviderError,messages_for,generate
    from datetime import datetime,timezone
    course=allowed(db,user,cid,lock=True)
    student_in(db,cid,body.student_id)
    existing=db.scalar(select(AIRun).where(AIRun.class_id==cid,AIRun.key==body.idempotency_key))
    if existing:
        if existing.student_id!=body.student_id:
            raise HTTPException(409,'Idempotency key digunakan untuk kasus lain')
        return {'run_id':existing.id,'status':existing.status,'intervention_id':existing.intervention_id}
    try:
        settings=Settings.load()
    except ProviderError:
        raise HTTPException(503,'Provider belum dikonfigurasi atau tarif/budget tidak valid')
    digest,outcome=snapshot(db,course,body.student_id)
    gaps=[c for c in outcome['cpmks'] if c['status']=='gap']
    if not gaps:
        raise HTTPException(409,'Tidak ada learning gap')
    check=decide(Context(True,'draft_intervention',tuple(e for c in gaps for e in c['evidence_ids']),digest,digest,
                         missing_required=not all(c['complete'] for c in outcome['cpmks']),kill_switch=os.getenv('AGENT_DISABLED')=='1'))
    if check.status!=Status.PROCEED:
        raise HTTPException(409,{'decision':check.status.value,'reason':check.reason})
    try:
        messages=messages_for(gaps)
    except ProviderError:
        raise HTTPException(422,'Konteks terlalu besar')
    # Reserve a conservative bound including schema/framing before external call.
    from campus_assistant.providers.llm import Recommendation
    input_bound=sum(len(m['content'].encode()) for m in messages)+len(json.dumps(Recommendation.model_json_schema()).encode())+1024
    reserve=settings.cost(input_bound,settings.max_output)
    period=datetime.now(timezone.utc).strftime('%Y-%m')
    budget=db.get(AIBudget,(cid,period))
    if not budget:
        budget=AIBudget(class_id=cid,period=period,committed_idr=0)
        db.add(budget);db.flush()
    count=db.scalar(select(__import__('sqlalchemy').func.count()).select_from(AIRun).where(AIRun.class_id==cid,AIRun.created>=int(datetime.now(timezone.utc).replace(day=1,hour=0,minute=0,second=0,microsecond=0).timestamp())))
    if reserve>settings.max_run_idr or budget.committed_idr+reserve>settings.monthly_idr or count>=300:
        raise HTTPException(409,'Budget atau batas 300 run bulanan tercapai')
    budget.committed_idr+=reserve
    run=AIRun(id=str(uuid4()),class_id=cid,student_id=body.student_id,key=body.idempotency_key,provider=settings.provider,model=settings.model,
              status='running',snapshot_hash=digest,reserved_idr=reserve,cost_idr=reserve,input_tokens=0,output_tokens=0,latency_ms=0,created=int(time.time()))
    db.add(run);audit(db,user,'ai_reserved',run.id);db.commit()
    run_id=run.id
    started=time.monotonic()
    result=None;inputs=outputs=0;failure=None
    try:
        result,inputs,outputs=generate(settings,messages,gaps)
        if inputs>input_bound or time.monotonic()-started>60:
            failure='usage_or_time_limit'
    except ProviderError as exc:
        failure=str(exc)
    db.expire_all()
    course=allowed(db,user,cid,lock=True)
    run=db.get(AIRun,run_id)
    run.latency_ms=int((time.monotonic()-started)*1000)
    current_digest,_=snapshot(db,course,body.student_id)
    if not failure and (current_digest!=digest or os.getenv('AGENT_DISABLED')=='1'):
        failure='stale_or_disabled'
    run.input_tokens=inputs;run.output_tokens=outputs
    # Failed/uncertain calls retain full reservation: timeouts can still be billed.
    if result is not None and inputs<=input_bound:
        actual=settings.cost(inputs,outputs)
        budget=db.get(AIBudget,(cid,period));budget.committed_idr-=reserve-actual
        run.cost_idr=actual
    if failure:
        run.status='failed' if failure!='stale_or_disabled' else 'blocked'
        audit(db,user,'ai_'+run.status,run.id);db.commit()
        raise HTTPException(502,'Run AI ditahan/gagal. Lihat log run; gunakan draft berbasis aturan bila diperlukan.')
    content=result.model_dump()
    content.update({'method':'ai','provider':settings.provider,'model':settings.model,'run_id':run.id,'prompt_version':'academic-v1','formula_version':outcome['formula_version']})
    for a in content['activities']:
        a['gap']=next(g['gap'] for g in gaps if g['id']==a['cpmk_id'])
    item=Intervention(id=str(uuid4()),class_id=cid,student_id=body.student_id,snapshot_hash=digest,content_json=json.dumps(content),
                      status='draft',key='ai-'+run.id)
    db.add(item);db.flush()
    run.status='succeeded';run.intervention_id=item.id
    audit(db,user,'ai_draft_created',item.id);db.commit()
    return {'run_id':run.id,'status':run.status,'intervention_id':item.id}
