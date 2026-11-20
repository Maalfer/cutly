"""Qué agentes de IA puede cargar el panel acoplable (el terminal es genérico: TerminalClaude lanza cualquier
programa, ver estudio/terminal/widget.py). Añadir uno nuevo: una entrada aquí + su integración de estado si la
soporta (ver `.opencode/plugins/cutly-estado.js` para el patrón con OpenCode; Claude Code usa sus hooks nativos,
`estudio/hooks/estado_claude.py`, declarados en `.claude/settings.json`)."""

MOTORES = {
    "claude": {
        "nombre": "Claude Code",
        "comando": ["claude"],
        "continuar": ["claude", "--continue"],
        "binario": "claude",
    },
    "opencode": {
        "nombre": "OpenCode",
        # --standalone: servidor propio por sesión, en vez del servicio de fondo compartido (que puede tener
        # cacheada la lista de plugins de antes de que estudio/motores.py o .opencode/plugins/ existieran) —
        # medido: sin esto, el plugin de estado (cutly-estado.js) no se cargaba en la sesión de la app.
        "comando": ["opencode", "--standalone"],
        "continuar": ["opencode", "--continue", "--standalone"],
        "binario": "opencode",
    },
}
MOTOR_DEFECTO = "claude"
