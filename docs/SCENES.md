# Escenas animadas (capa `scene`)

Una **escena** es una animación 2D tipo «explainer» (redes, flujos, esquemas, rótulos cinematográficos) que Cutly dibuja
en el servidor y superpone al vídeo como una capa más. Sirve para lo mismo que las animaciones de la carpeta `yt/`
(viaje de paquetes, DNS, TLS, partes de una URL…) pero **la describes con JSON**: no hay que escribir código.

Dos formas de usarla:

1. **Plantilla** (lo rápido): `{"type":"scene","template":"dns_lookup","params":{"domain":"cogny.es"},"start":4,"end":22}`.
   La plantilla se ajusta sola a la duración de la capa (`end - start`) y a la orientación (`orient`).
2. **Escena a mano** (lo flexible): `{"type":"scene","scene":{…}}` con tus propios nodos, textos, enlaces, viajeros y cámara.
   Punto de partida: `POST /scenes/build` expande cualquier plantilla a su JSON completo; edítalo y úsalo como `scene`.

## Flujo de trabajo recomendado

1. `GET /scenes/templates` → catálogo (parámetros, duración recomendada y una `example_layer`).
2. **Mira antes de montar**: `POST /scenes/preview` con `{"template":…,"params":…,"duration":14,"times":[1,3,5,8,11,13]}` devuelve
   un PNG con esos fotogramas (hoja de contacto). No crea nada en el proyecto. Itera hasta que se vea bien.
3. `add_layer` con la capa `scene` (o `POST /projects/{id}/layers`).
4. Verifica dentro del proyecto con `GET /projects/{id}/frame?t=…` o `filmstrip` (la escena sale compuesta sobre el vídeo).
5. `render draft` → `render final`.

## La capa `scene`

| Campo | Qué es |
|---|---|
| `start`, `end` | Tiempos en el reloj del clip resultante. **Los tiempos DENTRO de la escena son segundos desde `start`.** |
| `template` + `params` | Plantilla generada y ajustada a la duración. |
| `scene` | Escena escrita a mano (alternativa a `template`). |
| `box` | Dónde se coloca en el fotograma: `x`,`y` (centro por defecto), `w` (fracción del ancho; 1 = ancho completo), `h` opcional (si no, se respeta la proporción de la escena), `anchor`. |
| `fit` | `contain` (se ve entera) o `cover` (rellena la caja recortando). |
| `opacity`, `animations.enter/exit` | Se aplican a toda la escena (funcionan `fade` y la opacidad; el resto de movimientos van dentro de la escena). |
| `z` | Orden respecto a otras capas (20 por defecto: sobre el vídeo, bajo los subtítulos). |

**Cómo colocarla según el vídeo (9:16, 1080×1920):**
- Recuadro explicativo en el tercio superior: `orient:"wide"` + `box:{"x":0.5,"y":0.3,"w":1.0}` (la escena 16:9 ocupa 1080×608).
- Pantalla completa vertical: `orient:"tall"` + `box:{"x":0.5,"y":0.5,"w":1.0,"h":1.0}`, `fit:"cover"`.
- Superpuesta sobre el vídeo (se ve lo de detrás): `"background":"transparent"` en los params.
- Deja libre la franja inferior (y > 0,82) y el borde derecho: tapan los botones de la app. Los subtítulos de la escena
  (`captions`) están dentro de su propio lienzo; si pones también la capa `subtitle`, no los solapes.

## Plantillas incluidas

Todas aceptan `orient` (`wide` 1600×900 | `tall` 900×1600), `accent` (#RRGGBB), `background` (`space`, `grid`, `solid`,
`transparent`) y `panel` (esquinas redondeadas con borde).

| Plantilla | Para qué | Parámetros propios |
|---|---|---|
| `packet_network` | TCP/IP: un mensaje se parte en paquetes que cruzan routers por rutas distintas; la cámara sigue a dos y el destino los reensambla | `packets` (3-12), `source_label`, `dest_label`, `captions` (lista) |
| `flow_steps` | Cadena de 2-8 nodos con un mensaje que viaja (y respuesta de vuelta): cliente→servidor, login, CI/CD… | `steps` `[{kind,label,sublabel?,color?}]`, `message`, `response`, `message_shape`, `return_trip`, `captions` |
| `dns_lookup` | Resolución DNS paso a paso (resolver → raíz → TLD → autoritativo) | `domain`, `ip` |
| `tls_handshake` | Handshake TLS y comparación HTTP (legible) vs HTTPS (cifrado) | `domain` |
| `url_anatomy` | Resalta esquema, dominio, puerto, ruta, parámetros y fragmento de una URL | `url` |
| `recap_cards` | Título + 1-6 tarjetas con icono que aparecen en secuencia | `title`, `items` `[{icon,title,body,color?}]` |
| `title_card` | Título cinematográfico con icono, línea de acento y subtítulo | `title`, `subtitle`, `icon` |
| `race_condition` | Condición de carrera: N peticiones simultáneas se cuelan antes de que el servidor compruebe «¿ya usado?» (doble canje, doble gasto, TOCTOU…) | `requests`, `client_label`, `server_label`, `resource_label`, `check_label`, `before_value`, `after_value`, `result_label` |

`captions` = subtítulos explicativos propios de la escena; se reparten en el tiempo. Marca énfasis con `**palabra**`.

## Escena a mano: referencia

