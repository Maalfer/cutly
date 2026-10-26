"""Metadatos con ffprobe."""

import json
import subprocess
from pathlib import Path


class ProbeError(RuntimeError):
    pass


def probe(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]  # fmt: skip
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True).stdout
    except subprocess.CalledProcessError as e:
        raise ProbeError(f"ffprobe no puede leer el archivo: {e.stderr.strip()[:300]}") from e
    except subprocess.TimeoutExpired as e:
        raise ProbeError("ffprobe tardó demasiado leyendo el archivo") from e
    data = json.loads(out)
    video = next((s for s in data.get("streams", []) if s["codec_type"] == "video"), None)
    audio = next((s for s in data.get("streams", []) if s["codec_type"] == "audio"), None)
    if video is None:
        raise ProbeError("El archivo no contiene pista de vídeo")
    num, _, den = video.get("avg_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    return {
        "duration": float(data["format"].get("duration") or video.get("duration") or 0),
        "width": video["width"],
        "height": video["height"],
        "fps": round(fps, 3),
        "video_codec": video["codec_name"],
        "audio_codec": audio["codec_name"] if audio else None,
        "has_audio": audio is not None,
        "bit_rate": int(data["format"].get("bit_rate") or 0),
    }
