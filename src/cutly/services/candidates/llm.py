"""Acceso al modelo. `CandidateLLM` permite sustituirlo en tests o por otro proveedor."""

import json
from typing import Protocol

from pydantic import BaseModel

from cutly.config import get_settings
from cutly.services.candidates.prompts import SYSTEM, build_user
from cutly.services.candidates.types import (
    ALL_CRITERIA,
    ProposeParams,
    RawCandidate,
    Usage,
)


class LLMCandidate(BaseModel):
    start_segment: int
    end_segment: int
    title: str
    reason: str
    criteria: list[str]
    score: int


class LLMChunk(BaseModel):
    candidates: list[LLMCandidate]


# Esquema escrito a mano: estricto (additionalProperties:false) y sin restricciones numéricas,
# que la salida estructurada no admite; los rangos se validan en código.
SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_segment": {"type": "integer"},
                    "end_segment": {"type": "integer"},
                    "title": {"type": "string"},
                    "reason": {"type": "string"},
                    "criteria": {"type": "array", "items": {"type": "string", "enum": list(ALL_CRITERIA)}},
                    "score": {"type": "integer"},
                },
                "required": ["start_segment", "end_segment", "title", "reason", "criteria", "score"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}


class CandidateLLM(Protocol):
    def propose(
        self, chunk_text: str, id_range: tuple[int, int], params: ProposeParams
    ) -> tuple[list[RawCandidate], Usage]: ...


class AnthropicLLM:
    def __init__(self, client=None):
        if client is None:
            import anthropic

            client = anthropic.Anthropic(max_retries=4)
        self.client = client
        self.s = get_settings()

    def _call(self, model: str, user: str):
        return self.client.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.s.candidates_effort, "format": {"type": "json_schema", "schema": SCHEMA}},
        )

    def propose(self, chunk_text, id_range, params):
        user = build_user(chunk_text, id_range, params)
        usage = Usage()
        resp = self._call(self.s.candidates_model, user)
        usage.input_tokens += resp.usage.input_tokens
        usage.output_tokens += resp.usage.output_tokens
        if resp.stop_reason == "refusal":  # clasificador de seguridad: se reintenta con el modelo de reserva
            usage.refusals += 1
            resp = self._call(self.s.candidates_fallback_model, user)
            usage.input_tokens += resp.usage.input_tokens
            usage.output_tokens += resp.usage.output_tokens
            if resp.stop_reason == "refusal":
                usage.refusals += 1
                return [], usage
        if resp.stop_reason == "max_tokens":
            raise RuntimeError(
                "La respuesta del modelo se cortó por longitud; reduce `per_chunk` o el tamaño del bloque"
            )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        data = LLMChunk.model_validate(json.loads(text))
        return [RawCandidate(**c.model_dump()) for c in data.candidates], usage


class FakeLLM:
    """Para tests: devuelve un clip fijo por bloque, desde el primer segmento hasta ~45 s después."""

    def propose(self, chunk_text, id_range, params):
        lines = [ln for ln in chunk_text.splitlines() if ln.startswith("[")]
        first = int(lines[0][1:].split(" ")[0])
        return [RawCandidate(first, min(first + 8, id_range[1]), f"Clip {first}", "Prueba", ["hook"], 80)], Usage(10, 5)


def get_llm() -> CandidateLLM:
    if get_settings().candidates_backend == "fake":
        return FakeLLM()
    return AnthropicLLM()
