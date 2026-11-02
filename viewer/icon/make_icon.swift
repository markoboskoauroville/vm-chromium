// The icon of Chromium Virtual Machine (Mantra): a browser window floating under a cloud, the version in a corner.
import AppKit
let v = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "1"
let S: CGFloat = 1024
let img = NSImage(size: NSSize(width: S, height: S))
img.lockFocus()
let bg = NSBezierPath(roundedRect: NSRect(x: 40, y: 40, width: S - 80, height: S - 80), xRadius: 200, yRadius: 200)
NSGradient(starting: NSColor(calibratedRed: 0.10, green: 0.16, blue: 0.30, alpha: 1),
           ending: NSColor(calibratedRed: 0.04, green: 0.06, blue: 0.12, alpha: 1))!.draw(in: bg, angle: -90)
// the cloud
NSColor(calibratedWhite: 1, alpha: 0.92).setFill()
for (x, y, r) in [(330.0, 735.0, 95.0), (450.0, 790.0, 130.0), (590.0, 760.0, 110.0), (690.0, 720.0, 80.0)] as [(CGFloat, CGFloat, CGFloat)] {
    NSBezierPath(ovalIn: NSRect(x: x - r, y: y - r, width: 2 * r, height: 2 * r)).fill()
}
NSBezierPath(roundedRect: NSRect(x: 235, y: 640, width: 535, height: 100), xRadius: 50, yRadius: 50).fill()
// the browser window
let win = NSRect(x: 170, y: 170, width: 684, height: 430)
NSColor(calibratedRed: 0.94, green: 0.95, blue: 0.97, alpha: 1).setFill()
NSBezierPath(roundedRect: win, xRadius: 36, yRadius: 36).fill()
NSColor(calibratedRed: 0.80, green: 0.86, blue: 0.96, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: win.minX, y: win.maxY - 92, width: win.width, height: 92), xRadius: 36, yRadius: 36).fill()
NSBezierPath(rect: NSRect(x: win.minX, y: win.maxY - 92, width: win.width, height: 40)).fill()
NSColor.white.setFill()
NSBezierPath(roundedRect: NSRect(x: win.minX + 30, y: win.maxY - 72, width: 200, height: 52), xRadius: 14, yRadius: 14).fill()
NSColor(calibratedRed: 0.88, green: 0.90, blue: 0.94, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: win.minX + 40, y: win.maxY - 160, width: win.width - 80, height: 46), xRadius: 23, yRadius: 23).fill()
// a round "browser" mark in the page: three arcs (not any company's logo)
let c = NSPoint(x: win.midX, y: win.minY + 150), R: CGFloat = 92
for (i, col) in [NSColor.systemRed, .systemYellow, .systemGreen].enumerated() {
    col.setStroke()
    let p = NSBezierPath(); p.appendArc(withCenter: c, radius: R, startAngle: CGFloat(90 + i * 120), endAngle: CGFloat(200 + i * 120))
    p.lineWidth = 44; p.stroke()
}
NSColor.systemBlue.setFill(); NSBezierPath(ovalIn: NSRect(x: c.x - 40, y: c.y - 40, width: 80, height: 80)).fill()
// the version (version-visible.md)
let a: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 120, weight: .heavy), .foregroundColor: NSColor.systemOrange]
NSAttributedString(string: "v\(v)", attributes: a).draw(at: NSPoint(x: 700, y: 60))
img.unlockFocus()
let rep = NSBitmapImageRep(data: img.tiffRepresentation!)!
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "icon_1024.png"))
