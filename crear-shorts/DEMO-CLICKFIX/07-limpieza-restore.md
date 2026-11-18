# 07 — Limpieza y restauración completa

## Estado que hay que dejar (todo lo tocado por la demo)

### Restos de la demo v2 (exfiltración):
- [ ] Proceso C2: `pkill -f c2_server.py`
- [ ] Ventanas de Terminal (víctima + C2): cerrar todas
- [ ] Ventana de Safari con fake-page.html: cerrar
- [ ] Botín: `rm -rf ~/Desktop/clickfix-demo/c2_loot`
- [ ] Temp: el payload borra sus propios temporales (verificado)

### Restos de la demo v1 (persistencia — YA LIMPIADA en esta sesión, verificar):
```bash
launchctl list | grep systemcheck        # vacío = OK
ls ~/Library/LaunchAgents/ | grep systemcheck   # vacío = OK
ls ~/Desktop/clickfix-demo/infected.log  # no existe = OK
```
Si existiera algo (NO debería):
```bash
launchctl unload ~/Library/LaunchAgents/com.apple.systemcheck.plist
rm ~/Library/LaunchAgents/com.apple.systemcheck.plist
rm ~/Desktop/clickfix-demo/infected.log
```

### Apps ocultas (restaurar SIEMPRE al terminar):
```bash
osascript - <<'EOF'
tell application "System Events"
  set visible of process "stable" to true
  set visible of process "Warp" to true
  set visible of process "Brave Browser" to true
  set visible of process "WhatsApp" to true
  set visible of process "OBS" to true
end tell
EOF
```
**Nota:** al restaurar, esas apps vuelven a primer plano. Es normal.
El usuario recupera su sesión tal cual estaba (Cmd+H reversible, nada se cerró).

### Archivos de proyecto (NO borrar — son el material de la demo):
- `~/Desktop/clickfix-demo/` — toda la demo (página, payload, C2, decoys)
- `~/Desktop/ctrl-kit/` — herramientas del agente
- `~/Desktop/crear-shorts/` — esta documentación

Si el usuario quiere borrar la demo entera:
```bash
pkill -f c2_server.py
rm -rf ~/Desktop/clickfix-demo
# (dejar ctrl-kit y crear-shorts para futuros videos)
```

## Checklist final de "Mac impecable"

```bash
# 1. Sin procesos de la demo:
pgrep -fl "c2_server" && echo "C2 VIVO" || echo "C2 muerto ✓"

# 2. Sin persistencia:
launchctl list | grep -c systemcheck  # 0 = ✓

# 3. Apps restauradas:
osascript -e 'tell application "System Events" to get name of every process whose visible is true'
# deben aparecer: stable, Warp, Brave, WhatsApp, OBS...

# 4. Sin basura temporal:
ls /tmp/pilenv 2>/dev/null   # venv de Pillow — opcional borrar
```

## Qué NO hay que limpiar (el usuario lo tiene legítimo)

- `~/Library/LaunchAgents/ai.openclaw.gateway.plist`, `com.google.*`, 
  `org.virtualbox.*` — LaunchAgents del usuario, intactos, no tocarlos
- El permiso de Accesibilidad de opencode — dejarlo activo
  (es lo que da al agente el control para futuros videos; revocarlo solo si el
  usuario lo pide explícitamente)
