# Arquitectura de cutly

> Qué es el sistema y cómo encajan sus piezas — independiente de los pasos operativos (eso está en
> `METODOLOGIA/`). Lee esto para entender el QUÉ; lee `METODOLOGIA/00-empezar-aqui-vm.md` para el CÓMO.

## 1. Las dos fases y sus contratos de datos

```
FASE 1 — GENERAR                              FASE 2 — EDITAR
crear-shorts/                                 editor/
  herramientas/vm_control.py                    scripts/short_desde_toma.py
  DEMO-<tema>/demo_<tema>.py                    scripts/construir_clip.sh (16:9 desde un directo)
        │                                             ▲
        │ produce                                     │ consume
        ▼                                             │
  editor/crudo/<toma>.mp4            ──────────────────┘
  editor/crudo/<toma>.steps.jsonl    (registro: cada paso, su hora, si falló)
  editor/crudo/<toma>.mapa.md        (rango en segundos de cada `mark`)
        │
        ▼
  editor/videos-editados/short_<Titulo>_editado.mp4   (1080×1920, banda para la cara, audio mudo)
  editor/videos-editados/_cortes.log                  (registro append-only de cada short construido)
```

**Último paso: la cara y la voz.** El Short sale mudo y con el hueco negro. El usuario graba aparte su cara
narrando (vídeo vertical con su voz) y el agente lo FUSIONA: quita sus tomas repetidas, mete la cara en la
banda de 648 px y re-temporiza la pantalla para que cada frase caiga sobre su momento
(`editor/METODOLOGIA-FUSION-CARA.md`):

```
  short_<Titulo>_editado.mp4 (mudo) + crudo/cara.mp4 (cara + voz)
        │ transcribir.py → analizar_fusion.py → fusion_plan.json → fusionar_cara_pantalla.py
        ▼
  editor/videos-editados/short_<Titulo>_editado.mp4   (cara en la banda, voz limpia, pantalla sincronizada)
        │ subtitular.py preparar → revisar texto → quemar
        ▼
  short_<Titulo>_editado_subtitulado.mp4   (subtítulos karaoke sobre la unión cara/pantalla)
        │ verificar_short.py
        ▼
  cumple editor/SHORT-IDEAL.md  →  se entrega
```

El contrato es el `.steps.jsonl`: cualquier pieza de Fase 2 (o un agente verificador) puede reconstruir
qué pasó, cuándo y si falló, sin tener que mirar el vídeo. Es lo que hace posible separar "quien actúa"
de "quien edita" sin que pierdan información entre sí.

## 2. Piezas y su responsabilidad única

| Pieza | Responsabilidad | NO hace |
|---|---|---|
| `vm_control.py` | Ver (captura/OCR), actuar (ratón/teclado humano), verificar en pantalla, grabar (VirtualBox), registrar pasos | No sabe nada del CONTENIDO de la demo (no conoce CVEs, comandos concretos) |
| `DEMO-<tema>/demo_<tema>.py` | El GUION de una demo concreta: qué teclear, en qué orden, qué verificar, cuándo marcar | No reinventa control de bajo nivel (todo eso vive en `vm_control.py`) |
| `short_desde_toma.py` | Construye el Short desde `.mp4` + `.steps.jsonl`, con las reglas de encuadre fijadas en `METODOLOGIA/10` | No sabe nada de la demo en sí: funciona igual para cualquier tema |
| `METODOLOGIA/09` | Reglas y fichas de apps, medidas y con causa raíz | No es un tutorial paso a paso de una demo concreta |
| `METODOLOGIA/10` | Checklist/plantilla para que una demo de terminal salga bien a la primera | No sustituye probar el guion sin grabar antes (Fase 0) |

Por qué importa esta separación: es lo que permite que una demo nueva, de **cualquier tema**, reutilice el
95% del sistema (§ en la respuesta de hace un momento) — solo `demo_<tema>.py` es nuevo cada vez.

## 3. Estado de hoy: un único agente, de principio a fin

Hoy, un mismo agente investiga el tema, escribe el guion, controla la VM, graba, verifica sus propias
comprobaciones y genera el Short. Funciona, pero tiene un punto débil real: **nadie externo revisa el
trabajo antes de dártelo por bueno**. Esta sesión, varios fallos (un falso éxito en `selecttext`, un
encuadre que cortaba texto) los encontré yo mismo a base de mirar capturas — no hubo una segunda mirada
independiente.

## 4. Propuesta: pipeline con agentes especializados y verificación independiente

### 4.1 Por qué NO es "todo en paralelo"
La VM es un recurso único y compartido (una pantalla, un ratón). **Actuar y grabar no se pueden paralelizar
entre sí** — son la misma operación. Lo que sí se puede separar y solapar es lo que ocurre ANTES (guion,
sin tocar la VM) y DESPUÉS (verificación y edición, sobre ficheros ya grabados) de ese tramo único.

### 4.2 Roles propuestos

