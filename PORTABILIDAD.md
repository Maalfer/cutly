# 🖥️ Portabilidad — misma metodología en macOS, Windows y Linux

> La metodología de `cutly` no depende de ningún sistema operativo concreto. Esta guía es la
> **referencia central** para usarla en cualquier máquina. El resto de documentos describen los
> comandos tal cual se usaron en la máquina de desarrollo (**macOS**); aquí tienes el equivalente
> para **Windows** y **Linux**.
>
> Regla general: **la Fase 2 (editar) es casi idéntica en todos lados** (mismas herramientas).
> **La Fase 1 (controlar el ordenador) es la que más cambia** entre sistemas — tabla de abajo.

---

## 0. Convenciones que valen en cualquier sistema

- **La carpeta `cutly/` puede vivir donde quieras.** Las rutas tipo `~/Desktop/cutly/...` que
  aparecen en los documentos son **ejemplos de la máquina macOS**. Sustituye por la ruta real de
  tu `cutly` en cada sistema. Dentro del repo, usa siempre rutas **relativas** cuando puedas.
- **Home / carpeta personal:** macOS y Linux → `~` (`$HOME`). Windows → `%USERPROFILE%`
  (PowerShell: `$env:USERPROFILE`; en Git Bash/WSL `~` también funciona).
- **Carpeta de modelos Whisper:** `~/.whisper-models` en macOS/Linux; `%USERPROFILE%\.whisper-models`
  en Windows. Los scripts en Python usan `os.path.expanduser("~")`, que resuelve bien en los tres.
- **Temporal / scratchpad:** `/tmp` o `$TMPDIR` (macOS/Linux); `%TEMP%` (Windows).
- **Papelera (para la regla "si `_cortes.log` falta, míralo antes de recrear"):**
  macOS `~/.Trash` · Linux `~/.local/share/Trash/files` · Windows Papelera de reciclaje
  (sin ruta fija; mírala desde el Explorador).
- **Scripts `.sh`:** nativos en macOS/Linux. En **Windows** ejecútalos con **Git Bash** o **WSL**
  (ambos traen `bash`, `curl`, `ffmpeg`…), o replica el comando a mano. El builder de shorts está
  en **Python** (`editor/scripts/construir_short.py`) justamente para ser portable sin shell.

---

## 1. FASE 2 — Editar (ffmpeg + whisper.cpp + yt-dlp + python): casi igual en todos lados

Las herramientas son las mismas; solo cambia **cómo se instalan** y la **aceleración por GPU**.

### Instalación por sistema

| Herramienta | macOS (Homebrew) | Windows | Linux (Debian/Ubuntu · Fedora · Arch) |
|---|---|---|---|
| **ffmpeg/ffprobe** | `brew install ffmpeg` | `winget install Gyan.FFmpeg` (o `choco install ffmpeg` / `scoop install ffmpeg`) | `apt install ffmpeg` · `dnf install ffmpeg` · `pacman -S ffmpeg` |
| **python3** | `brew install python` | `winget install Python.Python.3` | `apt install python3` · `dnf install python3` · `pacman -S python` |
| **yt-dlp** | `brew install yt-dlp` | `winget install yt-dlp.yt-dlp` (o `pipx install yt-dlp`) | `pipx install yt-dlp` · `pacman -S yt-dlp` |
| **whisper.cpp** | `brew install whisper-cpp` (trae Metal) | compilar desde fuente (abajo) o binarios de releases | compilar desde fuente (abajo) |

### whisper.cpp con GPU (compilar desde fuente si no hay paquete)

```bash
git clone https://github.com/ggml-org/whisper.cpp && cd whisper.cpp
# Elige el backend según tu hardware:
#   Apple Silicon (macOS):   -DGGML_METAL=1     (por defecto en mac)
#   NVIDIA (Win/Linux):      -DGGML_CUDA=1
#   AMD/Intel (Win/Linux):   -DGGML_VULKAN=1
#   Sin GPU (cualquiera):    (nada, usa CPU)
cmake -B build -DGGML_CUDA=1          # <- ajusta el flag a tu caso
cmake --build build -j --config Release
# Binario resultante: build/bin/whisper-cli  (en Windows: build\bin\Release\whisper-cli.exe)
```

