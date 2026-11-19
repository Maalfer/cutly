"""Canal con el invitado: SSH y scp (en BYTES: en Windows text=True convertiría los \n en \r\n y bash fallaría)."""
import subprocess

from .config import KEY, PORT, USER, die


def _ssh_cmd(extra=None):
    return ["ssh", "-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=accept-new", "-p", PORT, f"{USER}@127.0.0.1"] + (extra or [])


def ssh(script, capture=False, check=True, timeout=25):
    # LC_ALL=C.UTF-8 es IMPRESCINDIBLE: sin locale UTF-8, xdotool descarta los no ASCII (doc 08 nº 38).
    # El script va en BYTES con \n: en Windows, text=True lo convertiría a \r\n y bash fallaría.
    # `timeout` es OBLIGATORIO: subprocess.run espera a que el REMOTO cierre stdout/stderr; un proceso
    # lanzado en segundo plano que por una condición de carrera no se desengancha del todo (incluso con
    # setsid) deja el canal SSH colgado para siempre y sin avisar (medido: 3+ min sin CPU, bloqueado en
    # I/O). Mejor fallar rápido y de forma diagnosticable que colgar el guion en silencio.
    try:
        r = subprocess.run(_ssh_cmd(["export DISPLAY=:0 LC_ALL=C.UTF-8 LANG=C.UTF-8; bash -s"]),
                           input=script.replace("\r\n", "\n").encode("utf-8"), capture_output=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        die(f"ssh TIMEOUT tras {timeout}s (el canal no cerró; ¿algo en segundo plano sigue enganchado al "
            f"pipe?) — script:\n{script[:200]}")
    out = r.stdout.decode("utf-8", "replace").strip()
    err = r.stderr.decode("utf-8", "replace").strip()
    if r.returncode and check:
        die(f"ssh falló: {err or out}")
    return out if capture else (r.returncode == 0)


def ssh_ok():
    return subprocess.run(_ssh_cmd(["true"]), capture_output=True).returncode == 0


def scp_from(remote, local):
    r = subprocess.run(["scp", "-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-P", PORT,
                        f"{USER}@127.0.0.1:{remote}", local], capture_output=True)
    return r.returncode == 0


def scp_to(local, remote):
    r = subprocess.run(["scp", "-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-P", PORT,
                        local, f"{USER}@127.0.0.1:{remote}"], capture_output=True)
    return r.returncode == 0