```
                         ┌─────────────────────────┐
                         │      ORQUESTADOR          │  dirige, decide, habla con el usuario
                         └───────────┬───────────────┘
                                     │
          ┌──────────────────────────┼───────────────────────────┐
          ▼                                                      │
┌───────────────────┐                                            │
│  1. GUIONISTA       │  investiga el tema, escribe el guion       │
│  (sin tocar la VM)  │  (demo_<tema>.py) + doc de reconocimiento  │
└──────────┬──────────┘                                            │
           │ entrega: demo_<tema>.py + 00-recon.md                 │
           ▼                                                      │
┌───────────────────┐                                            │
│  2. OPERADOR-VM     │  despliega, actúa, graba — SECUENCIAL,    │
│  (dueño de la VM)   │  un único agente (la VM no se comparte)   │
└──────────┬──────────┘                                            │
           │ entrega: .mp4 + .steps.jsonl + .mapa.md                │
           ▼                                                      │
┌───────────────────┐         ┌──────────────────────┐            │
│  3a. VERIFICADOR    │────────▶│ ¿aprobado? sí/no + por │───────────┘
│  (independiente,    │         │ qué (fotogramas, log) │   si NO: vuelve al Operador-VM con
│  NO es quien actuó) │         └──────────────────────┘   la causa exacta (reintento dirigido,
└──────────┬──────────┘                                     no "repetir todo a ciegas")
           │ si SÍ
           ▼
┌───────────────────┐
│  4. EDITOR          │  short_desde_toma.py + el clip 16:9
│                     │  (editor/CLAUDE.md)
└─────────────────────┘
```

| Rol | Entrada | Salida | Puede empezar cuando... |
|---|---|---|---|
| **Orquestador** | petición del usuario | plan, decisiones, el resumen final | siempre (es quien arranca todo) |
| **Guionista** | tema/CVE/petición | `demo_<tema>.py` + `00-recon.md`, **probado a mano por SSH sin GUI** (Fase 0 de doc 10) | de inmediato, en paralelo a que el Operador-VM prepare el laboratorio |
| **Operador-VM** | guion ya probado | `.mp4` + `.steps.jsonl` + `.mapa.md` | cuando el guion está listo y la VM libre |
| **Verificador** | los tres ficheros de arriba | veredicto + lista de problemas concretos (con fotograma/segundo) | en cuanto termina la toma — **nunca es el mismo agente que actuó** |
| **Editor** | toma aprobada | Short + clip 16:9 | solo si el Verificador aprobó |

### 4.3 Qué comprueba el Verificador (checklist, no vibes)
Esto es lo que yo mismo hice a mano, a base de extraer fotogramas, durante toda la sesión — formalizado:
1. **Cada `mark` del `.mapa.md` tiene 0 pasos fallidos** (si no, rechazar sin más).
2. **Ningún texto cortado por el borde**: extraer 1 fotograma por acto y mirarlo (igual que hice yo).
3. **La banda de la cara mide `padtop` exacto** en varios instantes (ya lo hace `short_desde_toma.py`,
   pero el Verificador debe confirmarlo, no asumir que el "OK" del script basta).
4. **Legibilidad**: ¿el tamaño de letra es consistente con `METODOLOGIA/10` §0-3?
5. **Coherencia del guion ético**: ¿el laboratorio es propio/autorizado? (checklist de `CLAUDE.md` raíz).

Si el Verificador rechaza, devuelve al Operador-VM el **acto concreto** que falló (no "repetir todo"): el
`.mapa.md` ya da el rango en segundos, y `focus`/`clear_and_focus` son cambios quirúrgicos en el guion.

### 4.4 Cómo se ejecutaría de verdad
El Orquestador (yo, en la conversación principal) puede delegar el rol de **Guionista** y el de
**Verificador** a subagentes (vía la herramienta `Agent`) sin pedir nada especial: son tareas de
investigación/revisión, no requieren privilegios nuevos. El **Operador-VM** en cambio necesita acceso
exclusivo a la VM — no tiene sentido paralelizarlo, así que normalmente lo ejecuta el propio Orquestador
o un único subagente dedicado por toma.

**Para automatizar el pipeline entero** (que el Orquestador lance Guionista → Operador-VM → Verificador →
Editor sin que yo tenga que ir coordinando cada paso a mano, como hice hoy) hace falta la herramienta
`Workflow`, que SÍ permite definir esta cadena con fases y agentes. Pero esa herramienta **solo se activa
si el usuario lo pide explícitamente** (política del propio Claude Code, no una limitación técnica) —
así que este diseño queda listo para implementarse como Workflow en cuanto confirmes que quieres que las
demos se produzcan así de punta a punta sin tu supervisión manual en cada fase.

### 4.5 Lo que esto compra, en concreto
- Un Short nunca llega al usuario sin que alguien distinto de quien lo grabó lo haya mirado fotograma a
  fotograma — el fallo de "se ve pequeño" o "queda cortado" se detecta ANTES de pedirte que lo revises tú.
- El Guionista puede trabajar en paralelo mientras se prepara el laboratorio (hoy todo es secuencial).
- Un rechazo del Verificador da un reintento dirigido (el acto concreto), no una repetición completa de
  10+ minutos como las que hicimos hoy a mano.