> El binario puede llamarse `whisper-cli` (reciente) o `main` (antiguo). Ajusta el nombre en los
> scripts si hace falta. En los documentos aparece `whisper-cli` (el de Homebrew en mac).

### ffmpeg y GPU (opcional, para acelerar el render)

Por defecto los scripts usan `libx264` (CPU, idéntico resultado en todos lados y lo más
compatible). Si quieres acelerar el codificado con la GPU, cambia el códec:

| GPU | Códec ffmpeg | Nota |
|---|---|---|
| Apple Silicon | `-c:v h264_videotoolbox` | macOS |
| NVIDIA | `-c:v h264_nvenc` | Win/Linux |
| AMD (Win) / VAAPI (Linux) | `-c:v h264_amf` / `-c:v h264_vaapi` | |

Para **máxima calidad y portabilidad**, deja `libx264 -preset slow` (lo documentado). Los
encoders de GPU son más rápidos pero algo menos eficientes a igual bitrate.

### Lo que NO cambia en la Fase 2

- Todos los filtros de ffmpeg (`crop`, `scale`, `pad`, `concat`, `trim`, `afade`, `silencedetect`…)
  son **idénticos** en los tres sistemas.
- La lógica de `construir_short.py`, `construir_clip.sh`, el flujo de transcripción y verificación,
  y la metodología de `CLAUDE.md` / `METODOLOGIA-SHORTS.md` son **las mismas**. Solo cambian las
  rutas y la forma de invocar el binario.

---

## 2. FASE 1 — Controlar el ordenador: aquí está la diferencia real

La Fase 1 (la IA mueve cursor/teclado/ventanas y "ve" la pantalla con OCR) usa APIs del sistema,
así que **cada SO tiene sus herramientas**. Esta es la tabla de equivalencias. La columna macOS es
la que está detallada en `crear-shorts/METODOLOGIA/`; las otras dos son su equivalente directo.

| Capacidad | macOS | Windows | Linux · X11 | Linux · Wayland |
|---|---|---|---|---|
| **Mover / clicar cursor** | `cliclick m:x,y` / `c:x,y` | AutoHotkey `Click x,y` · `nircmd sendmouse left click` · PowerShell+user32 | `xdotool mousemove x y click 1` | `ydotool mousemove x y` + `ydotool click` |
| **Teclear texto / combinaciones** | `osascript … keystroke` | AutoHotkey `Send "txt"` · PowerShell `[System.Windows.Forms.SendKeys]::SendWait()` | `xdotool type "txt"` / `xdotool key ctrl+v` | `ydotool type "txt"` / `ydotool key` |
| **Posición del cursor** | `mousepos` (Swift) | PowerShell `[System.Windows.Forms.Cursor]::Position` | `xdotool getmouselocation` | compositor (p. ej. `swaymsg`) |
| **Captura de pantalla** | `screencapture -x out.png` | `nircmd savescreenshot out.png` · PowerShell `CopyFromScreen` | `scrot out.png` · `maim out.png` | `grim out.png` |
| **OCR con coordenadas** | `ocr.swift` (Vision) | **Tesseract** `tesseract in.png out tsv` · o WinRT `Windows.Media.Ocr` | **Tesseract** `tesseract in.png out tsv` | Tesseract (igual) |
| **Abrir app / archivo** | `open -a App f` | `Start-Process App` · `start f` | `xdg-open f` / binario | `xdg-open f` |
| **Posicionar ventana** | AppleScript `set bounds` | `nircmd win move title "X" x y w h` · PowerShell+`MoveWindow` | `wmctrl -r :ACTIVE: -e 0,x,y,w,h` · `xdotool windowmove` | limitado (depende del compositor) |
| **Ocultar / minimizar ventana** | `set visible to false` | `nircmd win hide title "X"` · `ShowWindow` | `xdotool windowminimize` · `wmctrl` | limitado |
| **Enumerar ventanas** | System Events (AppleScript) | PowerShell `Get-Process \| ? MainWindowTitle` · `EnumWindows` | `wmctrl -l` · `xdotool search --name` | limitado |
| **Portapapeles** | `pbcopy` / `pbpaste` | `Set-Clipboard` / `Get-Clipboard` · `… \| clip` | `xclip -selection clipboard` · `xsel -b` | `wl-copy` / `wl-paste` |
| **Permiso para automatizar** | TCC → **Accesibilidad** (obligatorio) | normalmente sin permiso extra (ojo UAC/apps elevadas) | X11 lo permite de serie | **restringido**: input por `uinput` (ydotool + daemon), captura por portal |

