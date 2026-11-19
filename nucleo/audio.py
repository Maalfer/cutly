"""Análisis de audio: dónde hay voz y cuánto suena. La energía es "la verdad física": los timestamps de Whisper fallan
50-500 ms y en los silencios inventa texto ("Gracias"), así que todo corte fino se decide con esto.

Ventana estándar: 10 ms (160 muestras a 16 kHz).
  rms  nivel en dB.
  hf   energía de ALTA FRECUENCIA (derivada de la señal) en dB: una sibilante final ("pass") tiene rms bajo pero hf
       alto, así que la palabra acaba donde cae el hf, no donde cae el rms (error real: se comió la "s").
"""
import json
import subprocess

from nucleo.ffmpeg import requerir


def energia(a, muestras=160):
    """(rms, hf) en dB por ventana de `muestras` (160 = 10 ms a 16 kHz) de un array mono float32."""
    import numpy as np
    n = len(a) // muestras
    fr = a[: n * muestras].reshape(n, muestras)
    rms = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    hf = 20 * np.log10(np.sqrt((np.diff(fr, axis=1) ** 2).mean(1)) + 1e-9)
    return rms, hf


def mascara_voz(rms, hf, umbral_rms=-38.0, umbral_hf=-42.0, min_tramas=6):
    """Voz por ventana: rms > umbral_rms o hf > umbral_hf (para no perder sibilantes). Quita rachas de voz de menos de
    `min_tramas` ventanas (con 10 ms: < 60 ms = chasquidos, golpes). Umbrales absolutos medidos en la grabación de cara
    del usuario (micro de escritorio, sin normalizar)."""
    v = (rms > umbral_rms) | (hf > umbral_hf)
    n = len(v)
    i = 0
    while i < n:
        if v[i]:
            j = i
            while j < n and v[j]:
                j += 1
            if j - i < min_tramas:
                v[i:j] = False
            i = j
        else:
            i += 1
    return v


def medir_sonoridad(path, filtro="loudnorm=print_format=json"):
    """Mide la sonoridad (LUFS integrados, pico real, LRA...) con loudnorm. Devuelve su JSON (input_i, input_tp...)."""
    med = subprocess.run([requerir("ffmpeg"), "-v", "info", "-i", path, "-vn", "-af", filtro, "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    return json.loads(med[med.rindex("{"):med.rindex("}") + 1])


def filtro_normalizar(medida, lufs, tp=-1, lra=11):
    """loudnorm LINEAL de segunda pasada (misma ganancia en todo el vídeo, sin compresión) a `lufs` con techo `tp`."""
    m = medida
    return (f"loudnorm=I={lufs}:TP={tp}:LRA={lra}:linear=true:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}")
