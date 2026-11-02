// Chromium Virtual Machine (Mantra): the Mac's window onto chromium-vm (Oracle Cloud, Tailscale 100.102.86.30).
// The VM's screen (RFB, RFB.swift), the clipboard shared both ways and files dropped on the window go to the VM
// (vm-agent, Agent.swift), and a remote door on 127.0.0.1 (MANTRA_MANIFEST remote-door.md, Door.swift).
// Marko, 2.11.2026: "let's build the Swift viewer for the Chromium virtual machine ... clipboard and drag-and-drop".
import AppKit

let VERSION = 1
let APP_NAME = "Chromium Virtual Machine (Mantra)"
let VNC_HOST = Agent.host, VNC_PORT = 5901

@main
final class App: NSObject, NSApplicationDelegate, RFBDelegate, NSWindowDelegate {
    static func main() { let a = NSApplication.shared; let d = App(); a.delegate = d; a.run() }

    var window: NSWindow!
    let screen = ScreenView(frame: NSRect(x: 0, y: 0, width: 1280, height: 800))
    let bar = NSStackView()
    let status = NSTextField(labelWithString: "connecting…")
    let note = NSTextField(labelWithString: "")
    var onButton: NSButton!, offButton: NSButton!
    let agent = Agent()
    var rfb: RFB?
    var connected = false
    var resizeTimer: Timer?
    var lastPushedChange = NSPasteboard.general.changeCount
    var lastClipText = ""
    var door: Door?

