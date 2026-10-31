from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from cutly.auth import (
    DUMMY_PASSWORD_HASH,
    Principal,
    current_principal,
    generate_api_key,
    require_write,
    verify_password,
)
from cutly.db.models import ApiKey, User
from cutly.db.session import get_session
from cutly.services.sanitize.text import sanitize_label

router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class KeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    can_write: bool = False

    @field_validator("name")
    @classmethod
    def _sanitize_name(cls, v: str) -> str:
        v = sanitize_label(v)
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        return v


@router.post("/auth/login")
def login(body: LoginIn, request: Request, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == body.username)).first()
    # Se calcula el hash siempre (señuelo si el usuario no existe): si no, el tiempo de respuesta
    # delata qué usernames existen aunque el mensaje de error sea idéntico.
    pw_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    valid = verify_password(pw_hash, body.password)
    if user is None or not valid:
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    request.session["user_id"] = user.id
    return {"username": user.username}


@router.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/auth/me")
def me(p: Principal = Depends(current_principal)):
    return {"kind": p.kind, "name": p.name, "can_write": p.can_write}


@router.get("/api-keys")
def list_keys(p: Principal = Depends(require_write), session: Session = Depends(get_session)):
    if p.kind != "user":
        raise HTTPException(403, "Solo una sesión web puede listar API keys")
    keys = session.exec(select(ApiKey)).all()
    return [k.model_dump(exclude={"key_hash"}) for k in keys]


@router.post("/api-keys")
def create_key(body: KeyIn, p: Principal = Depends(require_write), session: Session = Depends(get_session)):
    if p.kind != "user":
        raise HTTPException(403, "Solo una sesión web puede crear API keys")
    key, token = generate_api_key(session, body.name, body.can_write)
    return {"id": key.id, "name": key.name, "can_write": key.can_write, "token": token}


@router.delete("/api-keys/{key_id}")
def revoke_key(key_id: str, p: Principal = Depends(require_write), session: Session = Depends(get_session)):
    if p.kind != "user":
        raise HTTPException(403, "Solo una sesión web puede revocar API keys")
    key = session.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(404, "API key no encontrada")
    key.revoked = True
    session.add(key)
    session.commit()
    return {"ok": True}
