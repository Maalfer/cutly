# 00 — Empezar aquí: todas las demos se graban DENTRO de una VM

> **Regla del repo:** las demos se ejecutan en una VM de VirtualBox (Kali/Debian con X11), **nunca en el
> ordenador anfitrión**. La IA actúa y se mueve; el usuario solo graba. El anfitrión puede ser **Windows,
> macOS o Linux**: lo único que cambia es cómo se instalan `VBoxManage`, `ssh`, `ffmpeg` y Tesseract
> (ver [`../../PORTABILIDAD.md`](../../PORTABILIDAD.md)). El control en sí es idéntico.

```
 ANFITRIÓN (cualquier SO)                      INVITADO (Kali/Debian, X11)
 ┌──────────────────────────┐   screenshotpng   ┌──────────────────────────┐
 │ vm_control.py            │◀──────────────────│ pantalla                 │
 │  · OCR / plantillas      │                   │                          │
 │  · plan humano (tipear,  │   SSH 127.0.0.1   │ xdotool (ratón/teclado)  │
 │    mover) → línea tiempo │──────:2222───────▶│ reproductor de planes    │
 │  · registro JSONL        │                   │ ffmpeg x11grab (vídeo)   │
 └──────────────────────────┘◀── scp .mp4 ──────│ Burp · Firefox · lab     │
                                                └──────────────────────────┘
```

## 1. Montaje único (una vez por máquina)

1. **Anfitrión:** instala VirtualBox, OpenSSH (`ssh`, `scp`), Python 3, Tesseract y ffmpeg
   (comandos por SO en `PORTABILIDAD.md`). `vm_control.py` localiza `VBoxManage` solo.
2. **VM apagada:** `python vm_control.py bootstrap` añade la regla NAT `127.0.0.1:2222 → 22`
   (solo se puede con la VM apagada), crea la clave dedicada `~/.ssh/cutly_vm` y la autoriza:
   - **Camino preferido:** define `VM_GUEST_PASS` con la contraseña **que tú le das** y se instala con
     `VBoxManage guestcontrol`.
   - **Alternativa:** teclea la clave en un terminal del invitado con `keyboardputscancode` (solo letras, con
     el teclado en US). Con tu sesión gráfica ya iniciada.
   - **El agente nunca adivina contraseñas** ni acepta acuerdos legales por ti (EULA de Burp: lo aceptas tú).
3. **Invitado:** `sudo apt install xdotool xclip wmctrl ffmpeg openssh-server` (X11, no Wayland), Guest Additions,
   salvapantallas y bloqueo desactivados, "no molestar". Perfil Firefox `demo` (proxy a Burp, sin
   autocompletado ni tráfico de fondo) y lab en `~/lab/lab_idor.py`.
4. **Comprobar:** `python vm_control.py status` debe mostrar `ssh: sí`, la resolución y la ventana activa.

## 2. Estado de partida: rápido y repetible

- **Reanudar en vez de arrancar:** al terminar de preparar (`prepare`), `vm_control.py suspend` guarda el estado
  (`savestate`; **no es un snapshot ni una copia**: se consume al reanudar). La siguiente sesión hace
  `vm_control.py prepare` y reanuda con Burp y Firefox ya abiertos, sin repetir los diálogos de Burp.
- `prepare --cold` fuerza el arranque desde cero (lab + Burp + Firefox).
- **Resolución del vídeo:** `vm_control.py res 1080 1920` (short vertical) o `res 1920 1080` (16:9) **antes**
  de grabar; no cambiarla a mitad de toma.

## 3. Protocolo de toma (con registro y grabación automáticos)

```bash
python vm_control.py prepare
python vm_control.py take start idor-01          # abre editor/crudo/idor-01.steps.jsonl
python vm_control.py rec start                   # ffmpeg dentro de la VM, cursor incluido
python vm_control.py mark "Acto 1: login legítimo"
python vm_control.py typeurl "http://127.0.0.1:8765/cuenta?id=1001" --in "Mozilla Firefox"
python vm_control.py labcheck "GET /cuenta?id=1001"   # verificación SIN OCR
python vm_control.py mark "Acto 2: Burp y Repeater"
...
python vm_control.py take end                    # deja idor-01.mp4 y escribe idor-01.mapa.md
python ../editor/scripts/short_desde_toma.py idor-01 --titulo Titulo-Con-Gancho   # SHORT 1080x1920 con banda para la cara
```

