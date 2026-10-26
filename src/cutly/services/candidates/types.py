"""Tipos del selector de clips."""

from dataclasses import dataclass, field
from typing import Literal

Criterion = Literal["hook", "complete_story", "strong_opinion", "funny", "standalone_value"]
ALL_CRITERIA: tuple[str, ...] = ("hook", "complete_story", "strong_opinion", "funny", "standalone_value")

CRITERIA_HELP = {
    "hook": "arranca con una frase que engancha en los primeros 3 segundos",
    "complete_story": "tiene planteamiento, desarrollo y cierre sin depender de lo anterior",
    "strong_opinion": "defiende una opinión fuerte o polémica con argumentos",
    "funny": "momento gracioso o con reacción genuina",
    "standalone_value": "aporta valor a quien no vio el directo: se entiende solo y enseña o cuenta algo útil",
}


@dataclass
class ProposeParams:
    criteria: list[str] = field(default_factory=lambda: list(ALL_CRITERIA))
    min_seconds: float = 25.0
    max_seconds: float = 90.0  # duración típica
    long_max_seconds: float = 300.0  # tope para los pocos clips de varios minutos
    per_chunk: int = 6
    max_candidates: int = 20
    instructions: str = ""


@dataclass
class RawCandidate:
    """Lo que devuelve el modelo: referencias a segmentos, no a segundos."""

    start_segment: int
    end_segment: int
    title: str
    reason: str
    criteria: list[str]
    score: int


@dataclass
class Candidate:
    start: float
    end: float
    score: float
    title: str
    reason: str
    criteria: list[str]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    refusals: int = 0
