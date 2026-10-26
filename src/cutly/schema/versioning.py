"""Migraciones del JSON del proyecto entre versiones de esquema.

Para subir de versión: incrementa CURRENT_VERSION en project.py y registra aquí
`@migration(from_version)` una función que reciba el dict de esa versión y devuelva el de la siguiente.
"""

from collections.abc import Callable

from cutly.schema.project import CURRENT_VERSION

MIGRATIONS: dict[int, Callable[[dict], dict]] = {}


def migration(from_version: int):
    def deco(fn):
        MIGRATIONS[from_version] = fn
        return fn

    return deco


def migrate_doc(data: dict) -> tuple[dict, bool]:
    """Devuelve (documento en la versión actual, si hubo migración)."""
    version = data.get("schema_version", 1)
    if version > CURRENT_VERSION:
        raise ValueError(f"El proyecto usa el esquema v{version}, más nuevo que este servidor (v{CURRENT_VERSION})")
    changed = False
    while version < CURRENT_VERSION:
        if version not in MIGRATIONS:
            raise ValueError(f"No hay migración de esquema desde la versión {version}")
        data = MIGRATIONS[version](dict(data))
        version += 1
        data["schema_version"] = version
        changed = True
    return data, changed
