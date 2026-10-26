"""Coherencia del render: fotogramas renderizados frente a imágenes de referencia (SSIM con umbral).

Regenerar las referencias tras un cambio visual intencionado: `UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py`.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

from cutly.schema.project import ProjectDoc
from cutly.services.render.fonts import merged_fonts_dir
from cutly.services.render.graph import MediaInfo
from cutly.services.verify.frames import render_frames

GOLDEN = Path(__file__).parent / "golden"
SCALE = 0.25  # 270x480
THRESHOLD = 0.93
WORDS = [
    {"w": w, "start": 0.2 + i * 0.35, "end": 0.5 + i * 0.35}
    for i, w in enumerate("Hoy aprendemos cómo se instalan aplicaciones en Linux".split())
]

SCENES = {
    "stack_title_subs": (
        {
            "timeline": [{"source_in": 0.2, "source_out": 2.8}],
            "reframe": {
                "mode": "stack",
                "facecam": {"x": 0.65, "y": 0, "w": 0.35, "h": 0.4},
                "game": {"x": 0, "y": 0, "w": 0.65, "h": 1},
            },
            "layers": [
                {"type": "subtitle", "end": 2.6, "style": {"font": "Poppins", "size": 0.05, "position_y": 0.72}},
                {
                    "type": "text",
                    "start": 0.0,
                    "end": 2.6,
                    "text": "CÓMO INSTALAR APPS",
                    "box": {"x": 0.5, "y": 0.06, "w": 0.9},
                    "style": {
                        "font": "Anton",
                        "size": 0.05,
                        "color": "#FFD400",
                        "bg_color": "#000000C0",
                        "bold": False,
                        "uppercase": True,
                        "outline_width": 0,
                    },
                },
            ],
        },
        1.0,
    ),
    "icon_and_shape_animated": (
        {
            "timeline": [{"source_in": 0.2, "source_out": 2.8}],
            "layers": [
                {
                    "type": "icon",
                    "asset": "icons/arrow-right",
                    "start": 0.0,
                    "end": 2.6,
                    "box": {"x": 0.7, "y": 0.5, "w": 0.2},
                    "animations": {
                        "enter": {"name": "slide_left", "dur": 0.6},
                        "loop": {"name": "float", "period": 1.0, "amount": 0.1},
                    },
                },
                {
                    "type": "shape",
                    "shape": "rect",
                    "start": 0.0,
                    "end": 2.6,
                    "fill": "#FFD40033",
                    "stroke": "#FFD400",
                    "box": {"x": 0.5, "y": 0.8, "w": 0.7, "h": 0.06},
                    "animations": {"enter": {"name": "pop", "dur": 0.4}},
                },
            ],
        },
        0.9,
    ),
    "zoom_region_and_progress": (
        {
            "timeline": [{"source_in": 0.2, "source_out": 2.8}],
            "layers": [
                {
                    "type": "effect",
                    "effect": "zoom_punch",
                    "start": 0.4,
                    "end": 2.2,
                    "region": {"x": 0, "y": 0, "w": 1, "h": 0.4},
                    "params": {"scale": 1.4, "attack": 0.3, "release": 0.3},
                },
                {
                    "type": "effect",
                    "effect": "progress_bar",
                    "start": 0.0,
                    "end": 2.6,
                    "z": 30,
                    "params": {"thickness": 0.02},
                },
            ],
        },
        1.3,
    ),
    "transition_midpoint": (
        {
            "timeline": [
                {"source_in": 0.0, "source_out": 1.4},
                {"source_in": 1.5, "source_out": 2.9, "transition_in": {"name": "slideleft", "dur": 0.6}},
            ],
            "layers": [],
        },
        1.1,
    ),
}


def _ssim(a: Path, b: Path) -> float:
    r = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(a), "-i", str(b), "-lavfi", "ssim", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    return float(re.search(r"All:([0-9.]+)", r.stderr).group(1))


@pytest.mark.parametrize("name", list(SCENES))
def test_render_matches_golden(name, tmp_path, sample_video):
    raw, t = SCENES[name]
    doc = ProjectDoc.model_validate({"media_id": "m", **raw})
    work = tmp_path / "w"
    work.mkdir()
    files, warnings = render_frames(
        doc,
        MediaInfo(str(sample_video), 640, 360, True),
        WORDS,
        [t],
        SCALE,
        work,
        tmp_path / "out",
        merged_fonts_dir(work),
    )
    assert warnings == []
    golden = GOLDEN / f"{name}.jpg"
    if os.environ.get("UPDATE_GOLDEN") == "1" or not golden.exists():
        golden.write_bytes(files[0].read_bytes())
        pytest.skip(f"referencia {'regenerada' if golden.exists() else 'creada'}: {golden.name}")
    assert _ssim(files[0], golden) >= THRESHOLD, (
        f"{name} se ha desviado de su referencia (revisa el cambio visual o regenera)"
    )
