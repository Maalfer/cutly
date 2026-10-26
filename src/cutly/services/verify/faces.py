"""Detección de caras en fotogramas del proxy (OpenCV, cascada Haar frontal; sin modelos que descargar)."""

import subprocess

from cutly.services.verify.geometry import Rect4


def detect_faces(path: str, t: float, width: int = 480) -> list[Rect4]:
    """Caras (x0, y0, x1, y1 normalizados al original) en el instante `t` de `path`. [] si no hay o no hay OpenCV."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", path, "-frames:v", "1",
           "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "-"]  # fmt: skip
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    if r.returncode != 0 or not r.stdout:
        return []
    cv2.setNumThreads(1)
    img = cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return []
    h, w = img.shape
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    found = cascade.detectMultiScale(
        cv2.equalizeHist(img), scaleFactor=1.1, minNeighbors=6, minSize=(int(w * 0.08), int(w * 0.08))
    )
    return [(x / w, y / h, (x + fw) / w, (y + fh) / h) for x, y, fw, fh in found]
