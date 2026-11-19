// Peers.swift: v34 (Marko's master, 19.11.2026): a menu-bar item listing the Tailscale machines that are online
// (`tailscale status --json`); choosing one points the viewer at it. chromium-vm keeps its full protocol (RFB :5901 with
// the Keychain password, vm-agent, vmctl); any other machine is plain RFB on :5900 with the password in
// ~/Downloads/API/vnc-<name>.txt, and the vm-agent features (clipboard, file drop, services, screen sizes) stay off.
import AppKit
import Security

/// where the viewer is pointed. The VM is the default; `Target.isVM` decides whether vm-agent is spoken to at all.
enum Target {
    static var name = "chromium-vm"
    static var host = Agent.host
    static var port = VNC_PORT
    static var os = ""
    static var isVM: Bool { host == Agent.host }
    /// a Mac on the other side (Tailscale says macOS, or this Mac's own server): ⌘ goes as ⌘ (Super), not as Ctrl
    static var isMac: Bool { os == "macOS" || isSelf }
    /// v39: this Mac's own server (Share this Mac), reached on 127.0.0.1 or this Mac's addresses, port 5901
    static var isSelf: Bool { port == Int(SHARE_PORT) && (host == "127.0.0.1" || host == "localhost" || PeersMenu.selfIPs.contains(host)) }
    /// the VNC password of a machine other than the VM: typed under the gear (LOGIN, the Keychain, v39), else
    /// ~/Downloads/API/vnc-<name>.txt (never in the code). A file of two lines is user name, then password (a Mac).
    static var peerPassword: String {
        if isSelf { return Share.password }
        if let k = PeerLogin.get(name)?.password, !k.isEmpty { return k }
        return fileLines.last ?? ""
    }
    /// the user name for a Mac's own Screen Sharing (Apple login): LOGIN, else the file's first of two lines, else this Mac's user
    static var peerUser: String {
        if let u = PeerLogin.get(name)?.user, !u.isEmpty { return u }
        let l = fileLines; return l.count >= 2 ? l[0] : NSUserName()
    }
    private static var fileLines: [String] {
        ((try? String(contentsOfFile: NSHomeDirectory() + "/Downloads/API/vnc-\(name).txt", encoding: .utf8)) ?? "")
            .split(whereSeparator: \.isNewline).map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }
    /// the VNC port of another machine: ~/Downloads/API/vnc-<name>.port when it has one (a server on 5901, 5902...), else 5900
    static func portFor(_ n: String) -> Int {
        let s = (try? String(contentsOfFile: NSHomeDirectory() + "/Downloads/API/vnc-\(n).port", encoding: .utf8))?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return Int(s) ?? 5900
    }
    static func set(name n: String, host h: String, port p: Int? = nil, os o: String = "") {
        name = n; host = h; os = o; port = (h == Agent.host) ? VNC_PORT : (p ?? portFor(n))
        Agent.enabled = (h == Agent.host)
    }
}

struct Peer { let name: String; let ip: String; let os: String }

/// v39: user name and password for a machine other than the VM, typed under the gear (LOGIN), kept in the Keychain
enum PeerLogin {
    static let service = "community.auroville.chromiumvm.peer"
    static func get(_ name: String) -> (user: String, password: String)? {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: name, kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data,
              let s = String(data: d, encoding: .utf8) else { return nil }
        let parts = s.split(separator: "\n", maxSplits: 1, omittingEmptySubsequences: false).map(String.init)
        return parts.count == 2 ? (parts[0], parts[1]) : ("", s)
    }
    static func save(_ name: String, user: String, password: String) {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: name]
        SecItemDelete(q as CFDictionary)
        var add = q; add[kSecValueData as String] = Data((user + "\n" + password).utf8)
        SecItemAdd(add as CFDictionary, nil)
    }
}

final class PeersMenu: NSObject, NSMenuDelegate {
    private let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    private let menu = NSMenu()
    private var peers: [Peer] = []
    private var timer: Timer?
    weak var app: App?