```json
{
  "world": {"w": 1600, "h": 900},
  "background": {"style": "space", "accent": "#34E3FF", "vignette": 0.5, "radius": 0, "border": null},
  "camera": [
    {"t": 0, "zoom": 1},
    {"t": 3, "follow": "pkt", "zoom": 2.2, "look": 100},
    {"t": 6, "zoom": 1}
  ],
  "handheld": 0.4,
  "objects": [ … ]
}
```

- **Mundo**: coordenadas en unidades del mundo (1600×900 por defecto, origen arriba a la izquierda). Todo se escala al
  tamaño de la caja. Piensa en que la escena se verá a ~1080 px de ancho: **textos ≥ 30 unidades** para leerse en el móvil.
- **Cámara**: lista de claves `{t, x?, y?, zoom, follow?, look?, easing?}`; interpola entre ellas. `follow` = `id` de un
  objeto en movimiento (la cámara lo sigue; `look` la adelanta hacia donde va). `handheld` añade temblor suave (0 = fija).
- **Fondo**: `space` (degradado + estrellas), `grid`, `solid`, `gradient` o `transparent` (deja ver el vídeo).

### Campos comunes a todos los objetos

`id` (necesario si otro objeto lo referencia), `at` (aparece en ese segundo), `until` (empieza a desaparecer),
`enter` (`none|fade|pop|zoom|slide_up|slide_down|slide_left|slide_right|drop|draw|type`), `dur` (duración de entrada/salida),
`exit` (`none|fade|shrink`), `loop` (`pulse|float|blink|spin|wiggle`, `loop_period`), `opacity`, `z`,
`fixed` (**fijo en pantalla**: la cámara no le afecta; úsalo en subtítulos y títulos), `keys` (fotogramas clave
`[{t,x,y,scale,opacity,rotation,easing}]`, `t` absoluto en la escena).

### Objetos

| `type` | Qué dibuja | Campos clave |
|---|---|---|
| `node` | Dispositivo/icono vectorial con halo y etiqueta | `kind` (`server router computer phone cloud database lock key shield globe doc user circle box pill chip bolt check cross warning gear mail packet`), `x`,`y`, `size`, `color`, `label`, `sublabel`, `label_pos` (`below above left right inside`), `glow`, `rotation` |
| `text` | Texto con ajuste de línea | `text` (`**énfasis**`), `x`,`y`, `size`, `color`, `weight` (`regular bold black`), `font`, `align`, `max_w`, `bg` (píldora), `outline`, `mono`, `spacing`, `highlight`, `scramble` (0-1: símbolos cifrados). `enter:"type"` = máquina de escribir |
| `card` | Panel con icono, título y cuerpo | `x`,`y`, `w`, `h?`, `title`, `body`, `icon` (un `kind` de node), `color`, `size`, `scramble`, `accent` (`left top border none`) |
| `link` | Línea/arco entre dos puntos u objetos | `a`, `b` (`[x,y]` o `id`), `curve`, `dashed`, `arrow`, `width`, `alpha`, `glow`, `gap` (hueco en los extremos), `label`, `flash` (instantes en que destella). `enter:"draw"` la traza |
| `dot` | Viajero (paquete, mensaje, clave…) que recorre un camino con estela | `path` (lista de puntos/ids), `travel` (s del recorrido completo), `shape` (`dot packet mail key lock check`), `color`/`colors`, `size`, `label`, `label_numbered`, `count` + `stagger` (varias copias), `halo`, `trail`, `ease`, `on_arrive` (`none burst ring both`), `persist` |
| `ring` | Onda expansiva | `where`, `r0`, `r1`, `repeat`, `period`, `color` |
| `burst` | Chispas | `where`, `n`, `color`, `speed`, `life`, `seed` |
| `meter` | Barra que se llena | `x`,`y`, `w`,`h`, `v0`,`v1`, `fill_dur`, `label` |

### Ejemplo mínimo (a mano)

```json
{"type":"scene","start":3,"end":10,"box":{"x":0.5,"y":0.3,"w":1.0},"scene":{
  "objects":[
    {"type":"node","id":"pc","kind":"computer","x":300,"y":450,"size":150,"color":"#37F5A3","label":"Tu PC"},
    {"type":"node","id":"srv","kind":"server","x":1300,"y":450,"size":150,"color":"#FF5D8F","label":"Servidor","at":0.4},
    {"type":"link","a":"pc","b":"srv","gap":110,"at":0.8,"enter":"draw","arrow":true},
    {"type":"dot","path":["pc","srv"],"at":1.6,"travel":2,"shape":"packet","label":"GET","halo":true},
    {"type":"text","text":"Tu navegador **pide** la página","x":800,"y":820,"size":44,"at":1.0,"fixed":true}
  ]}}
```

## Límites y consejos

- Máx. 400 objetos por escena, 120 s por capa, caja ≤ 4096×4096. Fuentes: las de `GET /assets?kind=font` (por defecto Poppins).
- Todo es determinista y sin estado: cualquier instante se puede pedir suelto (`frame`, `filmstrip`, renders por tramos).
- Rendimiento en el VPS (2 CPU): ≈0,1–0,3 s por fotograma a pantalla completa 1080×1920; un borrador (⅓) es varias veces más rápido.
  Usa `draft` para iterar y evita escenas a pantalla completa de más de ~40 s en renders finales.
- Una escena opaca tapa el vídeo: úsala como «corte explicativo» (el vídeo sigue por debajo, también su audio) o pon
  `"background":"transparent"` para que solo floten los elementos.
- No pongas en la escena texto que no hayas escrito tú ni datos de la transcripción sin revisar: el texto se dibuja tal cual.
- Las escenas no se «ven» en el editor web (marcador punteado); usa **▶ Vista previa** del inspector o `POST /scenes/preview`.
