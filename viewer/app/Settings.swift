// Settings.swift: v6 (Marko, 2.11.2026): "for the top bar which is hiding, I don't need anything from the top bar. I just
// need in the upper left corner one setting button when all settings will be available. And this is transparent overlay
// over the window and it doesn't let the mouse clicks goes through the remote session." Inside: the keys held for the
// Mac (F1 Speechify, F2 Voice to Text: "I can choose one or both to not pass through the remote session"), full screen,
// reconnect, close window, quit.
import AppKit

/// A view that swallows every click and scroll, so nothing over it reaches the VM's screen underneath.
class Solid: NSView {
    override func mouseDown(with e: NSEvent) {}
    override func mouseUp(with e: NSEvent) {}
    override func rightMouseDown(with e: NSEvent) {}
    override func rightMouseUp(with e: NSEvent) {}
    override func otherMouseDown(with e: NSEvent) {}
    override func scrollWheel(with e: NSEvent) {}
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

/// A word that is a button: grey, lit (white or green) when on, underlined with a hand pointer on hover.
final class WordButton: NSButton {
    var lit = false { didSet { paint() } }
    var litColor = NSColor.systemGreen { didSet { paint() } }
    private var hover = false { didSet { paint() } }
    convenience init(_ title: String, _ target: AnyObject, _ action: Selector) {
        self.init(title: title, target: target, action: action)
        isBordered = false; setButtonType(.momentaryChange)
        setAccessibilityLabel(title)
        addTrackingArea(NSTrackingArea(rect: .zero, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect], owner: self))
        paint()
    }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func resetCursorRects() { addCursorRect(bounds, cursor: .pointingHand) }
    override func mouseEntered(with e: NSEvent) { hover = true }
    override func mouseExited(with e: NSEvent) { hover = false }
    func paint() {
        var a: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 13, weight: .semibold),
                                                .foregroundColor: lit ? litColor : (hover ? NSColor.white : NSColor(white: 0.62, alpha: 1))]
        if hover { a[.underlineStyle] = NSUnderlineStyle.single.rawValue }
        attributedTitle = NSAttributedString(string: title, attributes: a)
    }
}

final class SettingsOverlay: Solid {
    weak var app: App?
    private let pill = NSVisualEffectView()
    private let gear = NSButton()
    let tip = NSTextField(labelWithString: "")            // a short note beside the gear (upload, clipboard, not connected)
    let permissions = WordButton()
    private let panel = NSVisualEffectView()
    let statusLine = NSTextField(labelWithString: "connecting…")
    let userField = NSTextField()
    let passField = NSSecureTextField()
    private var keyButtons: [UInt16: (WordButton, WordButton)] = [:]
    var isOpen: Bool { !panel.isHidden }

    static let GEAR_W: CGFloat = 34
    static let macKeys: [(String, UInt16, String)] = [("F1", 122, "Speechify"), ("F2", 120, "Voice to Text")]

