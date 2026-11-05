// Grips.swift: v16 (Marko, 5.11.2026): "in a bottom-right corner, make one corner with lines ... when I click on that one,
// I can move my window around. On the left side, put the one for resizing. Same icon, small corner, hash."
// Two small hatched corners over the picture: bottom-right MOVES the window, bottom-left RESIZES it (the top-right corner
// stays where it is). Their clicks never reach the VM.
import AppKit

final class CornerGrip: NSView {
    enum Kind { case move, resize }
    let kind: Kind
    static let SIZE: CGFloat = 16
    private var startFrame = NSRect.zero
    private var startMouse = NSPoint.zero

    init(_ kind: Kind) {
        self.kind = kind
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        setAccessibilityElement(true)
        setAccessibilityRole(.button)
        setAccessibilityLabel(kind == .move ? "MOVE WINDOW" : "RESIZE WINDOW")
        toolTip = kind == .move ? "drag to move the window" : "drag to resize the window"
    }
    required init?(coder: NSCoder) { fatalError() }

    override var isFlipped: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override var mouseDownCanMoveWindow: Bool { false }

    /// v17 (Marko, 5.11.2026: "Only one line ... gray color, so it's barely visible"): one long diagonal line across the
    /// corner, no backing; the left one is the mirror of the right one
    override func draw(_ r: NSRect) {
        let s = bounds.width
        NSColor(white: 0.5, alpha: 0.45).setStroke()
        let p = NSBezierPath(); p.lineWidth = 1.5; p.lineCapStyle = .round
        if kind == .move { p.move(to: NSPoint(x: 1.5, y: s - 1.5)); p.line(to: NSPoint(x: s - 1.5, y: 1.5)) }
        else { p.move(to: NSPoint(x: 1.5, y: 1.5)); p.line(to: NSPoint(x: s - 1.5, y: s - 1.5)) }
        p.stroke()
    }

    override func resetCursorRects() {
        if kind == .move { addCursorRect(bounds, cursor: .openHand); return }
        if #available(macOS 15, *) { addCursorRect(bounds, cursor: .frameResize(position: .bottomLeft, directions: .all)) }
        else { addCursorRect(bounds, cursor: .crosshair) }
    }

    override func mouseDown(with e: NSEvent) {
        guard let w = window, !w.styleMask.contains(.fullScreen) else { return }
        if kind == .move { NSCursor.closedHand.set(); w.performDrag(with: e); return }
        startFrame = w.frame; startMouse = NSEvent.mouseLocation
    }

    override func mouseDragged(with e: NSEvent) {
        guard kind == .resize, let w = window, !w.styleMask.contains(.fullScreen) else { return }
        let m = NSEvent.mouseLocation
        let minW = w.minSize.width, minH = w.minSize.height
        // the top-right corner stays put: x and the bottom edge follow the mouse
        let width = max(minW, startFrame.width - (m.x - startMouse.x))
        let height = max(minH, startFrame.height - (m.y - startMouse.y))
        let f = NSRect(x: startFrame.maxX - width, y: startFrame.maxY - height, width: width, height: height)
        w.setFrame(f, display: true)
    }

    override func mouseUp(with e: NSEvent) { window?.invalidateCursorRects(for: self) }
    override func rightMouseDown(with e: NSEvent) {}
    override func scrollWheel(with e: NSEvent) {}
}
