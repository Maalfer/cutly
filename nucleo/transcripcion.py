"""Transcripción con timestamps por palabra (faster-whisper) con la configuración MEDIDA para este proyecto
(editor/comun/BENCHMARK-WHISPER.md), y sus formatos de archivo.

Decisiones (todas medidas, no por costumbre):
  - Modelo por defecto `large-v3-turbo`: en CPU tarda la mitad que `large-v3`, usa ~40 % menos RAM y en el audio de
    prueba se equivocó MENOS (WER 1,2 % frente a 2,4 %). `large-v3` queda como SEGUNDA OPINIÓN para un tramo dudoso.
  - `vad_filter=True`: sin él, Whisper inventa "Gracias" / "Gracias por ver el vídeo" en los silencios y se salta
    trozos con voz real (medido: la pasada sin VAD perdió ~30 s de narración). Es la mejora que más importa.
  - `condition_on_previous_text=False`: evita que una alucinación se arrastre al resto del archivo (equivale a -mc 0).
    Excepción: el modo SUBTÍTULOS (solo sobre un Short final, sin silencios) encadena contexto para puntuar bien.
  - El audio se decodifica con ffmpeg (nucleo.medios.audio_mono): el PyAV interno de faster-whisper falla en algunas
    instalaciones de Windows ("open() got an unexpected keyword argument 'metadata_errors'").
  - Los timestamps de CUALQUIER modelo fallan entre 50 y 500 ms en algunas palabras: NO cortes directamente con
    ellos. Afina cada corte con nucleo.audio (energía a 10 ms) y verifica re-transcribiendo el empalme.

Formato JSON (lo leen subtitulos, analizar_fusion...):
    {"modelo": str, "dispositivo": str, "segmentos": [{"start", "end", "text", "words": [[ini, fin, palabra], ...]}]}
"""
import os

from nucleo.archivos import escribir_json, leer_json
from nucleo.rutas import GLOSARIO

MODELO_DEFECTO = "large-v3-turbo"


def prompt_subtitulos(glosario=GLOSARIO):
    """Texto de contexto para el modo subtítulos: frases BIEN PUNTUADAS (Whisper imita la puntuación y las mayúsculas
    del contexto) + el vocabulario técnico del glosario escrito como debe salir. Genérico a propósito: nombrar
    comandos o puertos de un vídeo concreto sesga a Whisper hacia ellos en cualquier otro vídeo."""
    terminos = []
    try:
        for _, bueno in leer_json(glosario)["reemplazos"]:
            if bueno not in terminos:
                terminos.append(bueno)
    except (OSError, ValueError, KeyError):
        pass
    return ("Hola, ¿qué tal? Hoy os enseño una técnica de hacking ético, paso a paso. Primero miro qué tiene la máquina; "
            "después, lanzo el ataque y, por último, compruebo que funciona." +
            (" Vocabulario: " + ", ".join(terminos) + "." if terminos else ""))


def dispositivo_auto():
    """cuda si hay GPU NVIDIA utilizable; si no, cpu (faster-whisper no usa GPUs AMD: ver BENCHMARK-WHISPER.md)."""
    try:
        import ctranslate2
        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:
        return "cpu"


def transcribir(audio, modelo=MODELO_DEFECTO, idioma="es", dispositivo="auto", subtitulos=False, al_segmento=None):
    """Transcribe un array mono de 16 kHz. Devuelve (segmentos, dispositivo). `al_segmento(seg)` se llama con cada
    segmento según sale (para ir mostrando el progreso)."""
    from faster_whisper import WhisperModel
    dev = dispositivo_auto() if dispositivo == "auto" else dispositivo
    m = WhisperModel(modelo, device=dev, compute_type="int8" if dev == "cpu" else "float16")
    segs, _ = m.transcribe(audio, language=idioma, word_timestamps=True, vad_filter=True,
                           condition_on_previous_text=subtitulos,
                           initial_prompt=prompt_subtitulos() if subtitulos else None, beam_size=5)
    out = []
    for s in segs:
        seg = {"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(),
               "words": [[round(w.start, 3), round(w.end, 3), w.word.strip()] for w in s.words]}
        out.append(seg)
        if al_segmento:
            al_segmento(seg)
    return out, dev


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def escribir(base, segmentos, modelo, dispositivo):
    """BASE.json + BASE.srt + BASE.txt (la línea N del .txt es el segmento N del .srt)."""
    escribir_json(base + ".json", {"modelo": modelo, "dispositivo": dispositivo, "segmentos": segmentos})
    with open(base + ".srt", "w", encoding="utf-8") as f:
        for i, s in enumerate(segmentos, 1):
            f.write(f"{i}\n{srt_time(s['start'])} --> {srt_time(s['end'])}\n{s['text']}\n\n")
    with open(base + ".txt", "w", encoding="utf-8") as f:
        f.write("\n".join(s["text"] for s in segmentos) + "\n")


def ruta_por_defecto(entrada):
    """<entrada sin extensión>_transcripcion (junto al vídeo)."""
    return os.path.splitext(entrada)[0] + "_transcripcion"


def cargar_segmentos(path):
    d = leer_json(path)
    return d["segmentos"] if isinstance(d, dict) else d


def palabras(segmentos):
    """[[ini, fin, palabra], ...] de todos los segmentos (sin palabras vacías)."""
    out = []
    for s in segmentos:
        for w in s["words"]:
            t = w[2].strip()
            if t:
                out.append([float(w[0]), float(w[1]), t])
    return out
