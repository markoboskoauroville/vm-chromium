// Services.swift: v33 (Marko, 14.11.2026): "I need to login with my remote viewing to this machine and on the gear icon I
// will have each program and we now call the program services ... I enable each service as I need it". The gear's
// SERVICES opens this panel: one row per service of the VM (vmctl, http://100.102.86.30:8896), a green dot = running,
// a white dot = stopped; a click starts or stops it. CORE rows (Connection Keeper, Tailscale, Queen, ...) are shown,
// locked. The token is a text file in ~/Downloads/API (chromium-vm-vmctl.txt), never in the code.
import AppKit

final class VMCtl {
    static let base = URL(string: "http://\(Agent.host):8896")!
    var token: String { (try? String(contentsOfFile: NSHomeDirectory() + "/Downloads/API/chromium-vm-vmctl.txt", encoding: .utf8))?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? "" }
    private let session: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 330; c.connectionProxyDictionary = [:]   // a Pixel boots ~40 s; Tailscale, never a proxy
        return URLSession(configuration: c)
    }()

    func call(_ method: String, _ path: String, _ body: [String: Any]? = nil, done: @escaping ([String: Any]?, String?) -> Void) {
        var r = URLRequest(url: VMCtl.base.appendingPathComponent(path))
        r.httpMethod = method
        r.setValue(token, forHTTPHeaderField: "X-Mantra-Token")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let b = body { r.httpBody = try? JSONSerialization.data(withJSONObject: b) }
        session.dataTask(with: r) { d, _, e in
            let j = d.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
            let err = e?.localizedDescription ?? ((j?["ok"] as? Bool) == false ? (j?["error"] as? String ?? "error") : nil)
            DispatchQueue.main.async { done(j, j == nil && err == nil ? "no answer" : err) }
        }.resume()
    }
}

/// One service: the dot, its short name, its title, its state word. The whole row is the button (hand, underline, lit).
final class ServiceRow: NSView {
    let name: String
    let core: Bool
    var running = false { didSet { paint() } }
    var busy: String? { didSet { paint() } }
    var error: String? { didSet { paint() } }
    var onClick: ((ServiceRow) -> Void)?
    private let dot = NSView()
    private let short = NSTextField(labelWithString: "")
    private let title = NSTextField(labelWithString: "")
    private let state = NSTextField(labelWithString: "")
    private var hover = false { didSet { paint() } }
    private var down = false { didSet { paint() } }

    init(_ s: [String: Any]) {
        name = s["name"] as? String ?? "?"
        core = s["core"] as? Bool ?? false
        super.init(frame: .zero)
        wantsLayer = true; layer?.cornerRadius = 5
        translatesAutoresizingMaskIntoConstraints = false
        dot.wantsLayer = true; dot.layer?.cornerRadius = 5
        short.stringValue = s["short"] as? String ?? name
        short.font = .monospacedSystemFont(ofSize: 13, weight: .bold)
        title.stringValue = s["title"] as? String ?? ""
        title.font = .systemFont(ofSize: 12); title.textColor = NSColor(white: 0.6, alpha: 1)
        title.lineBreakMode = .byTruncatingTail
        title.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        state.font = .systemFont(ofSize: 11, weight: .semibold); state.alignment = .right
        for v in [dot, short, title, state] { v.translatesAutoresizingMaskIntoConstraints = false; addSubview(v) }
        NSLayoutConstraint.activate([
            heightAnchor.constraint(equalToConstant: 24),
            dot.widthAnchor.constraint(equalToConstant: 10), dot.heightAnchor.constraint(equalToConstant: 10),
            dot.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 6), dot.centerYAnchor.constraint(equalTo: centerYAnchor),
            short.leadingAnchor.constraint(equalTo: dot.trailingAnchor, constant: 8), short.centerYAnchor.constraint(equalTo: centerYAnchor),
            short.widthAnchor.constraint(equalToConstant: 82),
            title.leadingAnchor.constraint(equalTo: short.trailingAnchor, constant: 6), title.centerYAnchor.constraint(equalTo: centerYAnchor),
            state.leadingAnchor.constraint(greaterThanOrEqualTo: title.trailingAnchor, constant: 8),
            state.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -6), state.centerYAnchor.constraint(equalTo: centerYAnchor),
            state.widthAnchor.constraint(equalToConstant: 92)])
        if !core { addTrackingArea(NSTrackingArea(rect: .zero, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect], owner: self)) }
        setAccessibilityElement(true); setAccessibilityRole(.button)
        running = s["running"] as? Bool ?? false
        paint()                                        // didSet does not run inside init
    }
    required init?(coder: NSCoder) { fatalError() }

    func update(_ s: [String: Any]) { running = s["running"] as? Bool ?? false }

    func paint() {
        dot.layer?.backgroundColor = (running ? NSColor.systemGreen : NSColor.white).cgColor
        short.textColor = core ? NSColor(white: 0.75, alpha: 1) : .white
        let under: [NSAttributedString.Key: Any] = hover && !core ? [.underlineStyle: NSUnderlineStyle.single.rawValue] : [:]
        short.attributedStringValue = NSAttributedString(string: short.stringValue, attributes: under.merging(
            [.font: NSFont.monospacedSystemFont(ofSize: 13, weight: .bold), .foregroundColor: short.textColor!]) { a, _ in a })
        if let e = error {
            state.stringValue = "FAILED"; state.textColor = .systemRed; toolTip = e
        } else if let b = busy {
            state.stringValue = b; state.textColor = .systemOrange; toolTip = nil
        } else if core {
            state.stringValue = "🔒 CORE"; state.textColor = NSColor(white: 0.55, alpha: 1); toolTip = "Core: on at boot, locked"
        } else {
            state.stringValue = running ? (hover ? "STOP" : "RUNNING") : (hover ? "START" : "STOPPED")
            state.textColor = running ? .systemGreen : NSColor(white: 0.8, alpha: 1); toolTip = nil
        }
        // pressable highlight: lit on hover, brighter while pressed
        layer?.backgroundColor = NSColor(white: 1, alpha: core ? 0 : (down ? 0.22 : (hover ? 0.10 : 0))).cgColor
        setAccessibilityLabel("\(short.stringValue) \(running ? "running" : "stopped")\(core ? ", core, locked" : "")")
    }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func resetCursorRects() { if !core { addCursorRect(bounds, cursor: .pointingHand) } }
    override func mouseEntered(with e: NSEvent) { hover = true }
    override func mouseExited(with e: NSEvent) { hover = false; down = false }
    override func mouseDown(with e: NSEvent) { if !core && busy == nil { down = true } }
    override func mouseUp(with e: NSEvent) {
        guard down else { return }
        down = false
        if bounds.contains(convert(e.locationInWindow, from: nil)) { onClick?(self) }
    }
    override func accessibilityPerformPress() -> Bool { if !core && busy == nil { onClick?(self) }; return true }
}

