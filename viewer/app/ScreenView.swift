// ScreenView.swift: the VM's screen in the window: the picture, the mouse, the keys, and files dropped on it.
// Keys: ⌘ becomes Ctrl on the VM (⌘C, ⌘V, ⌘T, ⌘W, ⌘L work as on the Mac); ⌥ composes characters the Mac way
// and is sent as Alt only with keys that are not characters (⌥← etc.). ⌘Q stays the Mac's.
import AppKit

final class ScreenView: NSView {
    var rfb: RFB?
    var onDropFiles: (([URL]) -> Void)?
    var beforePaste: ((@escaping () -> Void) -> Void)?   // push the Mac clipboard to the VM, then send ⌘V
    var heldForMac: Set<UInt16> = []                       // key codes never sent to the VM (F1 122, F2 120)
    var onMacKey: ((UInt16) -> Void)?                       // one of them was pressed: hand it to the Mac
    var onClick: (() -> Void)?                              // a click on the picture (closes the settings panel)
    static let ownMark: Int64 = 0x4D414E54                  // "MANT": a key this app pressed into the Mac itself
    var onTypeText: ((String) -> Void)?                     // text a Mac app wrote into this view: paste it on the VM
    private var typed = ""                                  // what Mac apps wrote here (read back by them as the value)

    // MARK: a text area for the Mac's dictation (v8, Marko 2.11.2026: "Text simply does not arrive"). Voice to Text and
    // Speechify write into the focused text field through Accessibility (AXSelectedText) and read the value back; a
    // plain view is no field, so they wrote nowhere. The picture now says it is a text area: what is written here goes
    // to the VM's clipboard and is pasted where the VM's cursor is.
    override func isAccessibilityElement() -> Bool { true }
    override func accessibilityRole() -> NSAccessibility.Role? { .textArea }
    override func accessibilityRoleDescription() -> String? { "text area" }
    override func accessibilityLabel() -> String? { "Chromium VM screen" }
    override func isAccessibilityFocused() -> Bool { window?.firstResponder === self }
    override func accessibilityValue() -> Any? { typed }
    override func setAccessibilityValue(_ v: Any?) {
        guard let new = v as? String else { return }
        let add = new.hasPrefix(typed) ? String(new.dropFirst(typed.count)) : new
        typed = new; if !add.isEmpty { onTypeText?(add) }
    }
    override func accessibilitySelectedText() -> String? { "" }
    override func setAccessibilitySelectedText(_ t: String?) {
        guard let t, !t.isEmpty else { return }
        typed += t; if typed.count > 4000 { typed = String(typed.suffix(2000)) }
        onTypeText?(t)
    }
    override func accessibilitySelectedTextRange() -> NSRange { NSRange(location: typed.utf16.count, length: 0) }
    override func accessibilityNumberOfCharacters() -> Int { typed.utf16.count }
    override func isAccessibilitySelectorAllowed(_ s: Selector) -> Bool {
        if s == NSSelectorFromString("setAccessibilitySelectedText:") || s == NSSelectorFromString("setAccessibilityValue:") { return true }
        return super.isAccessibilitySelectorAllowed(s)
    }