    init(app: App) {
        self.app = app
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false

        // v6b (Marko, 2.11.2026: "next to [the power button] add setting button ... these settings are for virtual machine
        // viewer, not for remote session"): the gear sits at the bottom-right corner, on the VM's status line, right
        // after its power button (the status bar keeps the last GEAR_W points free for it)
        gear.image = NSImage(systemSymbolName: "gearshape.fill", accessibilityDescription: "SETTINGS")?
            .withSymbolConfiguration(.init(pointSize: 16, weight: .semibold))
        gear.isBordered = false; gear.contentTintColor = .white
        gear.target = self; gear.action = #selector(toggle)
        gear.setAccessibilityLabel("SETTINGS")
        gear.translatesAutoresizingMaskIntoConstraints = false
        addSubview(gear)
        // a note above the gear only when there is one (upload, clipboard, not connected, PERMISSIONS)
        pill.material = .hudWindow; pill.blendingMode = .withinWindow; pill.state = .active
        pill.wantsLayer = true; pill.layer?.cornerRadius = 12; pill.isHidden = true
        tip.font = .systemFont(ofSize: 12, weight: .semibold); tip.textColor = .systemOrange
        tip.lineBreakMode = .byTruncatingMiddle; tip.isHidden = true
        tip.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        permissions.title = "PERMISSIONS"; permissions.target = self; permissions.action = #selector(openPermissions)
        permissions.setAccessibilityLabel("PERMISSIONS")
        permissions.lit = true; permissions.litColor = .systemOrange; permissions.isHidden = true
        let notes = NSStackView(views: [tip, permissions])
        notes.orientation = .horizontal; notes.spacing = 8
        notes.edgeInsets = NSEdgeInsets(top: 0, left: 10, bottom: 0, right: 10)
        pill.addSubview(notes); notes.translatesAutoresizingMaskIntoConstraints = false
        pill.translatesAutoresizingMaskIntoConstraints = false
        addSubview(pill)
        NSLayoutConstraint.activate([
            gear.widthAnchor.constraint(equalToConstant: SettingsOverlay.GEAR_W), gear.heightAnchor.constraint(equalToConstant: 30),
            // v11: kept 12 points in from the corner, where macOS takes the click for resizing the window
            gear.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -12), gear.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -12),
            notes.leadingAnchor.constraint(equalTo: pill.leadingAnchor), notes.trailingAnchor.constraint(equalTo: pill.trailingAnchor),
            notes.topAnchor.constraint(equalTo: pill.topAnchor), notes.bottomAnchor.constraint(equalTo: pill.bottomAnchor),
            pill.heightAnchor.constraint(equalToConstant: 24),
            pill.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -6),
            pill.bottomAnchor.constraint(equalTo: gear.topAnchor, constant: -6),
            pill.widthAnchor.constraint(lessThanOrEqualToConstant: 520)])

        // the panel above the gear
        panel.material = .hudWindow; panel.blendingMode = .withinWindow; panel.state = .active
        panel.wantsLayer = true; panel.layer?.cornerRadius = 10; panel.isHidden = true
        panel.translatesAutoresizingMaskIntoConstraints = false
        let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 10
        stack.edgeInsets = NSEdgeInsets(top: 12, left: 14, bottom: 12, right: 14)
        stack.translatesAutoresizingMaskIntoConstraints = false
        panel.addSubview(stack)

        let name = label("\(APP_NAME)  v\(VERSION)", 13, .white, .semibold)
        statusLine.font = .systemFont(ofSize: 12, weight: .semibold); statusLine.textColor = .secondaryLabelColor
        stack.addArrangedSubview(name); stack.addArrangedSubview(statusLine)
        stack.addArrangedSubview(hairline())

        // v11 (Marko, 5.11.2026): username and password inside the gear; SAVE AND CONNECT stores and connects
        stack.addArrangedSubview(label("LOGIN  (chromium-vm, \(VNC_HOST):\(VNC_PORT))", 11, NSColor(white: 0.55, alpha: 1), .medium))
        for (t, f, ph) in [("USERNAME", userField as NSTextField, "ubuntu"), ("PASSWORD", passField as NSTextField, "the VM's VNC password")] {
            f.placeholderString = ph; f.font = .systemFont(ofSize: 13); f.setAccessibilityLabel(t)
            f.widthAnchor.constraint(equalToConstant: 190).isActive = true
            let n = label(t, 13, .white, .semibold); n.widthAnchor.constraint(equalToConstant: 96).isActive = true
            stack.addArrangedSubview(row([n, f]))
        }
        userField.stringValue = App.username
        passField.target = self; passField.action = #selector(saveLogin)
        stack.addArrangedSubview(row([WordButton("SAVE AND CONNECT", self, #selector(saveLogin))]))
        stack.addArrangedSubview(hairline())

        // Marko: "I can enable or disable my F1 and F2 to be on the Mac OS or in the remote session": per key, MAC | VM
        stack.addArrangedSubview(label("WHERE THE KEYS GO", 11, NSColor(white: 0.55, alpha: 1), .medium))
        for (k, code, who) in SettingsOverlay.macKeys {
            let mac = WordButton("MAC", self, #selector(keyToMac(_:))), vm = WordButton("VM", self, #selector(keyToVM(_:)))
            mac.tag = Int(code); vm.tag = Int(code)
            mac.setAccessibilityLabel("\(k) MAC"); vm.setAccessibilityLabel("\(k) VM")
            keyButtons[code] = (mac, vm)
            let name = label("\(k)  \(who)", 13, .white, .semibold)
            name.widthAnchor.constraint(equalToConstant: 150).isActive = true
            stack.addArrangedSubview(row([name, mac, pipe(), vm]))
        }
        stack.addArrangedSubview(hairline())
        stack.addArrangedSubview(row([WordButton("FULL SCREEN", self, #selector(fullScreen)), pipe(),
                                      WordButton("RECONNECT", self, #selector(reconnect))]))
        stack.addArrangedSubview(hairline())
        stack.addArrangedSubview(row([WordButton("CLOSE WINDOW", self, #selector(closeWindow)), pipe(),
                                      WordButton("QUIT", self, #selector(quit))]))
        addSubview(panel)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: panel.leadingAnchor), stack.trailingAnchor.constraint(equalTo: panel.trailingAnchor),
            stack.topAnchor.constraint(equalTo: panel.topAnchor), stack.bottomAnchor.constraint(equalTo: panel.bottomAnchor),
            panel.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -6), panel.bottomAnchor.constraint(equalTo: gear.topAnchor, constant: -6),
            panel.widthAnchor.constraint(greaterThanOrEqualToConstant: 330)])
        refreshKeys()
    }
    required init?(coder: NSCoder) { fatalError() }

    override var isFlipped: Bool { true }
    /// Only the pill and the open panel take the mouse; the rest of this (sizing) view lets clicks through to the VM.
    override func hitTest(_ p: NSPoint) -> NSView? {
        let local = convert(p, from: superview)
        for v in [panel, pill, gear] where !v.isHidden && v.frame.contains(local) {
            return super.hitTest(p) ?? self
        }
        return nil
    }

    private func label(_ s: String, _ size: CGFloat, _ c: NSColor, _ w: NSFont.Weight) -> NSTextField {
        let l = NSTextField(labelWithString: s); l.font = .systemFont(ofSize: size, weight: w); l.textColor = c; return l
    }
    private func pipe() -> NSTextField { label("|", 13, NSColor(white: 0.4, alpha: 1), .regular) }
    private func row(_ v: [NSView]) -> NSStackView { let s = NSStackView(views: v); s.orientation = .horizontal; s.spacing = 8; return s }
    private func hairline() -> NSView {
        let l = NSBox(); l.boxType = .custom; l.borderWidth = 0; l.fillColor = NSColor(white: 1, alpha: 0.15)
        l.translatesAutoresizingMaskIntoConstraints = false
        l.heightAnchor.constraint(equalToConstant: 1).isActive = true
        l.widthAnchor.constraint(equalToConstant: 300).isActive = true
        return l
    }

    func refreshKeys() {
        let held = App.heldKeys
        for (code, (mac, vm)) in keyButtons { mac.lit = held.contains(code); vm.lit = !held.contains(code) }
        permissions.isHidden = held.isEmpty || CGPreflightPostEventAccess()
        showNotes()
    }

    @objc func saveLogin() {
        let pw = passField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        App.username = userField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        if !pw.isEmpty { app?.savePassword(pw) }
        passField.stringValue = ""
        close(); app?.reconnect()
    }
    func openLogin() {
        panel.isHidden = false; refreshKeys()
        DispatchQueue.main.async { [weak self] in guard let self else { return }; self.window?.makeFirstResponder(self.passField) }
    }
    @objc func toggle() { panel.isHidden.toggle(); refreshKeys() }
    func close() { panel.isHidden = true; showNotes() }
    @objc func keyToMac(_ b: NSButton) { setHeld(UInt16(b.tag), true) }
    @objc func keyToVM(_ b: NSButton) { setHeld(UInt16(b.tag), false) }
    func setHeld(_ c: UInt16, _ on: Bool) {
        var held = App.heldKeys
        if on { held.insert(c) } else { held.remove(c) }
        App.heldKeys = held; app?.screen.heldForMac = held
        refreshKeys()
    }
    /// the note pill shows only when it has something, and never over the open panel
    func showNotes() { pill.isHidden = !isOpen ? (tip.isHidden && permissions.isHidden) : true }
    @objc func openPermissions() {
        _ = CGRequestPostEventAccess()
        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!)
    }
    @objc func fullScreen() { close(); app?.window.toggleFullScreen(nil) }
    @objc func reconnect() { close(); app?.reconnect() }
    @objc func closeWindow() { close(); app?.window.orderOut(nil) }
    @objc func quit() { NSApp.terminate(nil) }

    /// the note beside the gear: shown while there is one
    func setTip(_ s: String, color: NSColor = .systemOrange) {
        tip.stringValue = s; tip.textColor = color; tip.isHidden = s.isEmpty; showNotes()
    }
}
