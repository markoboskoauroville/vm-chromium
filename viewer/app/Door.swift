// Door.swift: the remote door (MANTRA_MANIFEST remote-door.md) on 127.0.0.1, port claimed as "chromium-vm".
// GET /health · GET /api · POST /api/<action>. What vm-agent does (ask Claude, files, keys) stays with `cvm` and the
// agent itself; this door drives the window.
import AppKit
import Network

final class Door {
    weak var app: App?
    private var listener: NWListener?
    let port: UInt16

    static let actions: [(String, String, [String: String])] = [
        ("status", "connected or not, the VM's screen size, the window's size", [:]),
        ("show", "brings the window to the front", [:]),
        ("hit_test", "who owns the point under x,y (screen, top-left origin): ours or covered by <app>; never moves the pointer", ["x": "num", "y": "num"]),
        ("fullscreen", "switches full screen on or off", [:]),
        ("reconnect", "drops the VNC connection and connects again", [:]),
        ("send_file", "sends a Mac file to ~/Downloads on the VM", ["path": "str"]),
        ("push_clipboard", "puts the Mac clipboard on the VM clipboard now", [:]),
        ("saver", "bandwidth saver: idle seconds before the picture freezes (0 = off), freeze or wake now", ["idle": "int", "freeze": "bool", "wake": "bool"]),
        ("target", "points the viewer at a machine and connects (same as the menu bar): name, host, optional port; chromium-vm keeps its full protocol", ["name": "str", "host": "str", "port": "int"]),
        ("pointer", "sends a pointer event to the connected machine (picture pixels): x, y, buttons (bit 0 = left)", ["x": "int", "y": "int", "buttons": "int"]),
        ("key", "sends one key event to the connected machine (X keysym), down true/false", ["keysym": "int", "down": "bool"]),
        ("share", "Share this Mac (VNC, port 5901): on true/false switches it; always answers on, listening, viewers, password, permissions; new_password true makes a new password; password <any> sets his own (one character is fine, empty = no password)", ["on": "bool", "new_password": "bool", "password": "str"]),
        ("fetch_downloads", "fetches new VM downloads into ~/Downloads/Chromium Downloads now", [:]),
    ]

