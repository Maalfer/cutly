# Cutly

Editor de vídeo **API-first**: convierte directos largos en clips verticales con subtítulos, efectos y animaciones.
Se maneja desde la web o con una **API key** (por ejemplo desde Claude Code): ambos usan los mismos endpoints.

- Subida reanudable y transcripción local (Whisper). **Sin APIs de IA externas**: tu agente (p. ej. Claude Code) elige los clips con la API key de la app.
- Montaje en JSON: cortes, subtítulos, texto, iconos, efectos y animaciones explicativas (`scene`).
- Render con FFmpeg y verificación por fotogramas y comprobaciones automáticas.

## Arranque

```bash
cp .env.example .env        # y cambia CUTLY_SESSION_SECRET
uv sync
uv run cutly create-user mario
uv run cutly create-key claude --write
uv run uvicorn cutly.api.app:app --reload
```

Necesita `ffmpeg`; Redis para la cola de trabajos (o `CUTLY_QUEUE_MODE=inline` en desarrollo). Documentación de la API en `/api/v1/docs`; guía para agentes en `docs/AGENT_GUIDE.md`.
