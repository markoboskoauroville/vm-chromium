// Chromium Virtual Machine (Mantra): the Mac's window onto chromium-vm (Oracle Cloud, Tailscale 100.102.86.30).
// The VM's screen (RFB, RFB.swift), the clipboard shared both ways and files dropped on the window go to the VM
// (vm-agent, Agent.swift), and a remote door on 127.0.0.1 (MANTRA_MANIFEST remote-door.md, Door.swift).
// Marko, 2.11.2026: "let's build the Swift viewer for the Chromium virtual machine ... clipboard and drag-and-drop".
import AppKit
import Security

let VERSION = 16
let APP_NAME = "VM Machine Remote (Mantra)"
let VNC_HOST = Agent.host, VNC_PORT = 5901

@main
final class App: NSObject, NSApplicationDelegate, RFBDelegate, NSWindowDelegate {
    static func main() { let a = NSApplication.shared; let d = App(); a.delegate = d; a.run() }

    var window: NSWindow!
    let screen = ScreenView(frame: NSRect(x: 0, y: 0, width: 1280, height: 800))
    var overlay: SettingsOverlay!
    // the keys held for the Mac (never sent to the VM): F1 Speechify, F2 Voice to Text (Marko, 2.11.2026)
    // F2 (Voice to Text, a Carbon hotkey) is pressed again into the Mac while the viewer suspends the hotkeys; F1
    // (Speechify) also hears keys through its own event tap, so it already got the real press: pressing it again toggled
    // its dictation straight off (test 2.11.2026). For F1 the viewer only keeps the key from the VM.
    static let pressAgain: Set<UInt16> = [120]
    static var heldKeys: Set<UInt16> {
        get { Set((UserDefaults.standard.array(forKey: "heldKeys") as? [Int] ?? [122, 120]).map { UInt16($0) }) }
        set { UserDefaults.standard.set(newValue.map { Int($0) }, forKey: "heldKeys") }
    }
    let agent = Agent()
    var rfb: RFB?
    var connected = false
    var resizeTimer: Timer?
    var lastPushedChange = NSPasteboard.general.changeCount
    var lastClipText = ""
    var door: Door?
    // v6 (Marko, 2.11.2026): "I don't need anything from the top bar ... in the upper left corner one setting button":
    // no title bar, no button bar; the gear (Settings.swift) floats over the picture's top-left corner
    var downloadsTimer: Timer?
    var fetching = false
    static let downloadsFolder = URL(fileURLWithPath: NSHomeDirectory() + "/Downloads/Chromium Downloads")

