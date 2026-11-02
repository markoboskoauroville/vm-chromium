// ScreenView.swift: the VM's screen in the window: the picture, the mouse, the keys, and files dropped on it.
// Keys: ⌘ becomes Ctrl on the VM (⌘C, ⌘V, ⌘T, ⌘W, ⌘L work as on the Mac); ⌥ composes characters the Mac way
// and is sent as Alt only with keys that are not characters (⌥← etc.). ⌘Q stays the Mac's.
import AppKit

final class ScreenView: NSView {
    var rfb: RFB?
    var onDropFiles: (([URL]) -> Void)?
    var beforePaste: ((@escaping () -> Void) -> Void)?   // push the Mac clipboard to the VM, then send ⌘V
    private var buttons: UInt8 = 0
    private var downKeys: [UInt16: UInt32] = [:]
    private var mods: Set<UInt32> = []
    private var scrollAcc = CGFloat(0), scrollAccX = CGFloat(0)
    private var dropHighlight = false { didSet { needsDisplay = true } }

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.backgroundColor = NSColor(calibratedRed: 0.125, green: 0.13, blue: 0.14, alpha: 1).cgColor
        layer?.contentsGravity = .resize
        layer?.magnificationFilter = .linear
        registerForDraggedTypes([.fileURL])
        addTrackingArea(NSTrackingArea(rect: .zero, options: [.mouseMoved, .activeAlways, .inVisibleRect], owner: self))
    }
    required init?(coder: NSCoder) { fatalError() }

    override var acceptsFirstResponder: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override var isFlipped: Bool { true }

    // MARK: picture

    func refresh() {
        guard let rfb else { return }
        rfb.lock.lock()
        let w = rfb.width, h = rfb.height
        guard w > 0, h > 0 else { rfb.lock.unlock(); return }
        let data = rfb.pixels.withUnsafeBufferPointer { Data(buffer: $0) }
        rfb.lock.unlock()
        guard let provider = CGDataProvider(data: data as CFData),
              let img = CGImage(width: w, height: h, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: w * 4,
                                space: CGColorSpaceCreateDeviceRGB(),
                                bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue),
                                provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent) else { return }
        CATransaction.begin(); CATransaction.setDisableActions(true)
        layer?.contents = img
        CATransaction.commit()
    }

    override func draw(_ dirtyRect: NSRect) {
        if dropHighlight {
            NSColor.systemOrange.withAlphaComponent(0.9).setStroke()
            let p = NSBezierPath(rect: bounds.insetBy(dx: 3, dy: 3)); p.lineWidth = 6; p.stroke()
        }
    }

    // MARK: mouse

    private func vmPoint(_ e: NSEvent) -> (Int, Int) {
        guard let rfb, bounds.width > 0, bounds.height > 0 else { return (0, 0) }
        let p = convert(e.locationInWindow, from: nil)
        let x = Int((p.x / bounds.width) * CGFloat(rfb.width)), y = Int((p.y / bounds.height) * CGFloat(rfb.height))
        return (min(max(0, x), rfb.width - 1), min(max(0, y), rfb.height - 1))
    }
    private func send(_ e: NSEvent) { let (x, y) = vmPoint(e); rfb?.pointer(x: x, y: y, buttons: buttons) }

    override func mouseDown(with e: NSEvent) { window?.makeFirstResponder(self); buttons |= 1; send(e) }
    override func mouseUp(with e: NSEvent) { buttons &= ~1; send(e) }
    override func rightMouseDown(with e: NSEvent) { buttons |= 4; send(e) }
    override func rightMouseUp(with e: NSEvent) { buttons &= ~4; send(e) }
    override func otherMouseDown(with e: NSEvent) { buttons |= 2; send(e) }
    override func otherMouseUp(with e: NSEvent) { buttons &= ~2; send(e) }
    override func mouseMoved(with e: NSEvent) { send(e) }
    override func mouseDragged(with e: NSEvent) { send(e) }
    override func rightMouseDragged(with e: NSEvent) { send(e) }
    override func otherMouseDragged(with e: NSEvent) { send(e) }

    override func scrollWheel(with e: NSEvent) {
        // Trackpad deltas are fine-grained: one wheel click on the VM per ~12 points.
        let step: CGFloat = e.hasPreciseScrollingDeltas ? 12 : 1
        scrollAcc += e.scrollingDeltaY; scrollAccX += e.scrollingDeltaX
        let (x, y) = vmPoint(e)
        func click(_ bit: UInt8) {
            rfb?.pointer(x: x, y: y, buttons: buttons | bit); rfb?.pointer(x: x, y: y, buttons: buttons)
        }
        while scrollAcc >= step { click(8); scrollAcc -= step }       // up
        while scrollAcc <= -step { click(16); scrollAcc += step }     // down
        while scrollAccX >= step { click(32); scrollAccX -= step }    // left
        while scrollAccX <= -step { click(64); scrollAccX += step }   // right
    }

    // MARK: keys

    private static let special: [UInt16: UInt32] = [
        36: 0xff0d, 48: 0xff09, 51: 0xff08, 53: 0xff1b, 117: 0xffff, 76: 0xff8d,
        123: 0xff51, 124: 0xff53, 125: 0xff54, 126: 0xff52,
        115: 0xff50, 119: 0xff57, 116: 0xff55, 121: 0xff56, 114: 0xff63,
        122: 0xffbe, 120: 0xffbf, 99: 0xffc0, 118: 0xffc1, 96: 0xffc2, 97: 0xffc3,
        98: 0xffc4, 100: 0xffc5, 101: 0xffc6, 109: 0xffc7, 103: 0xffc8, 111: 0xffc9,
    ]
    static let ctrl: UInt32 = 0xffe3, shift: UInt32 = 0xffe1, alt: UInt32 = 0xffe9

    private func keysym(_ e: NSEvent) -> UInt32? {
        if let s = ScreenView.special[e.keyCode] { return s }
        let f = e.modifierFlags
        let chars = (f.contains(.command) || f.contains(.control)) ? e.charactersIgnoringModifiers?.lowercased() : e.characters
        guard let u = chars?.unicodeScalars.first else { return nil }
        if u.value < 0x20 { return nil }
        return u.value < 0x100 ? u.value : 0x0100_0000 + u.value
    }

    override func keyDown(with e: NSEvent) {
        guard let ks = keysym(e) else { return }
        let f = e.modifierFlags
        let altWrap = f.contains(.option) && ScreenView.special[e.keyCode] != nil
        let go = { [weak self] in
            guard let self else { return }
            if altWrap { self.rfb?.key(ScreenView.alt, down: true) }
            self.downKeys[e.keyCode] = ks
            self.rfb?.key(ks, down: true)
            if altWrap { self.rfb?.key(ScreenView.alt, down: false) }
        }
        if f.contains(.command) && ks == 0x76 && !e.isARepeat, let beforePaste { beforePaste(go) } else { go() }   // ⌘V
    }

    override func keyUp(with e: NSEvent) {
        if let ks = downKeys.removeValue(forKey: e.keyCode) { rfb?.key(ks, down: false) }
    }

    override func flagsChanged(with e: NSEvent) {
        let f = e.modifierFlags
        var want: Set<UInt32> = []
        if f.contains(.command) || f.contains(.control) { want.insert(ScreenView.ctrl) }
        if f.contains(.shift) { want.insert(ScreenView.shift) }
        for k in want.subtracting(mods) { rfb?.key(k, down: true) }
        for k in mods.subtracting(want) { rfb?.key(k, down: false) }
        mods = want
    }

    /// Everything with ⌘ goes to the VM, except ⌘Q (quit), ⌃⌘F (full screen) and ⌘H (hide).
    override func performKeyEquivalent(with e: NSEvent) -> Bool {
        guard window?.firstResponder === self, e.type == .keyDown else { return false }
        let k = e.charactersIgnoringModifiers?.lowercased()
        if e.modifierFlags.contains(.command) && (k == "q" || k == "h" || (k == "f" && e.modifierFlags.contains(.control))) { return false }
        keyDown(with: e); return true
    }

    /// The window lost the focus: let go of everything held, so no key stays down on the VM.
    func releaseAll() {
        for (_, ks) in downKeys { rfb?.key(ks, down: false) }
        for k in mods { rfb?.key(k, down: false) }
        downKeys = [:]; mods = []
        if buttons != 0 { buttons = 0; rfb?.pointer(x: 0, y: 0, buttons: 0) }
    }

    // MARK: drag and drop

    override func draggingEntered(_ s: NSDraggingInfo) -> NSDragOperation { dropHighlight = true; return .copy }
    override func draggingExited(_ s: NSDraggingInfo?) { dropHighlight = false }
    override func performDragOperation(_ s: NSDraggingInfo) -> Bool {
        dropHighlight = false
        let urls = (s.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL]) ?? []
        guard !urls.isEmpty else { return false }
        onDropFiles?(urls); return true
    }
}
