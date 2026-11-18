import Foundation
import AppKit

let pos = NSEvent.mouseLocation
let screenH = NSScreen.screens.first?.frame.height ?? 832
// NSEvent usa origen abajo-izquierda; cliclick usa arriba-izquierda → convertir Y
print("cursor_x=\(Int(pos.x)) cursor_y=\(Int(screenH - pos.y)) (coords cliclick)")
