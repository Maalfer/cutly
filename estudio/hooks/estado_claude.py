#!/usr/bin/env python3
"""Hook de Claude Code -> cutly estudio: deja en un fichero en qué está la sesión, para que la app lo enseñe
(Claude trabajando / necesita tu respuesta / ha terminado) sin tener que leer el terminal.

    python estado_claude.py trabajando|necesita|libre      (stdin: el JSON que Claude Code pasa a cada hook)

Solo actúa en la sesión que lanzó cutly estudio: la app pone CUTLY_ESTADO_FICHERO en el entorno de `claude`, y los
hooks lo heredan. En cualquier otra sesión (tu terminal de siempre) no hace nada.

Reglas para no estorbar a Claude Code: no imprime NADA (en UserPromptSubmit lo impreso se añadiría al contexto),
sale siempre con código 0 (otro código podría bloquear) y es rápido (sin importar nada pesado).
"""
import json
import os
import sys
import time


def main():
    destino = os.environ.get("CUTLY_ESTADO_FICHERO")
    if not destino or len(sys.argv) < 2:
        return
    try:
        datos = json.load(sys.stdin)
    except Exception:
        datos = {}
    estado = {"estado": sys.argv[1], "t": time.time(),
              "evento": datos.get("hook_event_name", ""), "mensaje": datos.get("message", "")}
    tmp = destino + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False)
    os.replace(tmp, destino)              # atómico: la app nunca lee un fichero a medias


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
