// Renders the ladder/smoke test image: ticket number 7291, destination "Galway harbour, pier 3", five blue crates.
// NSImage.lockFocus draws at the screen backing scale. On a Retina Mac the output is 2560x1600, not 1280x800.
// The committed ticket-1280.png was made with:
//   swift make_image.swift ticket.png && sips -z 800 1280 ticket.png --out ticket-1280.png
// sha256(ticket-1280.png) = bcaa68de4570a2738b6f7c2fec72b3b1d367bcbc28f61a5da0028dcd234c51ec (macOS 26.5, M4). Use the committed PNG to repeat the runs.
import AppKit
let W = 1280, H = 800
let img = NSImage(size: NSSize(width: W, height: H))
img.lockFocus()
NSColor(calibratedRed: 0.96, green: 0.94, blue: 0.88, alpha: 1).setFill(); NSRect(x: 0, y: 0, width: W, height: H).fill()
let title: [NSAttributedString.Key: Any] = [.font: NSFont.boldSystemFont(ofSize: 64), .foregroundColor: NSColor.black]
("WAREHOUSE TICKET 7291" as NSString).draw(at: NSPoint(x: 60, y: 660), withAttributes: title)
let body: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 40), .foregroundColor: NSColor.darkGray]
("Destination: Galway harbour, pier 3" as NSString).draw(at: NSPoint(x: 60, y: 570), withAttributes: body)
("Crates below: count them" as NSString).draw(at: NSPoint(x: 60, y: 500), withAttributes: body)
let colours: [NSColor] = [.systemBlue, .systemBlue, .systemBlue, .systemBlue, .systemBlue]
for (i, c) in colours.enumerated() { c.setFill(); NSBezierPath(roundedRect: NSRect(x: 80 + i * 230, y: 120, width: 170, height: 300), xRadius: 16, yRadius: 16).fill() }
img.unlockFocus()
let rep = NSBitmapImageRep(data: img.tiffRepresentation!)!
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
