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
        ("fullscreen", "switches full screen on or off", [:]),
        ("reconnect", "drops the VNC connection and connects again", [:]),
        ("send_file", "sends a Mac file to ~/Downloads on the VM", ["path": "str"]),
        ("push_clipboard", "puts the Mac clipboard on the VM clipboard now", [:]),
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
                                               "window": "\(Int(s.width))x\(Int(s.height))", "fullscreen": app.window.styleMask.contains(.fullScreen)]])
        case "show":
            app.window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true); reply(200, ["ok": true, "result": "shown"])
        case "fullscreen":
            app.window.toggleFullScreen(nil); reply(200, ["ok": true, "result": "toggled"])
        case "reconnect":
            app.reconnect(); reply(200, ["ok": true, "result": "reconnecting"])
        case "push_clipboard":
            app.lastPushedChange = -1; app.lastClipText = ""
            app.pushClipboard { reply(200, ["ok": true, "result": "pushed"]) }
        case "send_file":
            guard let p = args["path"] as? String, FileManager.default.fileExists(atPath: p) else {
                return reply(400, ["ok": false, "error": "no file at that path"]) }
            app.upload([URL(fileURLWithPath: p)]); reply(200, ["ok": true, "result": "sending"])
        default:
            reply(404, ["ok": false, "error": "no such action; see /api"])
        }
    }
}