    init(app: App) {
        self.app = app
        port = Ports.claim("chromium-vm", 8962)
        guard let p = NWEndpoint.Port(rawValue: port) else { return }
        let params = NWParameters.tcp
        params.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: p)
        guard let l = try? NWListener(using: params) else { return }
        l.newConnectionHandler = { [weak self] c in self?.serve(c) }
        l.start(queue: .main)
        listener = l
    }

    private func serve(_ c: NWConnection) {
        c.start(queue: .main)
        var buf = Data()
        func readMore() {
            c.receive(minimumIncompleteLength: 1, maximumLength: 1 << 20) { [weak self] d, _, done, _ in
                if let d { buf.append(d) }
                if let r = buf.range(of: Data("\r\n\r\n".utf8)) {
                    let head = String(decoding: buf[..<r.lowerBound], as: UTF8.self)
                    let len = head.split(separator: "\r\n").first { $0.lowercased().hasPrefix("content-length:") }
                        .flatMap { Int($0.split(separator: ":")[1].trimmingCharacters(in: .whitespaces)) } ?? 0
                    if buf.count - r.upperBound >= len {
                        let body = buf[r.upperBound..<(r.upperBound + len)]
                        let first = head.split(separator: "\r\n").first?.split(separator: " ") ?? []
                        self?.handle(first.count > 1 ? String(first[0]) : "GET", first.count > 1 ? String(first[1]) : "/", Data(body)) { code, obj in
                            let b = (try? JSONSerialization.data(withJSONObject: obj)) ?? Data()
                            let h = "HTTP/1.1 \(code) OK\r\nContent-Type: application/json\r\nContent-Length: \(b.count)\r\nConnection: close\r\n\r\n"
                            c.send(content: Data(h.utf8) + b, completion: .contentProcessed { _ in c.cancel() })
                        }
                        return
                    }
                }
                if done { c.cancel() } else { readMore() }
            }
        }
        readMore()
    }

    private func handle(_ method: String, _ path: String, _ body: Data, reply: @escaping (Int, Any) -> Void) {
        guard let app else { return reply(500, ["ok": false, "error": "no app"]) }
        if path == "/health" {
            return reply(200, ["app": "chromium-vm", "name": APP_NAME, "version": VERSION, "pid": Int(getpid())])
        }
        if path == "/api" {
            return reply(200, ["app": "chromium-vm", "version": VERSION,
                               "actions": Door.actions.map { ["name": $0.0, "does": $0.1, "args": $0.2] }])
        }
        guard method == "POST", path.hasPrefix("/api/") else { return reply(404, ["ok": false, "error": "no such path; see /api"]) }
        let args = (try? JSONSerialization.jsonObject(with: body) as? [String: Any]) ?? [:]
        switch String(path.dropFirst(5)) {
        case "status":
            let s = app.screen.bounds.size
            reply(200, ["ok": true, "result": ["connected": app.connected, "vm": "\(app.rfb?.width ?? 0)x\(app.rfb?.height ?? 0)",
                                               "window": "\(Int(s.width))x\(Int(s.height))", "fullscreen": app.window.styleMask.contains(.fullScreen), "pointer_sent": pointerSent,
                                               "saver_idle": app.saverIdle, "frozen": app.rfb?.isFrozen ?? false, "bytes_in": app.rfb?.bytesIn ?? 0]])
        case "saver":   // {"idle": seconds (0 = off)} and/or {"freeze": true} / {"wake": true}
            if let i = args["idle"] as? Int { app.saverIdle = max(0, i) }
            if args["freeze"] as? Bool == true { app.freezeNow() }
            if args["wake"] as? Bool == true, app.rfb?.isFrozen == true { app.rfb?.wake(); app.saverWoke() }
            reply(200, ["ok": true, "result": ["saver_idle": app.saverIdle, "frozen": app.rfb?.isFrozen ?? false]])
        case "hit_test":
            let r = app.screen.hitTest(cgX: (args["x"] as? Double) ?? 0, cgY: (args["y"] as? Double) ?? 0)
            reply(200, ["ok": true, "result": r])
        case "show":
            app.window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true); reply(200, ["ok": true, "result": "shown"])
        case "fullscreen":
            app.toggleFull(); reply(200, ["ok": true, "result": "toggled"])
        case "target":
            guard let h = args["host"] as? String, !h.isEmpty else { return reply(400, ["ok": false, "error": "host needed"]) }
            Target.set(name: (args["name"] as? String) ?? h, host: h, port: args["port"] as? Int)
            app.reconnect(); reply(200, ["ok": true, "result": "\(Target.name) \(Target.host):\(Target.port)"])
        case "pointer":
            guard let r = app.rfb, app.connected else { return reply(400, ["ok": false, "error": "not connected"]) }
            r.pointer(x: (args["x"] as? Int) ?? 0, y: (args["y"] as? Int) ?? 0, buttons: UInt8((args["buttons"] as? Int) ?? 0))
            reply(200, ["ok": true, "result": "sent"])
        case "key":
            guard let r = app.rfb, app.connected, let k = args["keysym"] as? Int else { return reply(400, ["ok": false, "error": "not connected or keysym missing"]) }
            r.key(UInt32(k), down: (args["down"] as? Bool) ?? true)
            reply(200, ["ok": true, "result": "sent"])
        case "reconnect":
            app.reconnect(); reply(200, ["ok": true, "result": "reconnecting"])
        case "push_clipboard":
            app.lastPushedChange = -1; app.lastClipText = ""
            app.pushClipboard { reply(200, ["ok": true, "result": "pushed"]) }
        case "share":
            if let on = args["on"] as? Bool, on != Share.on { app.setShare(on) }
            if let pw = args["password"] as? String { Share.setPassword(pw); app.overlay.refreshShare(); app.peersMenu?.rebuild() }
            if args["new_password"] as? Bool == true { Share.newPassword(); app.overlay.refreshShare(); app.peersMenu?.rebuild() }
            let srv = VNCServer.shared
            reply(200, ["ok": true, "result": ["on": Share.on, "listening": srv.listening, "port": Int(SHARE_PORT),
                                               "viewers": srv.clientCount, "password": Share.password, "error": srv.lastError,
                                               "screen_recording": Share.screenAllowed, "accessibility": Share.inputAllowed,
                                               "target": "\(Target.name) \(Target.host):\(Target.port)"]])
        case "fetch_downloads":
            app.fetchDownloads(); reply(200, ["ok": true, "result": "fetching"])
        case "send_file":
            guard let p = args["path"] as? String, FileManager.default.fileExists(atPath: p) else {
                return reply(400, ["ok": false, "error": "no file at that path"]) }
            app.upload([URL(fileURLWithPath: p)]); reply(200, ["ok": true, "result": "sending"])
        default:
            reply(404, ["ok": false, "error": "no such action; see /api"])
        }
    }
}
