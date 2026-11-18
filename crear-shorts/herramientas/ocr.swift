// ocr.swift — Lee texto de una captura de pantalla CON coordenadas.
// Uso: ocr <imagen.png>
// Salida: <texto>\t[x,y WxH] (píxeles físicos; en Retina, punto lógico = px/2)
import Foundation
import AppKit
import Vision

let args = CommandLine.arguments
guard args.count > 1 else {
    FileHandle.standardError.write("uso: ocr <imagen.png>\n".data(using: .utf8)!)
    exit(1)
}
let path = args[1]

guard let img = NSImage(contentsOfFile: path),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("no pude abrir \(path)\n".data(using: .utf8)!)
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["es-ES", "en-US"]
request.usesLanguageCorrection = false

let handler = VNImageRequestHandler(cgImage: cg, options: [:])
try handler.perform([request])

let W = Double(cg.width), H = Double(cg.height)
for obs in (request.results ?? []) {
    guard let top = obs.topCandidates(1).first else { continue }
    let b = obs.boundingBox
    let x = Int(b.origin.x * W)
    let y = Int(H - (b.origin.y + b.size.height) * H)
    let w = Int(b.size.width * W)
    let h = Int(b.size.height * H)
    print("\(top.string)\t[\(x),\(y) \(w)x\(h)]")
}
