---
name: grabar-demo
description: Prepara, ensaya y graba una demo de ciberseguridad nueva DENTRO de la VM de VirtualBox con entrada humana, y genera el Short mudo. Úsala cuando el usuario pida una demo o un vídeo de una técnica nueva.
argument-hint: "<tema de la demo>"
---

# Grabar una demo nueva en la VM

Tema: $ARGUMENTS. Reglas no negociables: `CLAUDE.md` (todo en la VM, sin snapshots, solo laboratorios propios o
autorizados, nunca adivinar contraseñas, verificar cada acción).

1. `/preparar-vm` (o `python crear-shorts/herramientas/vm_control.py doctor` debe decir "todo listo").
2. Mira el catálogo de demos en `crear-shorts/README.md`: puede bastar con adaptar una existente.
3. Si es de terminal, sigue `crear-shorts/METODOLOGIA/10-plantilla-demo-terminal.md`; si es GUI,
   `crear-shorts/METODOLOGIA/09-conducir-apps-kali.md`. Copia `crear-shorts/DEMO-SSHOLE/demo_sshole.py` (terminal) o
   `crear-shorts/DEMO-IDOR/demo_idor.py` (GUI) a `crear-shorts/DEMO-<TEMA>/`.
4. **Ensaya sin grabar** (Fase 0) hasta tener los comandos exactos; luego la toma con `take start`, `rec start`,
   `mark` por acto y `take end` (protocolo: `crear-shorts/METODOLOGIA/04-flujo-toma-video.md`).
5. `python editor/shorts/short_desde_toma.py <toma> --titulo Titulo-Con-Gancho` y revisa el mapa de edición.
6. Añade la demo al catálogo de `crear-shorts/README.md`.