    func applicationDidFinishLaunching(_ n: Notification) {
        NSApp.setActivationPolicy(.regular)
        buildMenu()
        buildWindow()
        door = Door(app: self)
        try? FileManager.default.createDirectory(at: App.downloadsFolder, withIntermediateDirectories: true)
        // Since 2.11.2026 downloads go to Google Drive only and are deleted from the VM; nothing comes to the Mac by
        // itself (Marko: "don't transfer anything to my computer ... We are saving the SIM"). fetch_downloads on the
        // door still brings them when asked.
        connect()
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ s: NSApplication, hasVisibleWindows: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil); return true
    }
    // v5 (Marko, 2.11.2026): ⌘Tab switches the VM's screens and ⌃⌥ + key snaps its windows like Rectangle. macOS
    // takes ⌘Tab (and Rectangle on the Mac takes ⌃⌥←…) before any app sees them, so while this app is the active one
    // the Mac's global hotkeys are suspended (CGSSetGlobalHotKeyOperatingMode: per connection, the WindowServer
    // gives them back when the app resigns, quits or dies). Mac-wide ⌘Tab/Spotlight work again as soon as another
    // app is in front.
    func applicationDidBecomeActive(_ n: Notification) { HotKeys.capture(true); pushClipboard {} }
    func applicationDidResignActive(_ n: Notification) { HotKeys.capture(false); screen.releaseAll() }
    func applicationWillTerminate(_ n: Notification) { HotKeys.capture(false) }

    // MARK: window

    func buildMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem(); main.addItem(appItem)
        let m = NSMenu()
        m.addItem(withTitle: "Hide \(APP_NAME)", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        m.addItem(withTitle: "Quit \(APP_NAME)", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = m
        // v12 (Marko, 5.11.2026: "Why can't I paste a simple password?"): an Edit menu, without it ⌘V/⌘C/⌘A do nothing in
        // the gear's fields. The VM picture still takes ⌘V first (ScreenView.performKeyEquivalent), so the VM keeps it.
        let editItem = NSMenuItem(); main.addItem(editItem)
        let ed = NSMenu(title: "Edit")
        ed.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        ed.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        ed.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        ed.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = ed
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
                          styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
        window.titlebarAppearsTransparent = true
        window.acceptsMouseMovedEvents = true
        window.title = APP_NAME
        window.minSize = NSSize(width: 480, height: 360)
        window.collectionBehavior = [.fullScreenPrimary]
        window.delegate = self
        window.setFrameAutosaveName("ChromiumVMWindow")

        // the picture fills the whole window; the bar floats over its top edge, below the (transparent) title bar
        let root = NSView()
        window.contentView = root
        screen.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(screen)
        NSLayoutConstraint.activate([screen.leadingAnchor.constraint(equalTo: root.leadingAnchor),
                                     screen.trailingAnchor.constraint(equalTo: root.trailingAnchor),
                                     screen.topAnchor.constraint(equalTo: root.topAnchor),
                                     screen.bottomAnchor.constraint(equalTo: root.bottomAnchor)])
        overlay = SettingsOverlay(app: self)
        root.addSubview(overlay)
        NSLayoutConstraint.activate([overlay.leadingAnchor.constraint(equalTo: root.leadingAnchor),
                                     overlay.topAnchor.constraint(equalTo: root.topAnchor),
                                     overlay.trailingAnchor.constraint(equalTo: root.trailingAnchor),
                                     overlay.bottomAnchor.constraint(equalTo: root.bottomAnchor)])
        screen.heldForMac = App.heldKeys
        screen.onMacKey = { [weak self] code in self?.passToMac(code) }
        screen.onClick = { [weak self] in self?.overlay.close() }
        screen.onTypeText = { [weak self] text in self?.typeOnVM(text) }
        screen.onDropFiles = { [weak self] in self?.upload($0) }
        screen.beforePaste = { [weak self] go in self?.pushClipboard(go) ?? go() }
        window.center()
        window.makeKeyAndOrderFront(nil)
        window.makeFirstResponder(screen)
        hideTitleBar()
    }

    /// the title bar (traffic lights, title) never shows: everything is in the gear's panel
    func hideTitleBar() {
        window.titleVisibility = .hidden
        window.standardWindowButton(.closeButton)?.superview?.superview?.isHidden = true   // the title bar container
    }

    /// A key held for the Mac (F1, F2) was pressed in the viewer. While the viewer is in front the Mac's global hotkeys
    /// are suspended (HotKeys.swift, for ⌘Tab on the VM), so Speechify and Voice to Text never saw it: give the hotkeys
    /// back for a moment, press the same key again into the Mac's own key stream, and take them again.
    func passToMac(_ code: UInt16) {
        guard CGPreflightPostEventAccess() else {
            overlay.refreshKeys()
            flash("F-key held for the Mac: allow \(APP_NAME) in Accessibility (PERMISSIONS)"); return
        }
        guard App.pressAgain.contains(code) else { return }
        HotKeys.capture(false)
        let src = CGEventSource(stateID: .hidSystemState)
        for down in [true, false] {
            let e = CGEvent(keyboardEventSource: src, virtualKey: CGKeyCode(code), keyDown: down)
            e?.setIntegerValueField(.eventSourceUserData, value: ScreenView.ownMark)
            e?.post(tap: .cghidEventTap)
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { if NSApp.isActive { HotKeys.capture(true) } }
    }

    @objc func reconnect() { rfb?.close(); rfb = nil; connected = false; connect() }

    func windowDidExitFullScreen(_ n: Notification) { hideTitleBar(); showGrips(true) }
    func windowWillEnterFullScreen(_ n: Notification) { showGrips(false) }
    /// the move and resize corners (Grips.swift) mean nothing in full screen
    func showGrips(_ on: Bool) { overlay.moveGrip.isHidden = !on; overlay.resizeGrip.isHidden = !on }
    func windowDidResignKey(_ n: Notification) { screen.releaseAll() }
    func windowDidResize(_ n: Notification) { scheduleResize() }

    // MARK: the connection

    // v13 (Marko, 5.11.2026: "this password is only read from this setting dialog, not connected to any text file on my
    // computer"): the password is typed under the gear (LOGIN) and kept in the Mac's Keychain, nothing else
    static let keychainService = "community.auroville.chromiumvm.vnc"
    var password: String? {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: App.keychainService,
                                kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data else { return nil }
        return String(data: d, encoding: .utf8)
    }
    static var username: String {
        get { UserDefaults.standard.string(forKey: "vmUser") ?? "ubuntu" }
        set { UserDefaults.standard.set(newValue, forKey: "vmUser") }
    }
    func savePassword(_ pw: String) {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: App.keychainService]
        SecItemDelete(q as CFDictionary)
        var add = q; add[kSecValueData as String] = Data(pw.utf8); add[kSecAttrAccount as String] = App.username
        SecItemAdd(add as CFDictionary, nil)
    }

    func connect() {
        guard let pw = password, !pw.isEmpty else {
            setStatus("no password yet: enter it under the gear, LOGIN", .systemOrange)
            overlay.openLogin(); return
        }
        setStatus("connecting to chromium-vm…", .secondaryLabelColor, tip: false)
        let r = RFB(); r.delegate = self; rfb = r; screen.rfb = r
        r.connect(host: VNC_HOST, port: VNC_PORT, password: pw)
    }

    func rfbConnected(name: String, width: Int, height: Int) {
        connected = true
        setStatus("● CHROMIUM VM  \(VNC_HOST)", .systemGreen, tip: false)
        if overlay.tip.textColor == .systemOrange && overlay.tip.stringValue.hasPrefix("not connected") { overlay.setTip("") }
        window.makeFirstResponder(screen)
        scheduleResize(delay: 0.2)
        pushClipboard {}
    }

    func rfbFrame() { screen.refresh() }
    func rfbResized(width: Int, height: Int) { screen.refresh() }

    func rfbClosed(reason: String) {
        connected = false
        if reason.contains("refused") {   // a wrong password: no retry loop, the login opens under the gear
            setStatus("password refused: enter it under the gear, LOGIN", .systemOrange); overlay.openLogin(); return
        }
        let tail = " (is Tailscale on?)"
        setStatus("not connected: \(reason)\(tail) · trying again", .systemOrange)
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

    // MARK: Chromium Downloads: every finished download on the VM lands in ~/Downloads/Chromium Downloads
    // (Marko, 2.11.2026). The VM numbers them (vm-agent `downloads`); the last number fetched is kept here, so
    // what was downloaded while this app was closed comes in when it opens.

    func fetchDownloads() {
        guard !fetching else { return }
        fetching = true
        let since = UserDefaults.standard.integer(forKey: "downloadsSeq")
        agent.call("downloads", ["since": since]) { [weak self] r, _ in
            guard let self, let r = r as? [String: Any], let files = r["files"] as? [[String: Any]], !files.isEmpty else {
                self?.fetching = false; return }
            var queue = files
            func next() {
                guard !queue.isEmpty else { self.fetching = false; return }
                let f = queue.removeFirst()
                guard let name = f["name"] as? String, let seq = f["seq"] as? Int else { return next() }
                self.overlay.setTip("↓ \(name)")
                self.agent.get(name, to: App.downloadsFolder.appendingPathComponent(name)) { err in
                    if let err { self.flash("↓ \(name): \(err)"); self.fetching = false; return }   // tried again in 3 s
                    UserDefaults.standard.set(seq, forKey: "downloadsSeq")
                    self.flash("↓ \(name) → Downloads/Chromium Downloads")
                    next()
                }
            }
            next()
        }
    }

    // MARK: files dropped on the window → ~/Downloads on the VM

    func upload(_ urls: [URL]) {
        var queue = urls.filter { !$0.hasDirectoryPath }
        if queue.count < urls.count { flash("folders are not sent yet: zip them first") }
        func next() {
            guard !queue.isEmpty else { return }
            let f = queue.removeFirst()
            overlay.setTip("↑ \(f.lastPathComponent) 0%")
            agent.put(f, progress: { [weak self] p in
                self?.overlay.setTip("↑ \(f.lastPathComponent) \(Int(p * 100))%")
            }, done: { [weak self] path, err in
                if let err { self?.flash("\(f.lastPathComponent): \(err)") }
                else { self?.flash("\(f.lastPathComponent) → Downloads on the VM") }
                _ = path; next()
            })
        }
        next()
    }

    /// text a Mac app (Voice to Text, Speechify) wrote into the picture: on the VM's clipboard, then ⌃V there
    func typeOnVM(_ text: String) {
        lastClipText = text
        // vm-agent v12 paste_text: the clipboard, then Ctrl+Shift+V into a terminal (Claude Code), Ctrl+V elsewhere
        agent.call("paste_text", ["text": text]) { [weak self] _, err in
            if let err { DispatchQueue.main.async { self?.flash("dictation not pasted on the VM: \(err)") } } }
    }

    /// the connection line in the panel; when it is bad, also the note beside the gear
    func setStatus(_ s: String, _ c: NSColor, tip: Bool = true) {
        overlay.statusLine.stringValue = s; overlay.statusLine.textColor = c
        if tip { overlay.setTip(s) }
    }

    func flash(_ s: String) {
        overlay.setTip(s)
        let now = s
        DispatchQueue.main.asyncAfter(deadline: .now() + 6) { [weak self] in
            if self?.overlay.tip.stringValue == now { self?.overlay.setTip("") }
        }
    }
}
