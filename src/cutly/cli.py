"""CLI de administración: crear usuario y API keys (no hay registro público)."""

import argparse
import getpass
import os

from sqlmodel import Session, select

from cutly.auth import generate_api_key, hash_password
from cutly.db.models import User
from cutly.db.session import get_engine, init_db


def _ask_password() -> str:
    pw = os.environ.get("CUTLY_PASSWORD") or getpass.getpass("Contraseña: ")
    if len(pw) < 10:
        raise SystemExit("Mínimo 10 caracteres")
    return pw


def main() -> None:
    p = argparse.ArgumentParser(prog="cutly")
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("create-user")
    u.add_argument("username")
    sp = sub.add_parser("set-password", help="cambia la contraseña (o usa CUTLY_PASSWORD)")
    sp.add_argument("username")
    k = sub.add_parser("create-key")
    k.add_argument("name")
    k.add_argument("--write", action="store_true", help="permiso de escritura")
    args = p.parse_args()

    init_db()
    with Session(get_engine()) as s:
        if args.cmd == "set-password":
            user = s.exec(select(User).where(User.username == args.username)).first()
            if not user:
                raise SystemExit("Usuario no encontrado")
            user.password_hash = hash_password(_ask_password())
            s.add(user)
            s.commit()
            print("Contraseña actualizada")
        elif args.cmd == "create-user":
            if s.exec(select(User).where(User.username == args.username)).first():
                raise SystemExit("El usuario ya existe")
            s.add(User(username=args.username, password_hash=hash_password(_ask_password())))
            s.commit()
            print("Usuario creado")
        else:
            key, token = generate_api_key(s, args.name, args.write)
            print(f"API key ({'escritura' if key.can_write else 'lectura'}): {token}")
            print("Guárdala ahora: no se vuelve a mostrar.")


if __name__ == "__main__":
    main()
