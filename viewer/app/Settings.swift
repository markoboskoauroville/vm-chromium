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
    private var keyButtons: [UInt16: WordButton] = [:]
    var isOpen: Bool { !panel.isHidden }

    static let macKeys: [(String, UInt16, String)] = [("F1", 122, "Speechify"), ("F2", 120, "Voice to Text")]

    init(app: App) {
        self.app = app
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false

        // the pill: the gear, then a note only when there is one
        pill.material = .hudWindow; pill.blendingMode = .withinWindow; pill.state = .active
        pill.wantsLayer = true; pill.layer?.cornerRadius = 15; pill.alphaValue = 0.85
        gear.image = NSImage(systemSymbolName: "gearshape.fill", accessibilityDescription: "SETTINGS")
        gear.isBordered = false; gear.contentTintColor = NSColor(white: 0.85, alpha: 1)
        gear.target = self; gear.action = #selector(toggle)
        gear.setAccessibilityLabel("SETTINGS")
        tip.font = .systemFont(ofSize: 12, weight: .semibold); tip.textColor = .systemOrange
        tip.lineBreakMode = .byTruncatingMiddle; tip.isHidden = true
        tip.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        permissions.title = "PERMISSIONS"; permissions.target = self; permissions.action = #selector(openPermissions)
        permissions.setAccessibilityLabel("PERMISSIONS")
        permissions.lit = true; permissions.litColor = .systemOrange; permissions.isHidden = true
        let top = NSStackView(views: [gear, tip, permissions])
        top.orientation = .horizontal; top.spacing = 8
        top.edgeInsets = NSEdgeInsets(top: 0, left: 7, bottom: 0, right: 7)
        pill.addSubview(top); top.translatesAutoresizingMaskIntoConstraints = false
        pill.translatesAutoresizingMaskIntoConstraints = false
        addSubview(pill)
        NSLayoutConstraint.activate([
            gear.widthAnchor.constraint(equalToConstant: 18), gear.heightAnchor.constraint(equalToConstant: 18),
            top.leadingAnchor.constraint(equalTo: pill.leadingAnchor), top.trailingAnchor.constraint(equalTo: pill.trailingAnchor),
            top.topAnchor.constraint(equalTo: pill.topAnchor), top.bottomAnchor.constraint(equalTo: pill.bottomAnchor),
            pill.heightAnchor.constraint(equalToConstant: 30),
            pill.leadingAnchor.constraint(equalTo: leadingAnchor), pill.topAnchor.constraint(equalTo: topAnchor),
            pill.widthAnchor.constraint(lessThanOrEqualToConstant: 520)])

        // the panel under the gear
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

        stack.addArrangedSubview(label("KEYS HELD FOR THIS MAC (not sent to the VM)", 11, NSColor(white: 0.55, alpha: 1), .medium))
        var keys: [NSView] = []
        for (i, (k, code, who)) in SettingsOverlay.macKeys.enumerated() {
            if i > 0 { keys.append(label("|", 13, NSColor(white: 0.4, alpha: 1), .regular)) }
            let b = WordButton("\(k)  \(who)", self, #selector(toggleKey(_:)))
            b.tag = Int(code); b.setAccessibilityLabel(k)
            keyButtons[code] = b; keys.append(b)
        }
        stack.addArrangedSubview(row(keys))
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
            panel.leadingAnchor.constraint(equalTo: leadingAnchor), panel.topAnchor.constraint(equalTo: pill.bottomAnchor, constant: 6),
            panel.widthAnchor.constraint(greaterThanOrEqualToConstant: 330)])
        refreshKeys()
    }
    required init?(coder: NSCoder) { fatalError() }

    override var isFlipped: Bool { true }
    /// Only the pill and the open panel take the mouse; the rest of this (sizing) view lets clicks through to the VM.
    override func hitTest(_ p: NSPoint) -> NSView? {
        let local = convert(p, from: superview)
        for v in [panel, pill] where !v.isHidden && v.frame.contains(local) {
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
        for (code, b) in keyButtons { b.lit = held.contains(code) }
        permissions.isHidden = held.isEmpty || CGPreflightPostEventAccess()
    }

    @objc func toggle() { panel.isHidden.toggle(); refreshKeys() }
    func close() { panel.isHidden = true }
    @objc func toggleKey(_ b: NSButton) {
        var held = App.heldKeys; let c = UInt16(b.tag)
        if held.contains(c) { held.remove(c) } else { held.insert(c) }
        App.heldKeys = held; app?.screen.heldForMac = held
        refreshKeys()
    }
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
        tip.stringValue = s; tip.textColor = color; tip.isHidden = s.isEmpty
    }
}
