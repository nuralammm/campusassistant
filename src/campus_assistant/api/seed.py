"""Explicit synthetic seed. Requires operator-supplied password."""
import json
import os
from sqlalchemy import select
from campus_assistant.api.db import SessionLocal, User, CourseClass, Membership, Student, Score
from campus_assistant.api.security import hash_password

POLICY = {
    "cpmks": [{"id": "CPMK-01", "target": 75, "cpl_mapping": {"CPL-01": "0.7", "CPL-02": "0.3"}},
              {"id": "CPMK-02", "target": 75, "cpl_mapping": {"CPL-01": "0.3", "CPL-02": "0.7"}},
              {"id": "CPMK-03", "target": 80, "cpl_mapping": {"CPL-02": "1"}}],
    "cpl_targets": {"CPL-01": 75, "CPL-02": 80},
    "assessments": [{"id": f"ASM-0{i}", "cpmk_id": f"CPMK-0{i}", "weight": "1"} for i in range(1, 4)]}


def seed(db, password):
    if len(password) < 12:
        raise ValueError("DEMO_PASSWORD must contain at least 12 characters")
    if db.get(CourseClass, "RPL-01"):
        return
    db.add(User(id="dosen", role="lecturer", password_hash=hash_password(password)))
    db.add(CourseClass(id="RPL-01", name="Rekayasa Perangkat Lunak • Kelas Sintetis", revision=1, policy_json=json.dumps(POLICY)))
    db.flush()
    db.add(Membership(user_id="dosen", class_id="RPL-01"))
    scores = [[92, 90, 94], [76, 74, 77], [78, 52, 69], [82, 79, 50], [88, 58, 80],
              [84, 72, 60], [58, 68, 79], [50, 46, 48], [88, 61, 57], [58, None, 84]]
    for i, values in enumerate(scores, 1):
        sid = f"STD-{i:03}"
        db.add(Student(id=sid, class_id="RPL-01", name=f"Mahasiswa Sintetis {i:02}"))
        db.flush()
        for a, value in enumerate(values, 1):
            db.add(Score(student_id=sid, assessment_id=f"ASM-0{a}", value=value))
    db.commit()

if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db, os.environ["DEMO_PASSWORD"])
    print("Synthetic class ready; username: dosen")
