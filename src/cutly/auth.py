"""Contraseñas (argon2), API keys hasheadas y sesión web."""

import hashlib
import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from cutly.db.models import ApiKey, User, now
from cutly.db.session import get_session

_ph = PasswordHasher()
KEY_PREFIX = "ct_"


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


# Hash señuelo para que un login con usuario inexistente cueste lo mismo que uno con contraseña
# incorrecta (si no, el tiempo de respuesta delata qué usernames existen: CWE-208).
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def verify_password(pw_hash: str, pw: str) -> bool:
    try:
        return _ph.verify(pw_hash, pw)
    except VerifyMismatchError:
        return False


def hash_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_api_key(session: Session, name: str, can_write: bool) -> tuple[ApiKey, str]:
    """Devuelve (registro, token en claro). El token solo se muestra una vez."""
    token = KEY_PREFIX + secrets.token_urlsafe(32)
    key = ApiKey(name=name, key_hash=hash_key(token), prefix=token[:8], can_write=can_write)
    session.add(key)
    session.commit()
    session.refresh(key)
    return key, token


@dataclass
class Principal:
    kind: str  # "user" | "key"
    name: str
    can_write: bool


def current_principal(request: Request, session: Session = Depends(get_session)) -> Principal:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        key = session.exec(select(ApiKey).where(ApiKey.key_hash == hash_key(token))).first()
        if key is None or key.revoked:
            raise HTTPException(401, "API key inválida o revocada")
        key.last_used_at = now()
        session.add(key)
        session.commit()
        return Principal("key", key.name, key.can_write)
    user_id = request.session.get("user_id")
    if user_id:
        user = session.get(User, user_id)
        if user:
            return Principal("user", user.username, True)
    raise HTTPException(401, "No autenticado: usa sesión web o 'Authorization: Bearer <api key>'")


def require_read(p: Principal = Depends(current_principal)) -> Principal:
    return p


def require_write(p: Principal = Depends(current_principal)) -> Principal:
    if not p.can_write:
        raise HTTPException(403, "Esta API key es de solo lectura; necesitas una con permiso de escritura")
    return p