    init(app: App) {
        self.app = app
        super.init()
        item.button?.title = "⌖"
        item.button?.toolTip = "\(APP_NAME): Tailscale machines"
        menu.delegate = self
        item.menu = menu
        rebuild()
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in self?.refresh() }
    }

    static var tailscalePath: String? {
        ["/usr/local/bin/tailscale", "/opt/homebrew/bin/tailscale", "/Applications/Tailscale.app/Contents/MacOS/Tailscale"]
            .first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    /// parse `tailscale status --json`: online peers (and this Mac left out), name = HostName, ip = first IPv4
    static func parse(_ data: Data) -> [Peer] {
        guard let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let all = j["Peer"] as? [String: [String: Any]] else { return [] }
        return all.values.compactMap { p -> Peer? in
            guard p["Online"] as? Bool == true, let ips = p["TailscaleIPs"] as? [String],
                  let ip = ips.first(where: { !$0.contains(":") }) else { return nil }
            let name = (p["HostName"] as? String) ?? (p["DNSName"] as? String) ?? ip
            return Peer(name: name, ip: ip, os: (p["OS"] as? String) ?? "")
        }.sorted { $0.name.lowercased() < $1.name.lowercased() }
    }

    /// this Mac's own Tailscale addresses (to know when the viewer is pointed at its own server)
    static var selfIPs: [String] = []
    static func parseSelf(_ data: Data) -> [String] {
        guard let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let me = j["Self"] as? [String: Any], let ips = me["TailscaleIPs"] as? [String] else { return [] }
        return ips
    }

    func refresh() {
        guard let path = PeersMenu.tailscalePath else { return }
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let p = Process(); p.executableURL = URL(fileURLWithPath: path); p.arguments = ["status", "--json"]
            let out = Pipe(); p.standardOutput = out; p.standardError = FileHandle.nullDevice
            guard (try? p.run()) != nil else { return }
            let data = out.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
            let list = PeersMenu.parse(data), me = PeersMenu.parseSelf(data)
            DispatchQueue.main.async { self?.peers = list; PeersMenu.selfIPs = me; self?.rebuild() }
        }
    }

    func menuWillOpen(_ menu: NSMenu) { refresh() }

    func rebuild() {
        menu.removeAllItems()
        let head = NSMenuItem(title: "Viewing: \(Target.name)  \(Target.host)", action: nil, keyEquivalent: ""); head.isEnabled = false
        menu.addItem(head); menu.addItem(.separator())
        if PeersMenu.tailscalePath == nil {
            let m = NSMenuItem(title: "Tailscale not found", action: nil, keyEquivalent: ""); m.isEnabled = false; menu.addItem(m)
        } else if peers.isEmpty {
            let m = NSMenuItem(title: "No machine online", action: nil, keyEquivalent: ""); m.isEnabled = false; menu.addItem(m)
        }
        for p in peers {
            let m = NSMenuItem(title: "\(p.name)  \(p.ip)", action: #selector(pick(_:)), keyEquivalent: "")
            m.target = self; m.representedObject = p
            m.state = (p.ip == Target.host) ? .on : .off
            menu.addItem(m)
        }
        menu.addItem(.separator())
        // v39: this Mac's own VNC server
        let srv = VNCServer.shared
        let share = menu.addItem(withTitle: "Share this Mac (VNC, port \(SHARE_PORT))", action: #selector(toggleShare), keyEquivalent: "")
        share.target = self; share.state = Share.on ? .on : .off
        if Share.on {
            let n = srv.clientCount
            let line = srv.lastError.isEmpty ? (srv.listening ? "Listening on every address · \(n) viewing" : "Starting…") : srv.lastError
            let st = NSMenuItem(title: line, action: nil, keyEquivalent: ""); st.isEnabled = false; menu.addItem(st)
            let ips = PeersMenu.selfIPs.filter { !$0.contains(":") }
            if let ip = ips.first {
                let a = NSMenuItem(title: "Address: \(ip):\(SHARE_PORT)", action: nil, keyEquivalent: ""); a.isEnabled = false; menu.addItem(a)
            }
            let pw = menu.addItem(withTitle: Share.password.isEmpty ? "No password (set one under the gear)" : "Password: \(Share.password)  (click to copy)", action: #selector(copyPassword), keyEquivalent: "")
            pw.target = self
            let np = menu.addItem(withTitle: "New password", action: #selector(newPassword), keyEquivalent: ""); np.target = self
            if !Share.screenAllowed || !Share.inputAllowed {
                let miss = [Share.screenAllowed ? nil : "Screen Recording", Share.inputAllowed ? nil : "Accessibility"].compactMap { $0 }
                let pm = menu.addItem(withTitle: "PERMISSIONS: allow \(miss.joined(separator: " and "))…", action: #selector(openPerms), keyEquivalent: "")
                pm.target = self
            }
        }
        menu.addItem(.separator())
        let show = menu.addItem(withTitle: "Show window", action: #selector(showWindow), keyEquivalent: ""); show.target = self
    }

    @objc private func toggleShare() { app?.setShare(!Share.on) }
    @objc private func copyPassword() {
        let pb = NSPasteboard.general; pb.clearContents(); pb.setString(Share.password, forType: .string)
    }
    @objc private func newPassword() { Share.newPassword(); rebuild(); app?.overlay.refreshShare() }
    @objc private func openPerms() { app?.overlay.openPermissions() }

    @objc private func showWindow() { app?.window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }

    @objc private func pick(_ s: NSMenuItem) {
        guard let p = s.representedObject as? Peer else { return }
        Target.set(name: p.name, host: p.ip, os: p.os)
        rebuild()
        app?.reconnect()
        showWindow()
    }
}
