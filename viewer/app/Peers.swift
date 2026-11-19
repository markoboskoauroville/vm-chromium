// Peers.swift: v34 (Marko's master, 19.11.2026): a menu-bar item listing the Tailscale machines that are online
// (`tailscale status --json`); choosing one points the viewer at it. chromium-vm keeps its full protocol (RFB :5901 with
// the Keychain password, vm-agent, vmctl); any other machine is plain RFB on :5900 with the password in
// ~/Downloads/API/vnc-<name>.txt, and the vm-agent features (clipboard, file drop, services, screen sizes) stay off.
import AppKit

/// where the viewer is pointed. The VM is the default; `Target.isVM` decides whether vm-agent is spoken to at all.
enum Target {
    static var name = "chromium-vm"
    static var host = Agent.host
    static var port = VNC_PORT
    static var isVM: Bool { host == Agent.host }
    /// the VNC password of a machine other than the VM: ~/Downloads/API/vnc-<name>.txt (never in the code)
    static var peerPassword: String {
        (try? String(contentsOfFile: NSHomeDirectory() + "/Downloads/API/vnc-\(name).txt", encoding: .utf8))?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }
    static func set(name n: String, host h: String) {
        name = n; host = h; port = (h == Agent.host) ? VNC_PORT : 5900
        Agent.enabled = (h == Agent.host)
    }
}

struct Peer { let name: String; let ip: String; let os: String }

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

    func refresh() {
        guard let path = PeersMenu.tailscalePath else { return }
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let p = Process(); p.executableURL = URL(fileURLWithPath: path); p.arguments = ["status", "--json"]
            let out = Pipe(); p.standardOutput = out; p.standardError = FileHandle.nullDevice
            guard (try? p.run()) != nil else { return }
            let data = out.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
            let list = PeersMenu.parse(data)
            DispatchQueue.main.async { self?.peers = list; self?.rebuild() }
        }
    }

    func menuWillOpen(_ menu: NSMenu) { refresh() }

    private func rebuild() {
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
        let show = menu.addItem(withTitle: "Show window", action: #selector(showWindow), keyEquivalent: ""); show.target = self
    }

    @objc private func showWindow() { app?.window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }

    @objc private func pick(_ s: NSMenuItem) {
        guard let p = s.representedObject as? Peer else { return }
        Target.set(name: p.name, host: p.ip)
        rebuild()
        app?.reconnect()
        showWindow()
    }
}
