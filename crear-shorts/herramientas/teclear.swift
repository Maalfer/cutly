// teclear.swift — Emisor de entrada (teclado y ratón) para tipear.py y mover.py (macOS).
// Lee eventos por stdin, uno por línea, y los envía como entrada real:
//   k <HEX>   -> escribe el carácter Unicode U+HEX (independiente de la distribución del teclado,
//                así que á é ú ü ñ ¿ € funcionan; `keystroke "á"` de AppleScript escribe "a")
//   bs        -> retroceso          ret -> Intro        tab -> Tabulador
//   m <x> <y> -> mueve el cursor a (x,y) en puntos lógicos, sin coste fijo (cliclick tarda ~100 ms por
//                movimiento, demasiado lento para trazar un trayecto con muchos puntos)
//   d <seg>   -> espera (segundos, decimales)
// Compilar una vez:  swiftc -O -o ~/Desktop/ctrl-kit/teclear teclear.swift
// Requiere el permiso de Accesibilidad (el mismo que cliclick).
import Foundation
import CoreGraphics

let src = CGEventSource(stateID: .hidSystemState)

func postKey(_ code: CGKeyCode) {
    for down in [true, false] {
        CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: down)?.post(tap: .cghidEventTap)
        usleep(6_000)          // sin micropausa entre eventos, la app pierde pulsaciones
    }
}
func postChar(_ scalar: UInt32) {
    guard let u = Unicode.Scalar(scalar) else { return }
    let utf16 = Array(String(Character(u)).utf16)
    for down in [true, false] {
        guard let e = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: down) else { continue }
        e.keyboardSetUnicodeString(stringLength: utf16.count, unicodeString: utf16)
        e.post(tap: .cghidEventTap)
        usleep(6_000)
    }
}

while let line = readLine() {
    let p = line.split(separator: " ", maxSplits: 1).map(String.init)
    guard let cmd = p.first else { continue }
    switch cmd {
    case "k":  if p.count > 1, let v = UInt32(p[1], radix: 16) { postChar(v) }
    case "bs":  postKey(51)
    case "ret": postKey(36)
    case "tab": postKey(48)
    case "m":
        let q = (p.count > 1 ? p[1] : "").split(separator: " ")
        if q.count == 2, let x = Double(q[0]), let y = Double(q[1]) {
            CGEvent(mouseEventSource: src, mouseType: .mouseMoved,
                    mouseCursorPosition: CGPoint(x: x, y: y), mouseButton: .left)?.post(tap: .cghidEventTap)
        }
    case "d":   if p.count > 1, let s = Double(p[1]) { usleep(UInt32(max(0, s) * 1_000_000)) }
    default: break
    }
}
usleep(150_000)   // al terminar, dar tiempo a que la app consuma los últimos eventos
