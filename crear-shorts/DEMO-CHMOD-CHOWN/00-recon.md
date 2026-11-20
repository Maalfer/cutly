# chmod y chown — guion técnico (básico, pedagógico, con acciones reales)

> Objetivo: enseñar los permisos de Linux desde cero, en la propia VM del usuario (sin laboratorio de
> terceros): `chmod` con letras, `chmod` con números, y `chown` muy básico. No hay CVE ni objetivo remoto:
> se crea una carpeta y un documento de texto propios, y se INTENTA leerlos/escribirlos/entrar en ellos
> de verdad en cada paso — no se explica solo con la notación simbólica, se ve el efecto.
>
> **Decisión explícita del usuario (sesión 2026-11-20), tras ver el primer guion:** nada de `stat -c '%a'`
> ni de comandos encadenados con `&&` (demasiado avanzado/denso para un espectador principiante); cada
> comando va suelto, y el ejercicio es sobre una carpeta/documento normal, no un `script.sh` — "algo que
> entiende todo el mundo: si se puede leer, cuando no se puede leer, cuando no se puede escribir".

## 1. Lo que se enseña (para el guion del vídeo)
- Todo fichero tiene 3 "quién": **u**ser (dueño), **g**roup (grupo), **o**thers (resto) — y **a** = los tres.
- Cada uno tiene 3 permisos: **r**ead, **w**rite, e**x**ecute.
- `chmod` con **letras**: `chmod u-r fichero` quita, `chmod u+r fichero` añade. Se demuestra quitándose el
  propio dueño la lectura y la escritura, e intentando leer/escribir de verdad (`cat`, `echo >>`): sale
  "Permission denied" aunque seas el dueño del fichero — el permiso manda, no la propiedad.
- Las **carpetas** también tienen permisos: sin el bit `x`, ni el propio dueño puede `cd` dentro (aunque
  tenga `r`). Es la confusión más común ("por qué no puedo entrar si tengo permiso de lectura").
- `chmod` con **números**: r=4, w=2, x=1, se suman por cada "quién" → un dígito 0-7. `644` = dueño rw
  (4+2), grupo r (4), resto r (4). `600` = solo el dueño, nadie más nada.
- `chown`: cambia el **propietario** (solo root/`sudo`). Efecto real: si cambias el dueño a otro usuario,
  TÚ puedes perder el acceso aunque los bits de permiso no cambien — "u" ahora es otra persona.

## 2. La secuencia (medida en esta VM, 2026-11-20) — un comando por línea, sin tuberías
```bash
# Acto 1 — creamos la carpeta y el documento, y lo leemos
mkdir carpeta-permisos
cd carpeta-permisos
echo 'Hola, esto es un documento de prueba.' > notas.txt
ls -l notas.txt                      # -rw-rw-r-- (664: umask 002 de esta VM, no 022)
cat notas.txt                        # se lee bien

# Acto 2 — chmod con letras: cuando NO se puede leer
chmod u-r notas.txt
cat notas.txt                        # cat: notas.txt: Permission denied
chmod u+r notas.txt
cat notas.txt                        # vuelve a leerse

# Acto 3 — chmod con letras: cuando NO se puede escribir
chmod u-w notas.txt
echo 'Ahora si puedo escribir.' >> notas.txt    # bash: notas.txt: Permission denied
chmod u+w notas.txt
echo 'Ahora si puedo escribir.' >> notas.txt    # esta vez sí
cat notas.txt                        # las dos líneas

# Acto 4 — chmod con números: el mismo permiso, como una suma
chmod 644 notas.txt
ls -l notas.txt                      # -rw-r--r--
chmod 600 notas.txt
ls -l notas.txt                      # -rw------- (privado: solo el dueño)

# Acto 5 — las carpetas también tienen permisos: hace falta "x" para entrar
cd ..
chmod u-x carpeta-permisos
cd carpeta-permisos                  # bash: cd: carpeta-permisos: Permission denied
chmod u+x carpeta-permisos
cd carpeta-permisos                  # ahora sí
pwd                                   # /home/kali/carpeta-permisos

# Acto 6 — chown: cambiar el propietario (y por qué también importa)
ls -l notas.txt                      # dueño: kali (el fichero sigue en 600 del Acto 4)
sudo chown root notas.txt
cat notas.txt                        # cat: notas.txt: Permission denied — ya NO soy el dueño
sudo chown kali notas.txt
cat notas.txt                        # se lee de nuevo
```
Verificación por OCR: siempre sobre texto llano que aparece de verdad en pantalla (el contenido leído, o
el "Permission denied" del propio bash/cat) — nunca con `stat` ni formatos `-c '%...'`, que son sintaxis
avanzada y no aportan nada que el espectador no vea ya con `ls -l`/`cat`/`cd`.

