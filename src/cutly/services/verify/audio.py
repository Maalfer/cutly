"""Medición de audio del proyecto: volumen integrado, pico y silencios, en tiempo del clip resultante."""

import re
import subprocess
from pathlib import Path

from cutly.schema.project import ProjectDoc
from cutly.services.render.graph import MediaInfo, audio_clip_fragments, audio_join, safe_path, user_audio_chain
from cutly.services.render.graph import f as fnum

SILENCE_DB = -38
SILENCE_MIN = 0.6


def build_stats_command(doc: ProjectDoc, media: MediaInfo, workdir: Path) -> list[str]:
    workdir.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    for c in doc.timeline:
        inputs += ["-vn", "-ss", fnum(c.source_in), "-t", fnum(c.source_out - c.source_in), "-i", safe_path(media.path)]
    g = audio_clip_fragments(doc, media)
    g += audio_join(doc)
    chain = [
        *user_audio_chain(doc),
        "ebur128=peak=true:framelog=quiet",
        f"silencedetect=n={SILENCE_DB}dB:d={SILENCE_MIN}",
    ]
    g.append(f"[ac]{','.join(chain)}[am]")
    gf = workdir / "stats.txt"
    gf.write_text(";\n".join(g), encoding="utf-8")
    return ["ffmpeg", "-nostdin", "-hide_banner", "-threads", "1", "-filter_complex_threads", "1", *inputs,
            "-filter_complex_script", safe_path(gf), "-map", "[am]", "-f", "null", "-"]  # fmt: skip


def parse_stats(stderr: str, duration: float, target_lufs: float, true_peak_limit: float) -> dict:
    def last(pattern: str) -> float | None:
        m = re.findall(pattern, stderr)
        return float(m[-1]) if m else None

    lufs = last(r"I:\s+(-?\d+(?:\.\d+)?)\s+LUFS")
    lra = last(r"LRA:\s+(-?\d+(?:\.\d+)?)\s+LU")
    peak = last(r"Peak:\s+(-?\d+(?:\.\d+)?)\s+dBFS")
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?\d+(?:\.\d+)?)", stderr)]
    ends = [
        (float(a), float(b))
        for a, b in re.findall(r"silence_end:\s*(-?\d+(?:\.\d+)?)\s*\|\s*silence_duration:\s*(-?\d+(?:\.\d+)?)", stderr)
    ]
    silences = [
        {"start": round(max(s, 0), 2), "end": round(e, 2), "duration": round(d, 2)}
        for s, (e, d) in zip(starts, ends, strict=False)
    ]
    if len(starts) > len(ends):  # silencio que llega hasta el final
        s = max(starts[-1], 0)
        silences.append({"start": round(s, 2), "end": round(duration, 2), "duration": round(duration - s, 2)})
    return {
        "integrated_lufs": lufs, "loudness_range": lra, "true_peak_db": peak, "target_lufs": target_lufs,
        "true_peak_limit_db": true_peak_limit, "silences": silences, "duration": round(duration, 2),
    }  # fmt: skip


def measure(doc: ProjectDoc, media: MediaInfo, workdir: Path, timeout: float = 180) -> dict:
    if not media.has_audio:
        return {"has_audio": False, "silences": [], "duration": round(doc.duration, 2)}
    r = subprocess.run(build_stats_command(doc, media, workdir), capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg no pudo medir el audio: {r.stderr[-300:]}")
    return {"has_audio": True, **parse_stats(r.stderr, doc.duration, doc.audio.target_lufs, doc.audio.true_peak)}
