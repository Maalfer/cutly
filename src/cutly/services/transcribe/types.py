"""Tipos comunes de transcripción, independientes del motor."""

from pydantic import BaseModel


class Word(BaseModel):
    w: str
    start: float
    end: float
    p: float | None = None  # probabilidad; None si se reparte a mano tras editar texto


class Segment(BaseModel):
    id: int
    start: float
    end: float
    text: str
    words: list[Word]