- **Quién graba:** `rec start` usa la **grabación nativa de VirtualBox en el anfitrión** (`VBoxManage controlvm recording`):
  no toca la VM, no necesita SSH y el cursor del invitado **sale en el vídeo** (medido). Se convierte a MP4 H.264 a 30 fps
  constantes. Alternativa: `rec start --guest` (ffmpeg dentro de la VM). **OBS ya no hace falta.**
  Ojo: `recording videores` lleva la resolución en DOS argumentos (`1920 1012`); con `1920x1012` imprime la ayuda y el
  vídeo sale recortado a 1024×768 (lo hace `vm_control.py` solo).
- **Salida para la Fase 2:** `editor/crudo/<toma>.mp4` + `<toma>.steps.jsonl` + `<toma>.mapa.md`. El mapa da, por
  cada `mark`, el rango en segundos del vídeo (±0,3 s) y los pasos fallidos a rehacer. Se usa tal cual en
  `editor/CLAUDE.md` para decidir cortes.
- **Anuncio al usuario:** "TOMA ÚNICA — no toques la ventana de la VM hasta 'CORTEN'". El usuario sí puede usar
  el resto de su ordenador (la VM tiene su propio ratón y teclado).
- Pacing y entrada humana: doc 04 (regla 0). Todo tecleo y movimiento va por `type`/`typeurl`/`move`/`clicktext`.

## 3b. De la toma al Short, automático
`editor/scripts/short_desde_toma.py TOMA` lee `editor/crudo/TOMA.mp4` + `TOMA.steps.jsonl` y construye
`editor/videos-editados/short_<Titulo>_editado.mp4` (1080×1920@60, **audio mudo**, banda negra superior de **648 px FIJA** para tu
cara, verificada midiendo píxeles). Cada acto (`mark`) se parte en planos de ≤ 8 s que siguen el foco; el foco sale solo del
ratón, de `typeurl` y de `waitfor` (dónde apareció el texto esperado), o a mano con `focus X Y`. Anota además `_cortes.log`.
Después tú pones tu cara y la voz. `demo_idor.py` hace todo el ciclo (ejecutar → grabar → Short).

## 4. Cómo se verifica cada paso (de más a menos fiable)

| Qué | Cómo | Cuándo |
|---|---|---|
| Que el servidor recibió la petición | `labcheck "GET /cuenta?id=1002"` (log del lab) | Siempre que haya un lab propio |
| Que apareció un texto | `waitfor "usuarioB"` (OCR, acepta región con Pillow) | Texto grande y legible |
| Que la pantalla terminó de pintar | `waitstill` | En vez de pausas fijas |
| Botón que el OCR no lee (texto claro sobre color) | `clickimg plantilla.png` (OpenCV) o coordenada vista + verificación | "I Accept", iconos |
| Que el foco es el correcto | `--in "Título"` en `type`/`typeurl` | Siempre que se teclee |
| Selección de texto en Java (Burp) | `selecttext` (copia y compara) | Doble clic en Swing |

Un paso que solo "informa" sin verificar da falsos éxitos: termina siempre con una comprobación que pueda fallar.

## 5. Referencia rápida de comandos
Para conducir una app NUEVA (reconocimiento, reglas aprendidas, fichas): `09-conducir-apps-kali.md`.
**Para una demo de terminal (nmap, ssh, exploits, reverse shells…) sigue la plantilla `10-plantilla-demo-terminal.md`
DESDE EL PRINCIPIO** — condensa 10 iteraciones reales hasta un Short perfecto, para no repetir el mismo camino.
Git Bash convierte rutas `/home/...`: usa rutas relativas al home o `MSYS_NO_PATHCONV=1`.


Ver la cabecera de `herramientas/vm_control.py` (`python vm_control.py` sin argumentos la imprime).

## 6. Estado de lo verificado
Ver [`../../PENDIENTE.md`](../../PENDIENTE.md). Resumen: control, tecleo humano, captura y fiabilidad 10/10 medidos en
macOS/ARM (doc 08). **En Windows/x86 está portado y sin probar de punta a punta** hasta completar el montaje §1.