/// The panel: title row (SERVICES · BACK · ✕), the rows, a note line. Refreshed every 5 s while it is open.
final class ServicesPanel: NSVisualEffectView {
    var onBack: (() -> Void)?
    private let api = VMCtl()
    private let stack = NSStackView()
    private let list = NSStackView()
    private let note = NSTextField(labelWithString: "")
    private var rows: [String: ServiceRow] = [:]
    private var timer: Timer?

    init() {
        super.init(frame: .zero)
        material = .hudWindow; blendingMode = .withinWindow; state = .active
        wantsLayer = true; layer?.cornerRadius = 10; isHidden = true
        translatesAutoresizingMaskIntoConstraints = false
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 8
        stack.edgeInsets = NSEdgeInsets(top: 12, left: 12, bottom: 12, right: 12)
        stack.translatesAutoresizingMaskIntoConstraints = false
        addSubview(stack)
        let head = NSTextField(labelWithString: "SERVICES  ·  chromium-vm")
        head.font = .systemFont(ofSize: 13, weight: .semibold); head.textColor = .white
        let backButton = WordButton("BACK", self, #selector(ServicesPanel.back))
        let top = NSStackView(views: [head, NSView(), backButton]); top.orientation = .horizontal; top.spacing = 8
        top.translatesAutoresizingMaskIntoConstraints = false
        stack.addArrangedSubview(top)
        top.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -24).isActive = true
        let sub = NSTextField(labelWithString: "Green runs, white is stopped. A click starts or stops it. CORE is locked.")
        sub.font = .systemFont(ofSize: 11); sub.textColor = NSColor(white: 0.55, alpha: 1)
        stack.addArrangedSubview(sub)
        list.orientation = .vertical; list.alignment = .leading; list.spacing = 1
        stack.addArrangedSubview(list)
        note.font = .systemFont(ofSize: 11, weight: .semibold); note.textColor = .systemOrange
        note.lineBreakMode = .byTruncatingTail; note.isHidden = true
        stack.addArrangedSubview(note)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: leadingAnchor), stack.trailingAnchor.constraint(equalTo: trailingAnchor),
            stack.topAnchor.constraint(equalTo: topAnchor), stack.bottomAnchor.constraint(equalTo: bottomAnchor),
            widthAnchor.constraint(equalToConstant: 470)])
    }
    required init?(coder: NSCoder) { fatalError() }

    // a click on the panel itself never reaches the VM underneath
    override func mouseDown(with e: NSEvent) {}
    override func scrollWheel(with e: NSEvent) {}

    func open() {
        isHidden = false; refresh()
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.refresh() }
    }
    func close() { isHidden = true; timer?.invalidate(); timer = nil }
    @objc func back() { close(); onBack?() }

    private func say(_ s: String?) { note.stringValue = s ?? ""; note.isHidden = s == nil }

    func refresh() {
        if api.token.isEmpty { say("No token: ~/Downloads/API/chromium-vm-vmctl.txt"); return }
        api.call("GET", "services") { [weak self] j, err in
            guard let self = self else { return }
            guard let list = j?["services"] as? [[String: Any]] else { self.say("vmctl: \(err ?? "no answer")"); return }
            self.say(nil)
            for s in list {
                let n = s["name"] as? String ?? "?"
                if let r = self.rows[n] { if r.busy == nil { r.update(s) } } else {
                    let r = ServiceRow(s)
                    r.onClick = { [weak self] row in self?.toggle(row) }
                    self.rows[n] = r; self.list.addArrangedSubview(r)
                    r.widthAnchor.constraint(equalToConstant: 446).isActive = true
                }
            }
        }
    }

    private func toggle(_ r: ServiceRow) {
        let verb = r.running ? "stop" : "start"
        r.error = nil; r.busy = r.running ? "STOPPING…" : "STARTING…"
        api.call("POST", "services/\(r.name)/\(verb)", ["who": "remote-viewing-mac", "gui": true]) { [weak self] _, err in
            r.busy = nil
            if let e = err { r.error = e; self?.say("\(r.name): \(e)") }
            self?.refresh()
        }
    }
}
