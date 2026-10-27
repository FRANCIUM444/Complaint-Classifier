from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

import sys
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from src.predictor import ComplaintPredictor
from src.preprocessing import extract_location
from src.similarity import find_similar

APP_NAME = "CampusCare API"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(Path(__file__).resolve().parent / 'campuscare.db').as_posix()}")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="student")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Complaint(Base):
    __tablename__ = "complaints"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    submitter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(180), default="Not detected")
    predicted_category: Mapped[str] = mapped_column(String(60))
    confirmed_category: Mapped[str] = mapped_column(String(60))
    predicted_priority: Mapped[str] = mapped_column(String(20))
    final_priority: Mapped[str] = mapped_column(String(20))
    sentiment: Mapped[str] = mapped_column(String(20), default="Neutral")
    suggested_department: Mapped[str] = mapped_column(String(100))
    assigned_department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Pending", index=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolution_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_post_id: Mapped[Optional[int]] = mapped_column(ForeignKey("posts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    history: Mapped[list["ComplaintHistory"]] = relationship(back_populates="complaint", cascade="all, delete-orphan")

class ComplaintHistory(Base):
    __tablename__ = "complaint_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    previous_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(String(20))
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    complaint: Mapped[Complaint] = relationship(back_populates="history")

class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(60), default="Other")
    location: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    moderation_status: Mapped[str] = mapped_column(String(20), default="visible", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    comments: Mapped[list["Comment"]] = relationship(back_populates="post", cascade="all, delete-orphan")
    likes: Mapped[list["PostLike"]] = relationship(cascade="all, delete-orphan")

class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("comments.id", ondelete="CASCADE"), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    moderation_status: Mapped[str] = mapped_column(String(20), default="visible")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    post: Mapped[Post] = relationship(back_populates="comments")
    likes: Mapped[list["CommentLike"]] = relationship(cascade="all, delete-orphan")

class PostLike(Base):
    __tablename__ = "post_likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_like"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

class CommentLike(Base):
    __tablename__ = "comment_likes"
    __table_args__ = (UniqueConstraint("comment_id", "user_id", name="uq_comment_like"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    comment_id: Mapped[int] = mapped_column(ForeignKey("comments.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(String(300))
    related_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ContentReport(Base):
    __tablename__ = "content_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    content_type: Mapped[str] = mapped_column(String(20))
    content_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(300))
    review_status: Mapped[str] = mapped_column(String(20), default="open")
    moderator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return base64.urlsafe_b64encode(salt + digest).decode()

def verify_password(password: str, encoded: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(encoded.encode())
        salt, expected = raw[:16], raw[16:]
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    # Safe for local development only; production deployment must set SECRET_KEY.
    SECRET_KEY = secrets.token_urlsafe(48)
bearer = HTTPBearer(auto_error=False)

def make_token(user: User) -> str:
    payload = {"sub": user.id, "role": user.role, "exp": int((datetime.now(timezone.utc) + timedelta(hours=8)).timestamp())}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest()
    return body + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")

def read_token(token: str) -> dict:
    try:
        body, sig = token.split(".", 1)
        expected = base64.urlsafe_b64encode(hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(sig, expected):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(payload["exp"]) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("expired")
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    payload = read_token(creds.credentials)
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Account unavailable")
    return user

def require_roles(*roles: str):
    def guard(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission for this action")
        return user
    return guard

DEPARTMENTS = {
    "Electrical": "Electrical Maintenance", "Cleanliness": "Housekeeping",
    "Internet": "IT Support", "Academic": "Academic Administration",
    "Hostel": "Hostel Administration", "Security": "Campus Security",
    "Transport": "Transport Office", "Library": "Library Administration",
    "Food": "Food Services", "Other": "Student Affairs",
}
CRITICAL_TERMS = ("fire", "smoke", "exposed wire", "electric shock", "threatened", "physical attack", "immediate danger")
NEGATIVE_TERMS = ("broken", "not working", "dirty", "unsafe", "issue", "problem", "leak", "no internet", "unresolved", "damaged")
POSITIVE_TERMS = ("thank", "excellent", "appreciate", "working well")

def analyze_text(text: str, predictor: ComplaintPredictor) -> dict:
    result = predictor.predict(text)
    lowered = text.lower()
    critical = any(term in lowered for term in CRITICAL_TERMS)
    sentiment = "Positive" if any(term in lowered for term in POSITIVE_TERMS) else ("Negative" if any(term in lowered for term in NEGATIVE_TERMS) else "Neutral")
    result["sentiment"] = sentiment
    result["suggested_department"] = DEPARTMENTS.get(result["category"], DEPARTMENTS["Other"])
    result["safety_review_required"] = critical or result["category_confidence"] < 0.35
    if critical:
        result["safety_flag"] = "Potential immediate safety risk — escalate for human review"
    else:
        result["safety_flag"] = None
    result["analysis_notice"] = "Sentiment is a lightweight keyword heuristic, not a separately trained sentiment model."
    return result

predictor: ComplaintPredictor | None = None

@asynccontextmanager
async def lifespan(_app: FastAPI):
    global predictor
    try:
        predictor = ComplaintPredictor()
    except FileNotFoundError:
        predictor = None
    yield

app = FastAPI(title=APP_NAME, version="1.0.0", description="Campus complaint management and community API", lifespan=lifespan)

origins = [x.strip() for x in os.getenv("FRONTEND_ORIGIN", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET","POST","PATCH","DELETE","OPTIONS"], allow_headers=["Authorization","Content-Type"])

@app.get("/api/health")
def health():
    return {"status": "ok", "service": APP_NAME, "model_loaded": predictor is not None}

class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class ComplaintAnalyzeIn(BaseModel):
    description: str = Field(min_length=10, max_length=5000)
    location: Optional[str] = Field(default=None, max_length=180)

class ComplaintCreateIn(ComplaintAnalyzeIn):
    confirmed_category: Optional[str] = Field(default=None, max_length=60)
    source_post_id: Optional[int] = None

class ComplaintUpdateIn(BaseModel):
    status: Optional[Literal["Pending","In Progress","Resolved","Rejected"]] = None
    assigned_department: Optional[str] = Field(default=None, max_length=100)
    final_priority: Optional[Literal["Low","Medium","High","Critical"]] = None
    rejection_reason: Optional[str] = Field(default=None, max_length=1000)
    resolution_details: Optional[str] = Field(default=None, max_length=2000)
    note: Optional[str] = Field(default=None, max_length=1000)

class PostIn(BaseModel):
    content: str = Field(min_length=2, max_length=3000)
    category: str = Field(default="Other", max_length=60)
    location: Optional[str] = Field(default=None, max_length=180)

class CommentIn(BaseModel):
    content: str = Field(min_length=1, max_length=1500)
    parent_id: Optional[int] = None

class ReportIn(BaseModel):
    content_type: Literal["post","comment"]
    content_id: int = Field(gt=0)
    reason: str = Field(min_length=5, max_length=300)

class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=1000)

def user_out(user: User):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}

def complaint_out(c: Complaint, include_history=False):
    out = {"id": c.id, "complaint_id": c.public_id, "description": c.description, "location": c.location,
           "predicted_category": c.predicted_category, "category": c.confirmed_category,
           "predicted_priority": c.predicted_priority, "priority": c.final_priority,
           "sentiment": c.sentiment, "suggested_department": c.suggested_department,
           "assigned_department": c.assigned_department, "status": c.status,
           "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat(),
           "resolution_details": c.resolution_details, "rejection_reason": c.rejection_reason}
    if include_history:
        out["history"] = [{"previous_status": h.previous_status, "new_status": h.new_status, "note": h.note, "created_at": h.created_at.isoformat()} for h in sorted(c.history, key=lambda x:x.created_at)]
    return out

@app.post("/api/auth/register", status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(name=data.name.strip(), email=email, password_hash=hash_password(data.password), role="student")
    db.add(user); db.commit(); db.refresh(user)
    return {"access_token": make_token(user), "token_type": "bearer", "user": user_out(user)}

@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not verify_password(data.password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return {"access_token": make_token(user), "token_type": "bearer", "user": user_out(user)}

@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return user_out(user)

@app.post("/api/complaints/analyze")
def analyze(data: ComplaintAnalyzeIn, user: User = Depends(current_user)):
    if predictor is None:
        raise HTTPException(status_code=503, detail="ML artifacts are missing. Run python -m src.train from the repository root.")
    result = analyze_text(data.description, predictor)
    if data.location and data.location.strip():
        result["location"] = data.location.strip()
    return result

@app.post("/api/complaints", status_code=201)
def create_complaint(data: ComplaintCreateIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if predictor is None:
        raise HTTPException(status_code=503, detail="ML artifacts are not loaded")
    analysis = analyze_text(data.description, predictor)
    if data.source_post_id is not None:
        source_post = db.get(Post, data.source_post_id)
        if not source_post or source_post.moderation_status != "visible":
            raise HTTPException(status_code=404, detail="Source discussion not found")
    category = data.confirmed_category or analysis["category"]
    location = (data.location or analysis["location"] or "Not detected").strip()
    if data.location and data.location.strip():
        location = data.location.strip()
    priority = "Critical" if analysis["safety_flag"] else analysis["priority"]
    c = Complaint(public_id="CC-" + secrets.token_hex(4).upper(), submitter_id=user.id,
                  description=data.description.strip(), location=location, predicted_category=analysis["category"],
                  confirmed_category=category, predicted_priority=analysis["priority"], final_priority=priority,
                  sentiment=analysis["sentiment"], suggested_department=analysis["suggested_department"],
                  source_post_id=data.source_post_id)
    db.add(c); db.flush()
    db.add(ComplaintHistory(complaint_id=c.id, actor_id=user.id, previous_status=None, new_status="Pending", note="Complaint submitted"))
    db.commit(); db.refresh(c)
    return complaint_out(c, True)

@app.get("/api/complaints")
def list_complaints(search: str = "", status_filter: str = "", category: str = "", page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(Complaint)
    if user.role == "student":
        query = query.where(Complaint.submitter_id == user.id)
    elif user.role == "staff":
        query = query.where(Complaint.assigned_department.is_not(None))
    if status_filter:
        query = query.where(Complaint.status == status_filter)
    if category:
        query = query.where(Complaint.confirmed_category == category)
    if search.strip():
        query = query.where(Complaint.description.ilike(f"%{search.strip()}%") | Complaint.public_id.ilike(f"%{search.strip()}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(Complaint.created_at.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {"items":[complaint_out(c) for c in rows], "total":total, "page":page, "page_size":page_size}

@app.get("/api/complaints/{complaint_id}")
def get_complaint(complaint_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = db.scalar(select(Complaint).where(Complaint.public_id == complaint_id))
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if user.role == "student" and c.submitter_id != user.id:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if user.role == "staff" and c.assigned_department is None:
        raise HTTPException(status_code=403, detail="Complaint is not assigned to your scope")
    return complaint_out(c, True)

@app.patch("/api/complaints/{complaint_id}")
def update_complaint(complaint_id: str, data: ComplaintUpdateIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin","staff"))):
    c = db.scalar(select(Complaint).where(Complaint.public_id == complaint_id))
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if user.role == "staff" and c.assigned_department is None:
        raise HTTPException(status_code=403, detail="Complaint is not assigned to your scope")
    if data.status == "Rejected" and not (data.rejection_reason or "").strip():
        raise HTTPException(status_code=422, detail="A rejection reason is required")
    old_status = c.status
    if data.status: c.status = data.status
    if data.assigned_department is not None: c.assigned_department = data.assigned_department
    if data.final_priority: c.final_priority = data.final_priority
    if data.rejection_reason is not None: c.rejection_reason = data.rejection_reason
    if data.resolution_details is not None: c.resolution_details = data.resolution_details
    if c.status == "Resolved": c.resolved_at = datetime.now(timezone.utc)
    if c.status != old_status or data.note or data.assigned_department is not None:
        db.add(ComplaintHistory(complaint_id=c.id, actor_id=user.id, previous_status=old_status, new_status=c.status, note=data.note or ("Department assigned: " + str(data.assigned_department) if data.assigned_department else None)))
        db.add(Notification(recipient_id=c.submitter_id, kind="complaint_update", message=f"Complaint {c.public_id} updated: {c.status}", related_id=c.id))
    db.commit(); db.refresh(c)
    return complaint_out(c, True)

@app.get("/api/analytics/overview")
def analytics(db: Session = Depends(get_db), user: User = Depends(require_roles("admin","staff"))):
    total = db.scalar(select(func.count(Complaint.id))) or 0
    counts = {s: db.scalar(select(func.count(Complaint.id)).where(Complaint.status == s)) or 0 for s in ["Pending","In Progress","Resolved","Rejected"]}
    high = db.scalar(select(func.count(Complaint.id)).where(Complaint.final_priority.in_(["High","Critical"]))) or 0
    cats = db.execute(select(Complaint.confirmed_category, func.count()).group_by(Complaint.confirmed_category)).all()
    depts = db.execute(select(Complaint.assigned_department, func.count()).where(Complaint.assigned_department.is_not(None)).group_by(Complaint.assigned_department)).all()
    resolved_dates = db.scalars(select(Complaint.resolved_at).where(Complaint.resolved_at.is_not(None))).all()
    avg_hours = None
    if resolved_dates:
        # Created timestamps are loaded only for resolved records to avoid fabricating a metric.
        records = db.scalars(select(Complaint).where(Complaint.resolved_at.is_not(None))).all()
        avg_hours = round(sum((r.resolved_at-r.created_at).total_seconds()/3600 for r in records)/len(records), 1)
    return {"total":total, "pending":counts["Pending"], "in_progress":counts["In Progress"], "resolved":counts["Resolved"], "rejected":counts["Rejected"], "high_priority":high, "resolution_rate":round(counts["Resolved"]/total*100,1) if total else 0, "average_resolution_hours":avg_hours, "categories":[{"category":k,"count":v} for k,v in cats], "departments":[{"department":k,"count":v} for k,v in depts]}

@app.get("/api/analytics/trends")
def trends(db: Session = Depends(get_db), user: User = Depends(require_roles("admin","staff"))):
    rows = db.execute(select(func.date(Complaint.created_at), func.count()).group_by(func.date(Complaint.created_at)).order_by(func.date(Complaint.created_at))).all()
    return {"items":[{"date":str(day),"count":count} for day,count in rows]}

def post_out(p: Post, db: Session, user_id: int):
    author = db.get(User, p.author_id)
    return {"id":p.id, "content":p.content, "category":p.category, "location":p.location, "author":{"id":author.id,"name":author.name} if author else {"name":"Community member"}, "created_at":p.created_at.isoformat(), "likes":db.scalar(select(func.count(PostLike.id).where(PostLike.post_id==p.id)) if False else select(func.count()).select_from(PostLike).where(PostLike.post_id==p.id)) or 0, "comments":db.scalar(select(func.count()).select_from(Comment).where(Comment.post_id==p.id, Comment.moderation_status=="visible")) or 0, "liked_by_me":bool(db.scalar(select(PostLike.id).where(PostLike.post_id==p.id, PostLike.user_id==user_id))), "can_edit":p.author_id==user_id}

@app.post("/api/community/posts", status_code=201)
def create_post(data: PostIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p=Post(author_id=user.id, content=data.content.strip(), category=data.category.strip() or "Other", location=data.location)
    db.add(p); db.commit(); db.refresh(p)
    return post_out(p,db,user.id)

@app.get("/api/community/posts")
def list_posts(search: str="", category: str="", sort: Literal["newest","liked","discussed"]="newest", page: int=Query(1,ge=1), page_size: int=Query(20,ge=1,le=50), db: Session=Depends(get_db), user: User=Depends(current_user)):
    q=select(Post).where(Post.moderation_status=="visible")
    if category: q=q.where(Post.category==category)
    if search.strip(): q=q.where(Post.content.ilike(f"%{search.strip()}%"))
    posts=db.scalars(q.order_by(Post.created_at.desc()).offset((page-1)*page_size).limit(page_size)).all()
    items=[post_out(p,db,user.id) for p in posts]
    if sort=="liked": items.sort(key=lambda x:x["likes"],reverse=True)
    if sort=="discussed": items.sort(key=lambda x:x["comments"],reverse=True)
    return {"items":items,"page":page,"page_size":page_size}

@app.patch("/api/community/posts/{post_id}")
def edit_post(post_id: int, data: PostIn, db: Session=Depends(get_db), user: User=Depends(current_user)):
    p=db.get(Post,post_id)
    if not p or (p.author_id!=user.id and user.role not in ("admin","moderator")): raise HTTPException(status_code=404,detail="Post not found")
    p.content=data.content.strip(); p.category=data.category; p.location=data.location
    db.commit(); db.refresh(p); return post_out(p,db,user.id)

@app.delete("/api/community/posts/{post_id}", status_code=204)
def delete_post(post_id: int, db: Session=Depends(get_db), user: User=Depends(current_user)):
    p=db.get(Post,post_id)
    if not p or (p.author_id!=user.id and user.role not in ("admin","moderator")): raise HTTPException(status_code=404,detail="Post not found")
    db.delete(p); db.commit()

@app.post("/api/community/posts/{post_id}/like")
def like_post(post_id: int, db: Session=Depends(get_db), user: User=Depends(current_user)):
    p=db.get(Post,post_id)
    if not p or p.moderation_status!="visible": raise HTTPException(status_code=404,detail="Post not found")
    existing=db.scalar(select(PostLike).where(PostLike.post_id==post_id,PostLike.user_id==user.id))
    if not existing: db.add(PostLike(post_id=post_id,user_id=user.id)); db.commit()
    return {"liked":True,"likes":db.scalar(select(func.count()).select_from(PostLike).where(PostLike.post_id==post_id)) or 0}

@app.delete("/api/community/posts/{post_id}/like")
def unlike_post(post_id: int, db: Session=Depends(get_db), user: User=Depends(current_user)):
    existing=db.scalar(select(PostLike).where(PostLike.post_id==post_id,PostLike.user_id==user.id))
    if existing: db.delete(existing); db.commit()
    return {"liked":False,"likes":db.scalar(select(func.count()).select_from(PostLike).where(PostLike.post_id==post_id)) or 0}

@app.get("/api/community/posts/{post_id}/comments")
def list_comments(post_id: int, db: Session=Depends(get_db), user: User=Depends(current_user)):
    p=db.get(Post,post_id)
    if not p or p.moderation_status!="visible": raise HTTPException(status_code=404,detail="Post not found")
    rows=db.scalars(select(Comment).where(Comment.post_id==post_id,Comment.moderation_status=="visible").order_by(Comment.created_at)).all()
    return {"items":[{"id":c.id,"post_id":c.post_id,"author":(db.get(User,c.author_id).name if db.get(User,c.author_id) else "Community member"),"author_id":c.author_id,"parent_id":c.parent_id,"content":c.content,"created_at":c.created_at.isoformat()} for c in rows]}

@app.post("/api/community/posts/{post_id}/comments",status_code=201)
def add_comment(post_id:int,data:CommentIn,db:Session=Depends(get_db),user:User=Depends(current_user)):
    p=db.get(Post,post_id)
    if not p or p.moderation_status!="visible": raise HTTPException(status_code=404,detail="Post not found")
    if data.parent_id:
        parent=db.get(Comment,data.parent_id)
        if not parent or parent.post_id!=post_id: raise HTTPException(status_code=422,detail="Reply target must belong to this post")
        if parent.id==data.parent_id and parent.parent_id==data.parent_id: raise HTTPException(status_code=422,detail="Invalid reply relationship")
    c=Comment(post_id=post_id,author_id=user.id,parent_id=data.parent_id,content=data.content.strip())
    db.add(c)
    if p.author_id!=user.id: db.add(Notification(recipient_id=p.author_id,kind="comment",message=f"{user.name} commented on your campus discussion",related_id=post_id))
    db.commit(); db.refresh(c)
    return {"id":c.id,"post_id":post_id,"author":user.name,"author_id":user.id,"parent_id":c.parent_id,"content":c.content,"created_at":c.created_at.isoformat()}

@app.patch("/api/community/comments/{comment_id}")
def edit_comment(comment_id:int,data:CommentIn,db:Session=Depends(get_db),user:User=Depends(current_user)):
    c=db.get(Comment,comment_id)
    if not c or (c.author_id!=user.id and user.role not in ("admin","moderator")): raise HTTPException(status_code=404,detail="Comment not found")
    c.content=data.content.strip(); db.commit()
    return {"id":c.id,"content":c.content}

@app.delete("/api/community/comments/{comment_id}",status_code=204)
def delete_comment(comment_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    c=db.get(Comment,comment_id)
    if not c or (c.author_id!=user.id and user.role not in ("admin","moderator")): raise HTTPException(status_code=404,detail="Comment not found")
    db.delete(c); db.commit()

@app.post("/api/community/reports",status_code=201)
def report_content(data:ReportIn,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if data.content_type=="post":
        exists=db.get(Post,data.content_id)
    else:
        exists=db.get(Comment,data.content_id)
    if not exists: raise HTTPException(status_code=404,detail="Content not found")
    report=ContentReport(reporter_id=user.id,content_type=data.content_type,content_id=data.content_id,reason=data.reason.strip())
    db.add(report); db.commit(); db.refresh(report)
    return {"id":report.id,"review_status":report.review_status}

@app.get("/api/moderation/reports")
def moderation_queue(db:Session=Depends(get_db),user:User=Depends(require_roles("admin","moderator"))):
    rows=db.scalars(select(ContentReport).where(ContentReport.review_status=="open").order_by(ContentReport.created_at)).all()
    return {"items":[{"id":r.id,"content_type":r.content_type,"content_id":r.content_id,"reason":r.reason,"created_at":r.created_at.isoformat()} for r in rows]}

@app.patch("/api/moderation/reports/{report_id}")
def review_report(report_id:int,action:Literal["dismiss","hide"],db:Session=Depends(get_db),user:User=Depends(require_roles("admin","moderator"))):
    r=db.get(ContentReport,report_id)
    if not r: raise HTTPException(status_code=404,detail="Report not found")
    if action=="hide":
        if r.content_type=="post":
            obj=db.get(Post,r.content_id)
        else: obj=db.get(Comment,r.content_id)
        if obj: obj.moderation_status="hidden"
    r.review_status="dismissed" if action=="dismiss" else "actioned"; r.moderator_id=user.id
    db.commit(); return {"id":r.id,"review_status":r.review_status}

@app.get("/api/notifications")
def notifications(db:Session=Depends(get_db),user:User=Depends(current_user)):
    rows=db.scalars(select(Notification).where(Notification.recipient_id==user.id).order_by(Notification.created_at.desc()).limit(100)).all()
    return {"items":[{"id":n.id,"kind":n.kind,"message":n.message,"related_id":n.related_id,"is_read":n.is_read,"created_at":n.created_at.isoformat()} for n in rows]}

@app.patch("/api/notifications/{notification_id}/read")
def read_notification(notification_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    n=db.get(Notification,notification_id)
    if not n or n.recipient_id!=user.id: raise HTTPException(status_code=404,detail="Notification not found")
    n.is_read=True; db.commit(); return {"id":n.id,"is_read":True}

@app.post("/api/complaints/{complaint_id}/feedback",status_code=201)
def feedback(complaint_id:str,data:FeedbackIn,db:Session=Depends(get_db),user:User=Depends(current_user)):
    c=db.scalar(select(Complaint).where(Complaint.public_id==complaint_id,Complaint.submitter_id==user.id))
    if not c: raise HTTPException(status_code=404,detail="Complaint not found")
    if c.status!="Resolved": raise HTTPException(status_code=409,detail="Feedback is available after resolution")
    if db.scalar(select(Feedback).where(Feedback.complaint_id==c.id)): raise HTTPException(status_code=409,detail="Feedback already submitted")
    f=Feedback(complaint_id=c.id,user_id=user.id,rating=data.rating,comment=data.comment); db.add(f); db.commit()
    return {"submitted":True}