**Pausa mínima entre comandos:** con <1 s entre el `Return` de un comando y teclear el siguiente, el
terminal puede no haber acabado de procesar el anterior y el siguiente comando sale mal tecleado (medido:
una comprobación que debía dar verdadero dio falso 5 de 5 veces con 0,3 s; con ≥1,2 s no ha vuelto a
fallar). El guion usa 1,2 s fijos entre cada comando suelto (`PAUSA` en `demo_chmod_chown.py`).

## 3. Entorno: la VM puede seguir en modo puente de la demo anterior (masscan)
Si `vm_control.py doctor` falla con "no hay reenvío 127.0.0.1:2222 -> 22", la VM sigue con el adaptador en
modo puente (`bridged`) de `DEMO-MASSCAN`. Usa `VM_HOST=<IP real> VM_SSH_PORT=22` (la IP la da
`vm_control.py status` sin necesitar SSH) para todos los comandos, incluido este script — no hace falta
volver a NAT para esta demo, no usa red para nada.

**Fallo de montaje encontrado y arreglado esta sesión:** con el NIC en modo puente, `vm_control.py start`
sigue intentando añadir la regla NAT `127.0.0.1:2222->22` (`ensure_natpf()`), pero su detección de si ya
existe busca "Forwarding" en `showvminfo`, texto que VirtualBox NO imprime para un NIC que no es `nat`
— así que el script la añade otra vez con el mismo nombre ("ssh") y VirtualBox la rechaza
("A NAT rule of this name already exists"), abortando `start()` antes de arrancar. Arreglo manual
aplicado: `VBoxManage modifyvm kali --natpf1 delete ssh` (dejarla ausente) y luego `start` la vuelve a
crear sin chocar. Pendiente para `PENDIENTE.md`: `ensure_natpf()` debería detectar la regla por su nombre
(`--natpf1 delete ssh` con manejo de error, o listar con otro comando que sí la vea en modo puente) en vez
de buscar "Forwarding" en texto que depende del modo del NIC.

## 4. Calidad de grabación: 25 Mbps en vez de 10 Mbps
Pedido explícito del usuario: "las grabaciones deben verse lo mejor posible, nada borroso". El VP8 nativo
de VirtualBox (`KBPS` en `vm/grabacion.py`) pasó de 10 a 25 Mbps — a 1920x1012@30fps el texto de terminal
de alto contraste es justo el contenido que más sufre los bloques de compresión de VP8 a bitrates bajos.
El `.webm` es solo intermedio (se recodifica a H.264 CRF 14 y se borra), así que el único coste es disco y
tiempo de recodificado, no el Short final. **VirtualBox exige la VM APAGADA para aplicar un bitrate mayor**
si ya se grabó en esa sesión (`vm/grabacion.py` lo explica): hubo que `stop` + `start` tras cambiar `KBPS`.

## 5. Para el vídeo (guion sugerido)
1. **Gancho:** "¿te sale 'Permission denied' y no sabes por qué? Esto es TODO lo que hace falta saber."
2. **Letras, de verdad:** no solo explicar qué significa `u-r` — quitarse la propia lectura y comprobar
   que ni el dueño puede leer su propio fichero. Lo mismo con la escritura.
3. **La trampa de las carpetas:** sin `x` no se puede entrar, aunque haya lectura. Es el fallo que más
   gente comete sin saber por qué pasa.
4. **Números:** el mismo permiso, pero como una suma (r=4, w=2, x=1) — 644 y 600, los dos que de verdad se
   usan en el día a día.
5. **chown, con su truco:** cambiar el dueño del fichero deja fuera al dueño ANTERIOR, aunque los permisos
   no hayan cambiado — por eso `chown` importa tanto como `chmod`.
6. **Cierre:** lo dejamos todo como estaba — llamada a comentar.

## 6. Nada que limpiar (fuera de lo que el propio guion limpia)
Todo ocurre dentro de `~/carpeta-permisos`, carpeta propia del usuario en su propia VM. El script la borra
y recrea al empezar (idempotente) y la vuelve a borrar al final, tras devolver el propietario a `kali`. No
se toca ningún fichero del sistema ni de otro usuario.
