// Para que cutly estudio sepa en qué está OpenCode, igual que ya sabe con Claude Code (sus hooks nativos,
// .claude/settings.json -> estudio/hooks/estado_claude.py). Mismo contrato de fichero: la app le pasa la ruta
// en CUTLY_ESTADO_FICHERO y espera {"estado": "trabajando"|"necesita"|"libre", "mensaje": "..."} en JSON.
// Solo escribe si esa variable existe (fuera de la app no hace nada, igual que el hook de Claude Code).
//
// Probado contra el binario real (opencode 2.3.0): ctx.event.subscribe() dicta "trabajando"/"libre" a partir
// de session.execution.started/succeeded (y session.idle si lo emite); ctx.permission.hook("evaluate")
// dicta "necesita" solo cuando effect=="ask" (si ya está permitido o denegado por configuración, no hace
// falta avisar: nadie tiene que responder).
import { writeFileSync } from "node:fs"

const LIBRE = new Set([
  "session.idle",
  "session.execution.succeeded",
  "session.execution.failed",
  "session.execution.error",
  "session.execution.cancelled",
])

function escribir(ficha, estado, mensaje) {
  if (!ficha) return
  try {
    writeFileSync(ficha, JSON.stringify({ estado, mensaje: mensaje || "" }))
  } catch {
    // si la app ya cerró el fichero o la carpeta temporal no existe, no hay nadie escuchando: no pasa nada
  }
}

export default {
  id: "cutly-estado",
  async setup(ctx) {
    const ficha = process.env.CUTLY_ESTADO_FICHERO
    if (!ficha) return {}

    const controller = new AbortController()
    ;(async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          if (event.type === "session.execution.started") escribir(ficha, "trabajando", "")
          else if (LIBRE.has(event.type)) escribir(ficha, "libre", "")
        }
      } catch {
        // AbortError al cerrar la sesión: esperado, no es un fallo real
      }
    })()

    await ctx.permission.hook("evaluate", (event) => {
      if (event.effect === "ask") {
        const detalle = Array.isArray(event.resources) ? event.resources.join(", ") : ""
        escribir(ficha, "necesita", [event.action, detalle].filter(Boolean).join(": "))
      }
    })

    return () => controller.abort()
  },
}
