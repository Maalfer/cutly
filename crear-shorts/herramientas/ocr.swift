// ocr.swift — Lee texto de una captura de pantalla CON coordenadas.
// Uso:   ocr <imagen.png>            -> una línea por bloque de texto:   <texto>\t[x,y WxH]
//        ocr --words <imagen.png>    -> una línea por PALABRA:           <palabra>\t[x,y WxH]
// Coordenadas en píxeles FÍSICOS (Retina: punto lógico para cliclick = px / 2).
// Usa --words para clicar una palabra concreta dentro de una frase (el modo por línea solo da
// la caja de toda la línea, y su centro NO es la palabra buscada).
import Foundation
import AppKit
import Vision

var args = Array(CommandLine.arguments.dropFirst())
let wordMode = args.contains("--words")
args.removeAll { $0 == "--words" }
guard let path = args.first else {
    FileHandle.standardError.write("uso: ocr [--words] <imagen.png>\n".data(using: .utf8)!)
    exit(1)
}
guard let img = NSImage(contentsOfFile: path),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("no pude abrir \(path)\n".data(using: .utf8)!)
    exit(1)
}
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["es-ES", "en-US"]
request.usesLanguageCorrection = false
try VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])

let W = Double(cg.width), H = Double(cg.height)
func emit(_ text: String, _ b: CGRect) {
    let x = Int(b.origin.x * W), y = Int(H - (b.origin.y + b.size.height) * H)
    let w = Int(b.size.width * W), h = Int(b.size.height * H)
    print("\(text)\t[\(x),\(y) \(w)x\(h)]")
}
for obs in (request.results ?? []) {
    guard let top = obs.topCandidates(1).first else { continue }
    if !wordMode { emit(top.string, obs.boundingBox); continue }
    let s = top.string
    var i = s.startIndex
    while i < s.endIndex {
        while i < s.endIndex, s[i].isWhitespace { i = s.index(after: i) }
        if i >= s.endIndex { break }
        var j = i
        while j < s.endIndex, !s[j].isWhitespace { j = s.index(after: j) }
        let r = i..<j
        if let box = try? top.boundingBox(for: r) { emit(String(s[r]), box.boundingBox) }
        i = j
    }
}
