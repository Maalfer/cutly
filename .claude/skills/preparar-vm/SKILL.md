---
name: preparar-vm
description: Deja la VM de VirtualBox lista para grabar (arrancada, con sesión, canal con el invitado y grabación configurada) y diagnostica lo que falte. Úsala antes de cualquier demo o cuando la VM no responda.
---

# Preparar la VM

Herramienta: `python crear-shorts/herramientas/vm_control.py` (doc: `crear-shorts/METODOLOGIA/00-empezar-aqui-vm.md`).

1. `vm_control.py doctor`: lee cada FALLA y su solución.
2. Si está apagada: `vm_control.py start --login` (configura la grabación con la VM apagada, arranca, inicia sesión
   si el usuario ha dado `VM_GUEST_PASSFILE`, y espera al canal diciendo en qué fase se queda). Sin
   `VM_GUEST_PASSFILE`, pide al usuario que inicie sesión él: **nunca adivines la contraseña**.
3. Si no hay canal SSH: `vm_control.py bootstrap` (con `VM_GUEST_PASSFILE`, lo monta solo por guestcontrol).
4. Si la demo es la de IDOR o usa Burp/Firefox: `vm_control.py prepare`.
5. Repite `doctor` hasta "todo listo para grabar una demo". Lo que dependa del usuario (instalar software en el
   anfitrión, aceptar un EULA, una contraseña) se le pide, no se hace por él.

Nunca hagas snapshots ni clones de la VM (`suspend`/`resume` sí).
