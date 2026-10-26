"""Ejecuta procesos externos con timeout, progreso y cancelación (sin shell)."""

import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable

from cutly.config import get_settings


class JobCancelled(Exception):
    pass


class ProcessError(RuntimeError):
    pass


def _with_nice(cmd: list[str]) -> list[str]:
    n = get_settings().ffmpeg_nice
    if n and shutil.which("nice"):
        return ["nice", "-n", str(n), *cmd]
    return cmd


def _stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def run_ffmpeg(
    cmd: list[str],
    *,
    duration: float | None,
    timeout: float,
    cancelled: Callable[[], bool],
    on_progress: Callable[[float], None] | None = None,
) -> str:
    """`cmd` debe llevar `-progress pipe:1` para tener progreso (= out_time / duration). Devuelve el stderr."""
    with tempfile.TemporaryFile("w+") as err:
        proc = subprocess.Popen(
            _with_nice(cmd), stdout=subprocess.PIPE, stderr=err, text=True, stdin=subprocess.DEVNULL
        )
        state = {"t": 0.0}

        def reader():
            for line in proc.stdout:  # type: ignore[union-attr]
                if line.startswith("out_time_us="):
                    try:
                        state["t"] = int(line.split("=")[1]) / 1e6
                    except ValueError:
                        pass

        threading.Thread(target=reader, daemon=True).start()
        start = time.monotonic()
        while True:
            try:
                rc = proc.wait(0.5)
                break
            except subprocess.TimeoutExpired:
                pass
            if cancelled():
                _stop(proc)
                raise JobCancelled()
            if time.monotonic() - start > timeout:
                _stop(proc)
                raise ProcessError(f"ffmpeg superó el timeout de {int(timeout)} s")
            if on_progress and duration:
                on_progress(min(state["t"] / duration, 0.99))
        err.seek(0)
        text = err.read()
        if rc != 0:
            raise ProcessError(f"ffmpeg falló (código {rc}): {text[-600:].strip()}")
        return text


def run_ffmpeg_pipe(
    cmd: list[str],
    *,
    on_chunk: Callable[[bytes], None],
    expected_bytes: int | None,
    timeout: float,
    cancelled: Callable[[], bool],
    on_progress: Callable[[float], None] | None = None,
    chunk_size: int = 1 << 20,
) -> None:
    """Lee stdout de ffmpeg por bloques (p. ej. audio PCM para los peaks)."""
    with tempfile.TemporaryFile("w+") as err:
        proc = subprocess.Popen(_with_nice(cmd), stdout=subprocess.PIPE, stderr=err, stdin=subprocess.DEVNULL)
        start, got = time.monotonic(), 0
        try:
            while True:
                data = proc.stdout.read(chunk_size)  # type: ignore[union-attr]
                if not data:
                    break
                got += len(data)
                on_chunk(data)
                if cancelled():
                    raise JobCancelled()
                if time.monotonic() - start > timeout:
                    raise ProcessError(f"ffmpeg superó el timeout de {int(timeout)} s")
                if on_progress and expected_bytes:
                    on_progress(min(got / expected_bytes, 0.99))
        except BaseException:
            _stop(proc)
            raise
        rc = proc.wait()
        if rc != 0:
            err.seek(0)
            raise ProcessError(f"ffmpeg falló (código {rc}): {err.read()[-600:].strip()}")
