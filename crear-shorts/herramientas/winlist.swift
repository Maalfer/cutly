import Cocoa
// Lista TODAS las ventanas en pantalla en orden de capas (la primera = la de más arriba).
// Salida TSV: z \t app \t título \t x \t y \t w \t h \t layer \t pid
let opts: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
guard let list = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]] else { exit(1) }
var z = 0
for w in list {
    let layer = w[kCGWindowLayer as String] as? Int ?? 0
    let owner = w[kCGWindowOwnerName as String] as? String ?? "?"
    let name = w[kCGWindowName as String] as? String ?? ""
    let pid = w[kCGWindowOwnerPID as String] as? Int ?? 0
    guard let b = w[kCGWindowBounds as String] as? [String: Any] else { continue }
    let x = Int((b["X"] as? Double) ?? 0), y = Int((b["Y"] as? Double) ?? 0)
    let ww = Int((b["Width"] as? Double) ?? 0), hh = Int((b["Height"] as? Double) ?? 0)
    print("\(z)\t\(owner)\t\(name)\t\(x)\t\(y)\t\(ww)\t\(hh)\t\(layer)\t\(pid)")
    z += 1
}