    func applicationDidFinishLaunching(_ n: Notification) {
        NSApp.setActivationPolicy(.regular)
        buildMenu()
        buildWindow()
        door = Door(app: self)
        connect()
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ s: NSApplication, hasVisibleWindows: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil); return true
    }
    func applicationDidBecomeActive(_ n: Notification) { pushClipboard {} }
    func applicationDidResignActive(_ n: Notification) { screen.releaseAll() }

    // MARK: window

    func buildMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem(); main.addItem(appItem)
        let m = NSMenu()
        m.addItem(withTitle: "Hide \(APP_NAME)", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        m.addItem(withTitle: "Quit \(APP_NAME)", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = m
        let viewItem = NSMenuItem(); main.addItem(viewItem)
        let v = NSMenu(title: "View")
        let fs = v.addItem(withTitle: "Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        fs.keyEquivalentModifierMask = [.command, .control]
        v.addItem(withTitle: "Reconnect", action: #selector(reconnect), keyEquivalent: "")
        viewItem.submenu = v
        NSApp.mainMenu = main
    }

    func button(_ title: String, _ action: Selector) -> NSButton {
        let b = NSButton(title: title, target: self, action: action)
        b.bezelStyle = .recessed; b.isBordered = false
        b.font = .systemFont(ofSize: 12, weight: .semibold)
        b.contentTintColor = .secondaryLabelColor
        b.setAccessibilityLabel(title)
        return b
    }

    func buildWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 830),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = APP_NAME
        window.minSize = NSSize(width: 480, height: 360)
        window.collectionBehavior = [.fullScreenPrimary]
        window.delegate = self
        window.setFrameAutosaveName("ChromiumVMWindow")

        status.font = .systemFont(ofSize: 12, weight: .semibold); status.textColor = .secondaryLabelColor
        status.lineBreakMode = .byTruncatingTail
        status.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        note.font = .systemFont(ofSize: 12); note.textColor = .systemOrange
        note.lineBreakMode = .byTruncatingMiddle
        note.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        onButton = button("ON", #selector(noop)); offButton = button("OFF", #selector(off))
        onButton.contentTintColor = .systemGreen
        let close = NSButton(image: NSImage(systemSymbolName: "xmark", accessibilityDescription: "Close")!, target: self, action: #selector(closeWindow))
        close.isBordered = false; close.contentTintColor = .secondaryLabelColor
        close.widthAnchor.constraint(equalToConstant: 28).isActive = true
        close.setAccessibilityLabel("CLOSE")
        let spacer = NSView(); spacer.setContentHuggingPriority(.init(1), for: .horizontal)
        for v in [onButton, offButton, status, note, spacer, button("FULL SCREEN", #selector(fullScreen)),
                  button("RECONNECT", #selector(reconnect)), close] as [NSView] { bar.addArrangedSubview(v) }
        bar.orientation = .horizontal; bar.spacing = 12
        bar.edgeInsets = NSEdgeInsets(top: 0, left: 12, bottom: 0, right: 6)
        bar.heightAnchor.constraint(equalToConstant: 30).isActive = true

        let line = NSBox(); line.boxType = .separator
        let root = NSStackView(views: [bar, line, screen])
        root.orientation = .vertical; root.spacing = 0
        root.setHuggingPriority(.defaultLow, for: .vertical)
        screen.setContentHuggingPriority(.init(1), for: .vertical)
        screen.setContentCompressionResistancePriority(.init(1), for: .vertical)
        screen.setContentCompressionResistancePriority(.init(1), for: .horizontal)
        window.contentView = root
        for v in [bar, line, screen] as [NSView] { v.widthAnchor.constraint(equalTo: root.widthAnchor).isActive = true }

        screen.onDropFiles = { [weak self] in self?.upload($0) }
        screen.beforePaste = { [weak self] go in self?.pushClipboard(go) ?? go() }
        window.center()
        window.makeKeyAndOrderFront(nil)
        window.makeFirstResponder(screen)
    }

    @objc func noop() {}
    @objc func off() { NSApp.terminate(nil) }
    @objc func closeWindow() { window.orderOut(nil) }
    @objc func fullScreen() { window.toggleFullScreen(nil) }
    @objc func reconnect() { rfb?.close(); rfb = nil; connected = false; connect() }

    func windowWillEnterFullScreen(_ n: Notification) { bar.isHidden = true }
    func windowDidExitFullScreen(_ n: Notification) { bar.isHidden = false }
    func windowDidResignKey(_ n: Notification) { screen.releaseAll() }
    func windowDidResize(_ n: Notification) { scheduleResize() }

    // MARK: the connection

    var password: String? {
        (try? String(contentsOfFile: NSHomeDirectory() + "/Downloads/API/chromium-vm-vnc.txt", encoding: .utf8))?
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func connect() {
        guard let pw = password, !pw.isEmpty else {
            status.stringValue = "no VNC password: ~/Downloads/API/chromium-vm-vnc.txt is missing"; return
        }
        status.stringValue = "connecting to chromium-vm…"
        let r = RFB(); r.delegate = self; rfb = r; screen.rfb = r
        r.connect(host: VNC_HOST, port: VNC_PORT, password: pw)
    }

    func rfbConnected(name: String, width: Int, height: Int) {
        connected = true
        status.stringValue = "● CHROMIUM VM  \(VNC_HOST)"
        status.textColor = .systemGreen
        window.makeFirstResponder(screen)
        scheduleResize(delay: 0.2)
        pushClipboard {}
    }

    func rfbFrame() { screen.refresh() }
    func rfbResized(width: Int, height: Int) { screen.refresh() }

    func rfbClosed(reason: String) {
        connected = false
        let tail = reason.contains("refused") ? "" : " (is Tailscale on?)"
        status.stringValue = "not connected: \(reason)\(tail) · trying again"
        status.textColor = .systemOrange
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in
            guard let self, !self.connected else { return }
            self.connect()
        }
    }

    /// The VM follows the window: its size in points (Chrome at 96 dpi looks like the Mac's own size).
    func scheduleResize(delay: TimeInterval = 0.35) {
        resizeTimer?.invalidate()
        resizeTimer = Timer.scheduledTimer(withTimeInterval: delay, repeats: false) { [weak self] _ in
            guard let self, let rfb = self.rfb, self.connected else { return }
            let s = self.screen.bounds.size
            let w = Int(s.width) & ~1, h = Int(s.height) & ~1
            if w != rfb.width || h != rfb.height { rfb.setDesktopSize(w, h) }
        }
    }

    // MARK: the clipboard, both ways (UTF-8 through vm-agent)

    /// Mac → VM: the Mac clipboard, if it changed since the last push. Then `then`.
    func pushClipboard(_ then: @escaping () -> Void) {
        let pb = NSPasteboard.general
        guard pb.changeCount != lastPushedChange, let text = pb.string(forType: .string) else { return then() }
        lastPushedChange = pb.changeCount
        guard text != lastClipText else { return then() }
        lastClipText = text
        agent.clipSet(text) { _ in then() }
    }

    /// VM → Mac: the VM said its clipboard changed; fetch the text.
    func rfbClipboardChanged() {
        agent.clipGet { [weak self] text in
            guard let self, let text, !text.isEmpty, text != self.lastClipText else { return }
            self.lastClipText = text
            let pb = NSPasteboard.general
            pb.clearContents(); pb.setString(text, forType: .string)
            self.lastPushedChange = pb.changeCount
            self.flash("copied on the VM: \(text.count) characters on the Mac clipboard")
        }
    }

    // MARK: files dropped on the window → ~/Downloads on the VM

    func upload(_ urls: [URL]) {
        var queue = urls.filter { !$0.hasDirectoryPath }
        if queue.count < urls.count { flash("folders are not sent yet: zip them first") }
        func next() {
            guard !queue.isEmpty else { return }
            let f = queue.removeFirst()
            note.stringValue = "↑ \(f.lastPathComponent) 0%"
            agent.put(f, progress: { [weak self] p in
                self?.note.stringValue = "↑ \(f.lastPathComponent) \(Int(p * 100))%"
            }, done: { [weak self] path, err in
                if let err { self?.flash("\(f.lastPathComponent): \(err)") }
                else { self?.flash("\(f.lastPathComponent) → Downloads on the VM") }
                _ = path; next()
            })
        }
        next()
    }

    func flash(_ s: String) {
        note.stringValue = s
        let now = s
        DispatchQueue.main.asyncAfter(deadline: .now() + 6) { [weak self] in
            if self?.note.stringValue == now { self?.note.stringValue = "" }
        }
    }
}
