"""Administrator sign-in and the audit log."""

from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from sqlalchemy import select

from ..admin_security import admin_access_configured, create_session_token, valid_session_token, verify_password
from ..config import ADMIN_SESSION_TTL_SECONDS, APP_ENV
from ..dependencies import AdminDep, SessionDep
from ..models import AuditLog
from ..schemas import AdminLogin

router = APIRouter(tags=["admin"])

SESSION_COOKIE = "admin_session"
# Sessions shorter than this would sign staff out in the middle of a review.
MIN_SESSION_SECONDS = 900


@router.get("/api/admin/session")
def admin_session_status(admin_session: Annotated[str | None, Cookie()] = None) -> dict:
    return {
        "configured": admin_access_configured(),
        "authenticated": valid_session_token(admin_session),
    }


@router.post("/api/admin/login")
def admin_login(credentials: AdminLogin, response: Response) -> dict:
    if not admin_access_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ผู้ดูแลยังไม่ได้เปิดใช้หน้าจัดการข้อมูล",
        )
    if not verify_password(credentials.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="รหัสผ่านไม่ถูกต้อง")
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(),
        max_age=max(MIN_SESSION_SECONDS, ADMIN_SESSION_TTL_SECONDS),
        httponly=True,
        samesite="strict",
        secure=APP_ENV not in {"development", "test"},
    )
    return {"authenticated": True}


@router.post("/api/admin/logout")
def admin_logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="strict")
    return {"authenticated": False}


@router.get("/api/admin/audit")
def admin_audit(session: SessionDep, _: AdminDep) -> dict:
    """The 20 most recent administrator changes."""
    items = session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(20)).all()
    return {"items": [{
        "id": item.id,
        "action": item.action,
        "entity_type": item.entity_type,
        "entity_id": item.entity_id,
        "actor": item.actor,
        "created_at": item.created_at,
        "before_data": item.before_data,
        "after_data": item.after_data,
    } for item in items]}