    /// ⌃V on the VM (⌘ is Ctrl there), whatever modifiers are held on the Mac
    func pasteOnVM() {
        let held = mods
        for k in held { rfb?.key(k, down: false) }
        rfb?.key(ScreenView.ctrl, down: true); rfb?.key(0x76, down: true)
        rfb?.key(0x76, down: false); rfb?.key(ScreenView.ctrl, down: false)
        for k in held { rfb?.key(k, down: true) }
    }
    private var buttons: UInt8 = 0
    private var downKeys: [UInt16: UInt32] = [:]
    private var mods: Set<UInt32> = []
    private var scrollAcc = CGFloat(0), scrollAccX = CGFloat(0)
    private var dropHighlight = false {
        didSet { picture.borderWidth = dropHighlight ? 6 : 0 }
    }
    // v19 (Marko, 5.11.2026: "never stretch or squish image, always resize it in original aspect ratio"): the picture
    // lives on its own sublayer, aspect-fitted and centred. Before, it was the view's own layer, which AppKit scales on
    // both axes (layerContentsPlacement) whenever it redraws or the window is resized live.
    let picture = CALayer()

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.backgroundColor = NSColor(calibratedRed: 0.125, green: 0.13, blue: 0.14, alpha: 1).cgColor
        layerContentsRedrawPolicy = .never
        picture.contentsGravity = .resizeAspect
        picture.magnificationFilter = .linear
        picture.borderColor = NSColor.systemOrange.withAlphaComponent(0.9).cgColor
        picture.actions = ["contents": NSNull(), "bounds": NSNull(), "position": NSNull(), "frame": NSNull()]
        layer?.addSublayer(picture)
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
        picture.contents = img
        CATransaction.commit()
    }

    override func layout() {
        super.layout()
        CATransaction.begin(); CATransaction.setDisableActions(true)
        picture.frame = bounds
        CATransaction.commit()
    }

    // MARK: mouse

    private func vmPoint(_ e: NSEvent) -> (Int, Int) {
        guard let rfb, bounds.width > 0, bounds.height > 0 else { return (0, 0) }
        let p = convert(e.locationInWindow, from: nil)
        // v13: the picture sits aspect-fitted (centred, bars at the sides or top and bottom)
        let k = min(bounds.width / CGFloat(rfb.width), bounds.height / CGFloat(rfb.height))
        let ox = (bounds.width - CGFloat(rfb.width) * k) / 2, oy = (bounds.height - CGFloat(rfb.height) * k) / 2
        let x = Int((p.x - ox) / k), y = Int((p.y - oy) / k)
        return (min(max(0, x), rfb.width - 1), min(max(0, y), rfb.height - 1))
    }
    private func send(_ e: NSEvent) { let (x, y) = vmPoint(e); rfb?.pointer(x: x, y: y, buttons: buttons) }

    override func mouseDown(with e: NSEvent) { onClick?(); window?.makeFirstResponder(self); buttons |= 1; send(e) }
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
    static let ctrl: UInt32 = 0xffe3, shift: UInt32 = 0xffe1, alt: UInt32 = 0xffe9, superL: UInt32 = 0xffeb

    private func keysym(_ e: NSEvent) -> UInt32? {
        if let s = ScreenView.special[e.keyCode] { return s }
        let f = e.modifierFlags
        let chars = (f.contains(.command) || f.contains(.control)) ? e.charactersIgnoringModifiers?.lowercased() : e.characters
        guard let u = chars?.unicodeScalars.first else { return nil }
        if u.value < 0x20 { return nil }
        return u.value < 0x100 ? u.value : 0x0100_0000 + u.value
    }

    override func keyDown(with e: NSEvent) {
        // F1 / F2 held for the Mac (Marko, 2.11.2026: "When I'm transcribing I'm pressing F1 or F2 ... it needs to be
        // blocked from sending it"): never to the VM; handed to Speechify / Voice to Text on the Mac
        if heldForMac.contains(e.keyCode) {
            if !e.isARepeat && e.cgEvent?.getIntegerValueField(.eventSourceUserData) != ScreenView.ownMark { onMacKey?(e.keyCode) }
            return
        }
        // ⌘V with text on the Mac clipboard (v9): the text itself goes to the VM and is pasted the way the window in front
        // takes it (vm-agent paste_text). Read now: Speechify and Voice to Text put the old clipboard back right after
        // their ⌘V, and their ⌘V comes without a ⌘ flagsChanged, so a forwarded key arrived as a bare "v" (test 2.11.2026).
        if e.modifierFlags.contains(.command) && e.keyCode == 9 && !e.isARepeat,
           let text = NSPasteboard.general.string(forType: .string), !text.isEmpty, let onTypeText {
            onTypeText(text); return
        }
        guard let ks = keysym(e) else { return }
        let f = e.modifierFlags
        // ⌘Tab = Super+Tab on the VM: the one key that switches its three screens (Marko, 2.11.2026). ⌘ is held as
        // Ctrl there, so Ctrl is let go around it.
        if f.contains(.command) && e.keyCode == 48 {
            let held = mods.contains(ScreenView.ctrl)
            if held { rfb?.key(ScreenView.ctrl, down: false) }
            rfb?.key(ScreenView.superL, down: true); rfb?.key(0xff09, down: true)
            rfb?.key(0xff09, down: false); rfb?.key(ScreenView.superL, down: false)
            if held { rfb?.key(ScreenView.ctrl, down: true) }
            return
        }
        // ⌥ goes as Alt with keys that are not characters, and with every key while ⌃ is held too (⌃⌥C, ⌃⌥U ...:
        // the Rectangle keys of the VM's window manager), since ⌃⌥ + letter composes nothing.
        let altWrap = f.contains(.option) && (ScreenView.special[e.keyCode] != nil || f.contains(.control))
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
