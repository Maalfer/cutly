# Mapa de edición — idor-run8

| # | Momento | Desde (s) | Hasta (s) | Dura | Pasos |
|---|---|---|---|---|---|
| 1 | Acto 1: usuarioA ve su cuenta (id=1001) | 0.0 | 20.5 | 20.4 s | 6 |
| 2 | Acto 2: Burp intercepta la petición | 20.5 | 30.8 | 10.3 s | 13 |
| 3 | Acto 2b: a Repeater, 1001 -> 1002 | 30.8 | 49.3 | 18.5 s | 23 |
| 4 | Acto 2c: Send -> datos de usuarioB (IDOR) | 49.3 | 59.5 | 10.1 s | 6 |
| 5 | Acto 3: lo mismo sin Burp, en la barra del navegador | 59.5 | 78.2 | 18.8 s | 5 |
| 6 | Cierre | 78.2 | 91.9 | 13.6 s | 0 |

Tiempos en segundos desde el inicio del vídeo (±0,3 s). Úsalos en editor/CLAUDE.md para los cortes.
