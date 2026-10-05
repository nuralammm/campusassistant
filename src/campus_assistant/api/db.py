import os
from sqlalchemy import create_engine, String, Integer, Float, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20))

class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires: Mapped[int] = mapped_column(Integer)

class CourseClass(Base):
    __tablename__ = "classes"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    policy_json: Mapped[str] = mapped_column(Text)

class Membership(Base):
    __tablename__ = "memberships"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id"), primary_key=True)

class Student(Base):
    __tablename__ = "students"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id"))
    name: Mapped[str] = mapped_column(String(120))

class Score(Base):
    __tablename__ = "scores"
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)

class Intervention(Base):
    __tablename__ = "interventions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id"))
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    content_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    followup_json: Mapped[str] = mapped_column(Text, default="{}")
    key: Mapped[str] = mapped_column(String(80))
    __table_args__ = (UniqueConstraint("class_id", "key"),)

class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    actor: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(60))
    object_id: Mapped[str] = mapped_column(String(80))
    created: Mapped[int] = mapped_column(Integer)

class Measurement(Base):
    __tablename__ = "measurements"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id"))
    case_id: Mapped[str] = mapped_column(String(80))
    arm: Mapped[str] = mapped_column(String(1))
    minutes: Mapped[float] = mapped_column(Float)
    review_minutes: Mapped[float] = mapped_column(Float)
    correction_minutes: Mapped[float] = mapped_column(Float)
    cost_idr: Mapped[float] = mapped_column(Float)
    __table_args__ = (UniqueConstraint("class_id", "case_id", "arm"),)


def make_engine(url=None):
    url = url or os.getenv("DATABASE_URL", "sqlite:///./campus.db")
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        from sqlalchemy import event
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    return engine

engine = make_engine()
SessionLocal = sessionmaker(engine, expire_on_commit=False)
