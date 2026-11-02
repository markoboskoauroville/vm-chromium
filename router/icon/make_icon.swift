// The icon of VM Router (Mantra): one cloud machine at the top, several session lines coming in from below and
// merging through one router node into a single line up to it; each session line its own colour, the version in a corner.
import AppKit
let v = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "1"
let S: CGFloat = 1024
let img = NSImage(size: NSSize(width: S, height: S))
img.lockFocus()
let bg = NSBezierPath(roundedRect: NSRect(x: 40, y: 40, width: S - 80, height: S - 80), xRadius: 200, yRadius: 200)
NSGradient(starting: NSColor(calibratedRed: 0.10, green: 0.12, blue: 0.14, alpha: 1),
           ending: NSColor(calibratedRed: 0.04, green: 0.05, blue: 0.06, alpha: 1))!.draw(in: bg, angle: -90)
// the machine (a browser window) at the top
let win = NSRect(x: 322, y: 690, width: 380, height: 220)
NSColor(calibratedWhite: 0.92, alpha: 1).setFill(); NSBezierPath(roundedRect: win, xRadius: 28, yRadius: 28).fill()
NSColor(calibratedRed: 0.20, green: 0.82, blue: 0.48, alpha: 1).setFill()
NSBezierPath(rect: NSRect(x: win.minX, y: win.maxY - 50, width: win.width, height: 22)).fill()
NSBezierPath(roundedRect: NSRect(x: win.minX, y: win.maxY - 50, width: win.width, height: 50), xRadius: 28, yRadius: 28).fill()
// the router node
let node = NSPoint(x: 512, y: 470)
// one line up from the node to the machine
NSColor(calibratedWhite: 0.92, alpha: 1).setStroke()
let up = NSBezierPath(); up.move(to: node); up.line(to: NSPoint(x: 512, y: win.minY)); up.lineWidth = 34; up.lineCapStyle = .round; up.stroke()
// sessions from below, each its own colour, into the node
let cols: [NSColor] = [.systemOrange, .systemTeal, .systemPink, .systemYellow]
for (i, x) in [190.0, 400.0, 624.0, 834.0].enumerated() {
    cols[i].setStroke()
    let p = NSBezierPath(); p.move(to: NSPoint(x: x, y: 150))
    p.curve(to: node, controlPoint1: NSPoint(x: x, y: 330), controlPoint2: NSPoint(x: 512, y: 330))
    p.lineWidth = 30; p.lineCapStyle = .round; p.stroke()
    cols[i].setFill(); NSBezierPath(ovalIn: NSRect(x: x - 42, y: 108, width: 84, height: 84)).fill()
}
NSColor.white.setFill(); NSBezierPath(ovalIn: NSRect(x: node.x - 70, y: node.y - 70, width: 140, height: 140)).fill()
NSColor(calibratedRed: 0.20, green: 0.82, blue: 0.48, alpha: 1).setFill()
NSBezierPath(ovalIn: NSRect(x: node.x - 36, y: node.y - 36, width: 72, height: 72)).fill()
let a: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 110, weight: .heavy), .foregroundColor: NSColor.systemOrange]
NSAttributedString(string: "v\(v)", attributes: a).draw(at: NSPoint(x: 730, y: 520))
img.unlockFocus()
let rep = NSBitmapImageRep(data: img.tiffRepresentation!)!
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "icon_1024.png"))
