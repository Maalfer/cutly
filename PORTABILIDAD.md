# 🖥️ Portabilidad — Windows, macOS y Linux como anfitrión

> Las demos se graban **dentro de una VM** (ver `crear-shorts/METODOLOGIA/00-empezar-aqui-vm.md`), así que el
> control (xdotool, X11) es el mismo en cualquier anfitrión. Lo único que depende del SO es **instalar las
> herramientas del anfitrión** y unos pocos detalles de rutas. Esta guía lo cubre.

## 0. Convenciones
- `cutly/` puede vivir donde quieras; los scripts calculan su ruta (`REPO`) a partir de su ubicación.
- Home: macOS/Linux `~`; Windows `%USERPROFILE%` (PowerShell `$env:USERPROFILE`; Git Bash `~`).
- Whisper: `~/.whisper-models` (Windows: `%USERPROFILE%\.whisper-models`). Los `.py` usan `expanduser`.
- Temporales: `vm_control.py` usa `tempfile.gettempdir()` (Windows `%TEMP%`, resto `/tmp`).
- Scripts `.sh` del editor: en Windows, con **Git Bash** o **WSL**. Lo demás es Python y va en todos lados.

---

## 1. Anfitrión WINDOWS (caso real de esta máquina)

### 1.1 Instalación (PowerShell)
```powershell
winget install Oracle.VirtualBox                     # si no lo tienes
winget install Python.Python.3.13
winget install UB-Mannheim.TesseractOCR              # OCR (Windows no tiene Vision)
winget install Gyan.FFmpeg                           # Fase 2 y miniaturas
pip install pillow opencv-python                     # opcionales: OCR por región y clickimg
# OpenSSH cliente: viene con Windows 10/11 (Configuración > Aplicaciones > Funciones opcionales)
```
Abre una terminal **nueva** tras instalar para que el PATH se refresque.

### 1.2 Rutas y detalles propios de Windows
| Cosa | Dónde está / qué hacer |
|---|---|
| `VBoxManage.exe` | `C:\Program Files\Oracle\VirtualBox\` — **no está en el PATH**. `vm_control.py` lo localiza solo; para otros scripts: `$env:VBOXMANAGE="C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"` |
| Tesseract | `C:\Program Files\Tesseract-OCR\tesseract.exe` (el script lo encuentra aunque no esté en el PATH) |
| Clave SSH de la VM | `%USERPROFILE%\.ssh\cutly_vm` (`ssh-keygen` ajusta los permisos; no la muevas a otra carpeta) |
| Python | usa `python`, no `python3` (en Windows `python3` suele ser un acceso directo de la Store) |
| Saltos de línea | `vm_control.py` envía los scripts por SSH en **bytes con `\n`**; con `text=True` Windows los convertiría en `\r\n` y bash fallaría (corregido) |
| `ControlMaster` de SSH | **No existe en OpenSSH para Windows**: por eso cada plan largo va en **una sola conexión** (reproductor de planes) |
| Codificación de consola | Si ves `?` en tildes en la salida, es solo la consola (`$env:PYTHONUTF8=1`); el texto tecleado en la VM va por JSON y no se ve afectado |
| Antivirus / Defender | Puede ralentizar `ssh`/`scp` la primera vez; no afecta al resultado |

### 1.3 Comprobación en 1 minuto
```powershell
python crear-shorts\herramientas\vm_control.py status   # VM, SSH, pantalla, ventana activa
tesseract --version; ffmpeg -version | Select-Object -First 1
```
Si `status` dice `ssh: no`: falta el montaje único (`bootstrap`, doc 00 §1) o la regla NAT.

### 1.4 Restricciones de la VM en esta máquina
La VM `kali` aquí es **x86-64 (Debian 64-bit)**, no ARM64 como en la máquina donde se desarrolló: las
instrucciones de Burp/Java para x86 son las estándar. La regla NAT `ssh,tcp,127.0.0.1,2222,,22` se añade con la VM
**apagada** (`bootstrap` lo hace).

---

## 2. Anfitrión macOS
```bash
brew install --cask virtualbox        # (Apple Silicon: VirtualBox 7.1+ con invitado ARM64)
brew install python tesseract ffmpeg
pip3 install pillow opencv-python     # opcionales
```
`VBoxManage` queda en el PATH. Si existe `~/Desktop/ctrl-kit/ocr` (Vision), `vm_control.py` lo prefiere a Tesseract
(`VM_OCR=tesseract` lo desactiva). Vision lee botones de interfaz que Tesseract no encuentra.

## 3. Anfitrión Linux
```bash
sudo apt install virtualbox openssh-client python3 python3-pip tesseract-ocr ffmpeg   # (dnf/pacman equivalentes)
pip3 install pillow opencv-python
```
`VBoxManage` queda en el PATH. Si el anfitrión es Wayland no importa: lo que debe ser **X11 es el invitado**.

---

## 4. Fase 2 — Editar (ffmpeg + whisper.cpp + yt-dlp): casi idéntica en todos lados

| Herramienta | macOS | Windows | Linux |
|---|---|---|---|
| ffmpeg/ffprobe | `brew install ffmpeg` | `winget install Gyan.FFmpeg` | `apt install ffmpeg` |
| python3 | `brew install python` | `winget install Python.Python.3.13` | `apt install python3` |
| yt-dlp | `brew install yt-dlp` | `winget install yt-dlp.yt-dlp` | `pipx install yt-dlp` |
| whisper.cpp | `brew install whisper-cpp` (Metal) | compilar o binarios de releases | compilar |

```bash
git clone https://github.com/ggml-org/whisper.cpp && cd whisper.cpp
# GPU: Apple -DGGML_METAL=1 · NVIDIA -DGGML_CUDA=1 · AMD/Intel -DGGML_VULKAN=1 · sin GPU: nada
cmake -B build -DGGML_CUDA=1 && cmake --build build -j --config Release
# Binario: build/bin/whisper-cli  (Windows: build\bin\Release\whisper-cli.exe)
```
El binario puede llamarse `whisper-cli` o `main`. Por defecto los scripts usan `libx264` (CPU, igual en todos
lados). Aceleración opcional: `h264_videotoolbox` (Apple), `h264_nvenc` (NVIDIA), `h264_amf` (AMD, Windows),
`h264_vaapi` (Linux). Los filtros de ffmpeg y la lógica de `construir_short.py` son idénticos en los tres SO.

---

## 5. Qué ya NO se usa
El control del ordenador anfitrión (`cliclick`, AppleScript, AutoHotkey, `wmctrl`, `ydotool`, Vision como único OCR,
gate anti-solape sobre ventanas del anfitrión…) **se retiró**: todo ocurre dentro de la VM. Los fallos históricos de ese
enfoque siguen documentados en `crear-shorts/METODOLOGIA/07-auditoria-de-pruebas.md` como lecciones, no como
instrucciones.
