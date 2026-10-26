import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_browser_upload_logic():
    """Lógica de subida del navegador (reintentos, bloqueos, reanudación) con XHR simulado."""
    r = subprocess.run(["node", str(ROOT / "js" / "upload.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_editor_javascript_matches_the_server(tmp_path):
    """Animación, tiempos con transiciones, agrupación de subtítulos y reencuadre del editor = los del servidor."""
    import itertools
    import json

    from cutly.schema.project import Animations, ProjectDoc, TextLayer, TimelineClip, Transition
    from cutly.services.render import ass as A
    from cutly.services.render.animation import eval_props
    from cutly.services.verify.checks import output_to_source

    anims = [
        {},
        {"enter": {"name": "pop", "dur": 0.4}},
        {"enter": {"name": "slide_left", "dur": 0.5}, "exit": {"name": "fade", "dur": 0.3}},
        {"enter": {"name": "bounce", "dur": 0.6}, "exit": {"name": "slide_up", "dur": 0.4}},
        {"enter": {"name": "spin_in", "dur": 0.5}, "loop": {"name": "pulse", "period": 1.2, "amount": 0.1}},
        {"loop": {"name": "wiggle", "period": 0.8, "amount": 0.2}},
        {"loop": {"name": "blink", "period": 0.9, "amount": 0.3}},
        {"loop": {"name": "float", "period": 1.0, "amount": 0.3}},
        {"loop": {"name": "shake", "period": 1.0, "amount": 0.4}},
        {
            "keyframes": [
                {"t": 1, "x": 0.8, "scale": 2, "easing": "linear"},
                {"t": 2, "x": 0.2, "opacity": 0.5, "rotation": 30, "easing": "ease_out_back"},
            ]
        },
        {
            "enter": {"name": "zoom_in", "dur": 0.4},
            "keyframes": [
                {"t": 0.5, "y": 0.2, "easing": "ease_out_elastic"},
                {"t": 1.5, "y": 0.9, "easing": "ease_out_bounce"},
            ],
        },
    ]
    fx = {"animation": [], "timeline": [], "cues": [], "lines": []}
    for a in anims:
        layer = TextLayer(start=2, end=6, text="x", opacity=0.9, animations=Animations.model_validate(a))
        for tau in (0, 0.1, 0.25, 0.4, 0.75, 1.0, 1.7, 2.0, 3.0, 3.7, 3.9, 4.0):
            p = eval_props(layer, tau, 0.5, 0.2, 5.0)
            fx["animation"].append({"layer": layer.model_dump(mode="json"), "tau": tau, "base_x": 0.5, "base_y": 0.2, "base_rot": 5.0,
                                    "expected": {"dx": p.dx, "dy": p.dy, "scale": p.scale, "opacity": p.opacity, "rot": p.rot}})  # fmt: skip
    words = [{"w": f"p{i}", "start": 1 + i * 0.7, "end": 1.5 + i * 0.7} for i in range(40)]
    tls = [
        [TimelineClip(source_in=2, source_out=12)],
        [
            TimelineClip(source_in=2, source_out=8, speed=1.5),
            TimelineClip(source_in=10, source_out=18, transition_in=Transition(name="fade", dur=0.5)),
        ],
        [
            TimelineClip(source_in=0, source_out=6),
            TimelineClip(source_in=7, source_out=13, speed=2, transition_in=Transition(name="slideleft", dur=0.8)),
            TimelineClip(source_in=20, source_out=24),
        ],
    ]
    for tl in tls:
        doc = ProjectDoc(media_id="m", timeline=tl)
        starts = A.timeline_starts(tl)
        mapped = A.map_words(words, A.build_time_map(tl))
        fx["timeline"].append({"timeline": [c.model_dump(mode="json") for c in tl], "starts": starts, "duration": doc.duration, "words": words,
                               "mapped": [list(m) for m in mapped],
                               "sources": [[t, output_to_source(doc, t)] for t in (0, 1.0, 3.2, 5.5, 7.9, 10.3, max(doc.duration - 0.2, 0))]})  # fmt: skip
    wt = [
        (0.0, 0.3, "Hola"),
        (0.35, 0.6, "amigos."),
        (0.7, 1.0, "Hoy"),
        (3.0, 3.3, "otra"),
        (3.4, 3.6, "vez"),
        (3.65, 3.9, "más"),
        (4.0, 4.2, "texto"),
        (4.25, 4.5, "largo?"),
        (4.55, 4.8, "fin"),
    ]
    for m in (1, 2, 3, 4):
        fx["cues"].append({"words": [{"w": w[2], "start": w[0], "end": w[1]} for w in wt] and [[w[0], w[1], w[2]] for w in wt], "max_words": m,
                           "cues": [[w[2] for w in cue] for cue in A.group_cues(wt, m)]})  # fmt: skip
    for texts, ml in itertools.product(
        [
            ["aprender", "cómo", "se"],
            ["aplicaciones", "en", "Linux,"],
            ["los", "repositorios", "del"],
            ["uno", "dos"],
            ["x"],
            ["a", "b", "c", "d", "e", "f"],
            ["internacionalización", "de", "aplicaciones", "web"],
        ],
        (1, 2, 3),
    ):
        fx["lines"].append({"texts": texts, "max_lines": ml, "lines": A._lines(texts, ml)})
    fixture = tmp_path / "fixtures.json"
    fixture.write_text(json.dumps(fx))
    r = subprocess.run(
        ["node", str(ROOT / "js" / "editor_parity.test.mjs"), str(fixture)], capture_output=True, text=True, timeout=120
    )
    assert r.returncode == 0, r.stdout + r.stderr
