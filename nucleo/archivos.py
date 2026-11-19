"""Leer y escribir JSON / texto en UTF-8 cerrando siempre el archivo (en Windows un archivo abierto no se puede
borrar ni mover, y sin cerrar una escritura puede quedar a medias)."""
import json


def leer_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def escribir_json(path, datos, indent=1):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=indent)


def leer_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def leer_texto(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def escribir_texto(path, texto):
    with open(path, "w", encoding="utf-8") as f:
        f.write(texto)
