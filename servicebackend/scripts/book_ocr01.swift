import AppKit
import Foundation
import PDFKit
import Vision

// OCR pages in memory. No page images are written to disk.
guard CommandLine.arguments.count == 4,
      let startPage = Int(CommandLine.arguments[2]),
      let pageCount = Int(CommandLine.arguments[3]),
      startPage >= 1, pageCount > 0,
      let document = PDFDocument(url: URL(fileURLWithPath: CommandLine.arguments[1])) else {
    fputs("usage: book_ocr01.swift PDF START_PAGE PAGE_COUNT\n", stderr)
    exit(2)
}

for pageNumber in startPage..<(startPage + pageCount) {
    guard let page = document.page(at: pageNumber - 1) else {
        fputs("invalid page \(pageNumber)\n", stderr)
        exit(2)
    }
    let bounds = page.bounds(for: .mediaBox)
    let targetWidth: CGFloat = 1800
    let targetSize = NSSize(width: targetWidth, height: targetWidth * bounds.height / bounds.width)
    let thumbnail = page.thumbnail(of: targetSize, for: .mediaBox)
    guard let cgImage = thumbnail.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        fputs("cannot rasterize page \(pageNumber)\n", stderr)
        exit(3)
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = true
    do {
        try VNImageRequestHandler(cgImage: cgImage).perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        let record: [String: Any] = ["page": pageNumber, "text": lines.joined(separator: "\n")]
        let data = try JSONSerialization.data(withJSONObject: record, options: [.fragmentsAllowed])
        if let line = String(data: data, encoding: .utf8) { print(line) }
    } catch {
        fputs("OCR failed on page \(pageNumber): \(error)\n", stderr)
        exit(4)
    }
}
