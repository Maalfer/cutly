from PIL import Image
import sys

img = Image.open(sys.argv[1] if len(sys.argv) > 1 else '/tmp/safari_check.png').convert('RGB')
w, h = img.size
print(f'Imagen: {w}x{h} px (Retina 2x)')

# Buscar píxeles rojos del botón (#d70015..#ff5148) en la mitad inferior
best_y = {}
count = 0
px = img.load()
for y in range(h//2, h, 2):
    row_hits = 0
    for x in range(0, w, 2):
        r, g, b = px[x, y]
        if r > 180 and g < 90 and b < 90:  # rojo intenso
            row_hits += 1
    if row_hits > 100:  # fila con mucho rojo = botón
        best_y[y] = row_hits

if best_y:
    # la banda de filas rojas más baja y ancha = botón COPIAR
    ys = sorted(best_y.keys())
    # tomar el bloque continuo más reciente
    center_y = ys[len(ys)//2]
    # buscar extensión horizontal del rojo en center_y
    xs = [x for x in range(0, w, 2)
          if px[x, center_y][0] > 180 and px[x, center_y][1] < 90 and px[x, center_y][2] < 90]
    center_x = (min(xs) + max(xs)) // 2
    print(f'BOTÓN ENCONTRADO (px físicos): centro=({center_x},{center_y})')
    print(f'BOTÓN (puntos lógicos, cliclick): ({center_x//2},{center_y//2})')
    print(f'Extensión vertical botón: y={min(ys)} a y={max(ys)}')
else:
    print('NO ENCONTRADO en mitad inferior — probablemente hay que hacer scroll')