### Instalación del kit de control por sistema

```text
Windows  : AutoHotkey v2 (autohotkey.com)  +  nircmd (nirsoft.net)  +  Tesseract (UB-Mannheim build)
           — o todo con PowerShell (cursor, portapapeles, captura nativos; clic/tecla vía user32 o AHK)
Linux X11: sudo apt install xdotool wmctrl scrot xclip tesseract-ocr        (o dnf / pacman equivalentes)
Linux Wayland: ydotool (+ ydotoold, acceso a /dev/uinput)  +  grim  +  wl-clipboard  +  tesseract-ocr
macOS    : cliclick (brew) + OCR/mousepos propios (Swift+Vision) + permiso de Accesibilidad  (ver crear-shorts/)
```

### Notas por sistema (importantes)

- **Windows:** la pila más cómoda para un agente es **AutoHotkey v2** (clic, teclado y mover
  ventanas en una sola herramienta) + **PowerShell** (portapapeles, captura, posición de cursor) +
  **Tesseract** para OCR. `nircmd` cubre captura y ventanas sin programar. No suele hacer falta
  permiso especial salvo que la ventana objetivo corra **elevada** (como admin): entonces el
  automatizador también debe ir elevado.
- **Linux X11** es el entorno **más parecido a macOS** para esto: `xdotool` + `wmctrl` + `scrot` +
  `xclip` + `tesseract` cubren todo con comandos simples. Es la opción recomendada en Linux para
  grabar demos.
- **Linux Wayland** es el **más restrictivo** por seguridad: el input sintético global necesita
  `ydotool` con su daemon y acceso a `/dev/uinput`, y la captura va por `grim`/portales. Si te
  complica, **inicia sesión en un escritorio X11** para grabar la demo y vuelve a Wayland después.

### OCR con coordenadas en Tesseract (equivalente al `ocr.swift` de macOS)

El OCR de macOS devuelve texto + caja `[x,y WxH]`. Con Tesseract se obtiene lo mismo con la salida
TSV (columnas `left top width height` + `text`):

```bash
tesseract captura.png salida --oem 1 --psm 11 -l spa+eng tsv
# salida.tsv: filtra conf>0 y lee left/top/width/height/text para localizar un botón y clicar su centro.
```

> Recuerda el factor de escala Retina/HiDPI: si capturas a resolución física y el clic va en puntos
> lógicos, divide las coordenadas por el factor de escala de la pantalla (en macOS Retina = 2;
> en Windows/Linux depende del "scale"/DPI configurado). Verifica siempre con un clic de prueba.

---

## 3. Resumen: qué tocar al cambiar de sistema

1. **Instala** las herramientas de tu SO (tablas de arriba).
2. **Ajusta las rutas** `~/Desktop/cutly/...` a donde tengas `cutly` (o usa rutas relativas).
3. **Fase 2 (editar):** funciona igual; solo cambia el nombre/ruta del binario de whisper y, si
   quieres, el códec de GPU. Los scripts `.sh` → Git Bash/WSL en Windows; el builder de shorts es
   Python y va en todos lados.
4. **Fase 1 (controlar):** sustituye `cliclick`/`osascript`/`ocr`/`screencapture` por el
   equivalente de tu SO (tabla de la sección 2). La *metodología* (verificar cada acción con OCR,
   pacing cinematográfico, gestión de z-order, toma única sin tocar) **es idéntica**; solo cambian
   los comandos.
