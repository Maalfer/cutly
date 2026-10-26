"""Tipos de los candidatos a clip. Quién los elige es el agente (Claude Code u otro) a través de la API."""

from dataclasses import dataclass
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
class Candidate:
    start: float
    end: float
    score: float
    title: str
    reason: str
    criteria: list[str]
