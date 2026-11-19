"""Leer vídeo y audio con ffprobe/ffmpeg (sin escribir nada)."""
import json
import subprocess

from nucleo.ffmpeg import requerir


def info(path):
    """Streams (tipo, tamaño, fps, Hz) y duración, como JSON de ffprobe."""
    out = subprocess.run([requerir("ffprobe"), "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,r_frame_rate,sample_rate:format=duration", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def probe_video(path):
    """(ancho, alto, duración) del primer stream de vídeo."""
    out = subprocess.run([requerir("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", path], capture_output=True, text=True).stdout
    d = json.loads(out)
    return d["streams"][0]["width"], d["streams"][0]["height"], float(d["format"]["duration"])


def duracion(path):
    return float(subprocess.run([requerir("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 path], capture_output=True, text=True, check=True).stdout.strip())


def audio_mono(path, hz=16000):
    """Audio mono como array float32 en [-1, 1] (decodificado por ffmpeg: evita el PyAV de faster-whisper, que falla
    en algunas instalaciones de Windows)."""
    import numpy as np
    raw = subprocess.run([requerir("ffmpeg"), "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(hz), "-f", "s16le",
                          "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768


def fotogramas_gris(path, fps, crop, scale):
    """(n, h, w) uint8: recorte crop=(w,h,x,y) escalado a scale=(w,h), a `fps` fotogramas por segundo."""
    import numpy as np
    cw, ch, cx, cy = crop
    w, h = scale
    raw = subprocess.run([requerir("ffmpeg"), "-v", "error", "-i", path, "-vf",
                          f"fps={fps},crop={cw}:{ch}:{cx}:{cy},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, h, w)


def fotograma_gris(path, t, ancho=1080, alto=1920):
    """Un fotograma completo en gris (alto, ancho) en el instante t."""
    import numpy as np
    raw = subprocess.run([requerir("ffmpeg"), "-v", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1", "-vf",
                          "format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(alto, ancho)
