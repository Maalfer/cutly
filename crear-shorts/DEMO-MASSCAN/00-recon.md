# masscan — escaneo masivo de la propia red doméstica: guion técnico

> Objetivo: la red doméstica del propio usuario (WiFi/LAN de casa), NO un laboratorio de terceros.
> Marco ético: es la red del propio usuario (router + dispositivos de su casa) — autorización propia,
> sin necesidad de un laboratorio aparte. La VM `kali` tiene su adaptador de red en **modo puente**
> (`bridged`, sobre el WiFi real del anfitrión) en vez del NAT habitual, así que su interfaz `eth0` vive
> en la misma subred que el resto de la casa (medido: `192.168.1.0/24`, gateway `192.168.1.1`, la VM en
> `192.168.1.11`). Nada se toca del anfitrión Windows ni de ningún dispositivo ajeno a la red del usuario.

## 1. Qué es masscan (para el guion del vídeo)
`masscan` es un escáner de puertos TCP/ICMP asíncrono (Robert David Graham): en vez de esperar
respuesta por host como `nmap`, dispara paquetes a toda velocidad y recoge las respuestas según llegan —
por eso puede recorrer una red entera en segundos en vez de minutos. Dos modos usados en esta demo:
- **`--ping`**: barrido ICMP Echo puro (sin puertos) → qué IPs de la subred están vivas.
- **`-p<puerto>`**: SYN scan a un puerto concreto en toda la subred → qué IPs tienen ese puerto abierto.

## 2. La secuencia (medida, funciona contra la red real de esta máquina)
```bash
# 1) ¿Cuál es mi red? (interfaz puente, no la NAT por defecto)
ip -br a show eth0                      # UP  192.168.1.11/24 ...
ip route | grep default                 # default via 192.168.1.1 dev eth0

# 2) Escaneo masivo: todos los hosts vivos de la subred (barrido ICMP)
sudo masscan 192.168.1.0/24 --ping --rate 2000 --wait 2
# → "Discovered open port 0/icmp on 192.168.1.X" por cada host vivo (medido: 10 hosts en esta red)

# 3) ¿Quién tiene el puerto 80 abierto?
sudo masscan -p80 192.168.1.0/24 --rate 2000 --wait 2
# → "Discovered open port 80/tcp on 192.168.1.X" (medido: el router + varios dispositivos, 6 en esta red)

# 4) Guardar el resultado
sudo masscan -p80 192.168.1.0/24 --rate 2000 --wait 2 -oL ~/resultado_masscan.txt
cat ~/resultado_masscan.txt
```
`--wait 2` acorta la espera final de masscan (por defecto ~10 s esperando retransmisiones tardías) a 2 s:
mismo resultado, menos tiempo muerto en el vídeo. `--rate 2000` es generoso pero no agresivo para una
red doméstica de /24 (256 IPs): el barrido entero tarda bien por debajo de un segundo de tráfico real.

## 3. Por qué hizo falta cambiar la red de la VM
La VM viene por defecto con un único adaptador NAT (`10.0.2.0/24` interno de VirtualBox, aislado): un
escaneo ahí solo vería la puerta de enlace virtual, nunca los dispositivos reales de casa. El usuario
cambió el adaptador a **modo puente** sobre su WiFi (`VBoxManage modifyvm kali --nic1 bridged
--bridgeadapter1 "<adaptador WiFi>"`) para que `eth0` del invitado sea un dispositivo más de su LAN real.
**Efecto colateral:** el reenvío NAT `127.0.0.1:2222→22` que usa `vm_control.py` para el canal SSH deja
de funcionar (ya no hay NAT). Se arregló añadiendo `VM_HOST` (por defecto `127.0.0.1`, para NAT) a
`vm/config.py` / `vm/canales/ssh.py`: con la VM en puente, el control se hace con
`VM_HOST=<IP real de la VM> VM_SSH_PORT=22` antes de cualquier comando de `vm_control.py` (incluida esta
demo). La IP real se puede ver sin SSH con `vm_control.py status` (la lee de las Guest Additions).

## 4. Para el vídeo (guion sugerido)
1. **Gancho:** "¿sabes cuántos dispositivos hay conectados a tu propio WiFi ahora mismo?"
2. **Mi red:** `ip -br a` — esta es la subred de mi casa.
3. **El escaneo masivo:** `masscan --ping` sobre toda la subred — todos los hosts vivos en segundos.
4. **El filtro:** `masscan -p80` — quién tiene un servidor web escuchando (típico: el router, alguna
   cámara/impresora/NAS con panel web).
5. **Cierre:** guardar el resultado (`-oL`) y mostrarlo con `cat` — así de rápido se mapea una red entera.

## 5. Nada que limpiar
No se despliega ningún laboratorio ni contenedor: el objetivo es la red real del propio usuario, siempre
viva. No se escribe ni se cambia nada en ningún dispositivo ajeno — solo paquetes de sondeo (ICMP echo /
TCP SYN), igual que hace cualquier escáner de puertos.
