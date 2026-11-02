// VM Router (Mantra): the window of vm-router, the one door to chromium-vm for many sessions at once.
// Marko, 2.11.2026: "please build the router for using virtual machines. If multiple sessions are using it, it should
// be seamless, not getting one image from the other session and so on" / "another star application".
// The router is router/vm-router.py (127.0.0.1:8891, MANTRA_PORTS `vm-router`); this window starts and stops it, runs
// its CHECK and shows the sessions with their tab, account, folder, the global lock and the last events.
// OFF quits only this window's app: the router keeps serving the sessions (a build presses OFF; it must never cut a
// running job). ① STOP stops the router.
import SwiftUI
import AppKit

let VERSION = 1
let APP_NAME = "VM Router (Mantra)"
let ROUTER_DIR = NSHomeDirectory() + "/Developer/vm-chromium/router"

// MARK: colours (design-language.md: colour carries state)
extension Color {
    static let on = Color(red: 0x33 / 255, green: 0xD1 / 255, blue: 0x7A / 255)
    static let off = Color(red: 0x7A / 255, green: 0x80 / 255, blue: 0x87 / 255)
    static let amber = Color(red: 0xE8 / 255, green: 0xA3 / 255, blue: 0x3D / 255)
    static let alarm = Color(red: 1, green: 0x3B / 255, blue: 0x30 / 255)
    static let hair = Color.white.opacity(0.14)
    static let ground = Color(red: 0.07, green: 0.08, blue: 0.09)
}

extension View {
    /// Every control is an Accessibility button with a short fixed identifier (swift-apps.md).
    func axButton(_ label: String, id: String, value: String? = nil, _ action: @escaping () -> Void) -> some View {
        accessibilityElement(children: .ignore)
            .accessibilityLabel(label).accessibilityIdentifier(id).accessibilityValue(value ?? "")
            .accessibilityAddTraits(.isButton).accessibilityAction(.default, action)
    }
}

// MARK: the router's state, read from GET /status every second

struct SessionRow: Identifiable {
    let id: String, name: String, account: String, folder: String, tabs: [String]
    let actions: Int, last: String, lastAgo: Int, nextImage: Int, pacing: Double
}
struct EventRow: Identifiable { let id: Int, time: String, session: String, what: String }

final class Model: ObservableObject {
    @Published var running = false
    @Published var port = 8891
    @Published var pid = 0
    @Published var version = 0
    @Published var sessions: [SessionRow] = []
    @Published var events: [EventRow] = []
    @Published var lock = "FREE"
    @Published var waiting = 0
    @Published var accounts = "—"
    @Published var busy = ""            // "STARTING", "STOPPING", "CHECKING"
    @Published var check = ""           // the last CHECK's answer
    @Published var checkOK = true
    var timer: Timer?

    var base: String {
        if let d = try? Data(contentsOf: URL(fileURLWithPath: NSHomeDirectory() + "/.config/mantra-ports.json")),
           let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
           let e = j["vm-router"] as? [String: Any], let u = e["url"] as? String { return u }
        return "http://127.0.0.1:8891"
    }

    func begin() {
        poll()
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.poll() }
    }

    func request(_ path: String, method: String = "GET", timeout: TimeInterval = 3,
                 done: @escaping ([String: Any]?) -> Void) {
        guard let url = URL(string: base + path) else { return done(nil) }
        var r = URLRequest(url: url, timeoutInterval: timeout); r.httpMethod = method
        if method == "POST" { r.httpBody = "{}".data(using: .utf8); r.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        URLSession.shared.dataTask(with: r) { d, _, _ in
            let j = d.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
            DispatchQueue.main.async { done(j) }
        }.resume()
    }

    func poll() {
        request("/status") { [weak self] j in
            guard let self else { return }
            guard let j else { self.running = false; self.sessions = []; self.lock = "—"; self.waiting = 0; return }
            self.running = true
            self.port = j["port"] as? Int ?? 8891; self.pid = j["pid"] as? Int ?? 0; self.version = j["version"] as? Int ?? 0
            self.sessions = (j["sessions"] as? [[String: Any]] ?? []).map { s in
                let acc = s["account"] as? Int
                let email = s["email"] as? String ?? ""
                return SessionRow(id: s["session"] as? String ?? "?", name: s["name"] as? String ?? "?",
                                  account: acc.map { "/u/\($0)" + (email.isEmpty ? "" : " \(email)") } ?? "—",
                                  folder: s["folder"] as? String ?? "", tabs: s["tabs"] as? [String] ?? [],
                                  actions: s["actions"] as? Int ?? 0, last: s["last"] as? String ?? "",
                                  lastAgo: s["last_ago_s"] as? Int ?? 0, nextImage: s["next_image_in_s"] as? Int ?? 0,
                                  pacing: s["pacing_s"] as? Double ?? 0)
            }
            let fl = j["focus_lock"] as? [String: Any]
            if let h = fl?["holder"] as? [String: Any] {
                self.lock = "\(h["session"] as? String ?? "?") · \(h["what"] as? String ?? "")"
            } else { self.lock = "FREE" }
            self.waiting = (fl?["waiting"] as? [Any])?.count ?? 0
            let acc = j["accounts"] as? [String: [String: Any]] ?? [:]
            self.accounts = acc.isEmpty ? "—" : acc.keys.sorted().map { k in
                let ago = acc[k]?["last_image_ago_s"] as? Int ?? 0
                return (k == "none" ? "no account" : "/u/\(k)") + " \(Model.span(ago)) ago"
            }.joined(separator: " | ")
            let f = DateFormatter(); f.dateFormat = "HH:mm:ss"
            self.events = (j["events"] as? [[String: Any]] ?? []).reversed().map { e in
                let t = Date(timeIntervalSince1970: e["t"] as? Double ?? 0)
                var what = e["what"] as? String ?? ""
                for k in ["tab", "save", "file", "method", "url", "waited_s"] { if let v = e[k] { what += " \(k)=\(v)" } }
                return EventRow(id: e["n"] as? Int ?? 0, time: f.string(from: t), session: e["session"] as? String ?? "", what: what)
            }
        }
    }

    static func span(_ s: Int) -> String { s < 60 ? "\(s)s" : s < 3600 ? "\(s / 60)m\(s % 60)s" : "\(s / 3600)h\(s % 3600 / 60)m" }

    /// ① START: vmr starts the router detached (it outlives this app). ① STOP: POST /stop.
    func startStop() {
        if running {
            busy = "STOPPING"; request("/stop", method: "POST") { [weak self] _ in self?.busy = ""; self?.poll() }
        } else { start() }
    }

    func start() {
        busy = "STARTING"
        DispatchQueue.global().async {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            p.arguments = ["python3", ROUTER_DIR + "/vmr.py", "start"]
            p.standardOutput = FileHandle.nullDevice; p.standardError = FileHandle.nullDevice
            try? p.run(); p.waitUntilExit()
            DispatchQueue.main.async { self.busy = ""; self.poll() }
        }
    }

    /// ② CHECK: the router's own test: two sessions, a background tab of its own, a refusal, the tab closed.
    func runCheck() {
        guard running else { return }
        busy = "CHECKING"; check = ""
        request("/selftest", method: "POST", timeout: 90) { [weak self] j in
            guard let self else { return }
            self.busy = ""
            let r = j?["result"] as? [String: Any]
            let steps = r?["steps"] as? [[String: Any]] ?? []
            let passed = steps.filter { $0["ok"] as? Bool == true }.count
            self.checkOK = (r?["ok"] as? Bool) == true
            self.check = self.checkOK ? "PASSED \(passed)/\(steps.count)"
                : "FAILED \(passed)/\(steps.count): " + (steps.first { $0["ok"] as? Bool != true }?["step"] as? String ?? "router did not answer")
        }
    }
}

// MARK: the window

struct Cell: View {
    let label: String, value: String
    var color: Color = .white
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.system(size: 10, weight: .semibold, design: .monospaced)).foregroundColor(.off)
            Text(value).font(.system(size: 13, weight: .bold, design: .monospaced)).foregroundColor(color)
                .fixedSize(horizontal: false, vertical: true)
            Rectangle().fill(Color.hair).frame(height: 1)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct Step: View {
    let n: Int, word: String, note: String
    var enabled = true
    var color: Color = .white
    let id: String
    let action: () -> Void
    @State private var hover = false
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            ZStack {
                Circle().stroke(enabled ? (hover ? Color.on : Color.white) : Color.off, lineWidth: 1.5)
                    .frame(width: hover ? 30 : 26, height: hover ? 30 : 26)
                Text("\(n)").font(.system(size: 13, weight: .bold, design: .monospaced))
            }.frame(width: 32, height: 32)
            Text(word).font(.system(size: 15, weight: .bold, design: .monospaced)).underline(hover && enabled)
            Text(note).font(.system(size: 12, design: .monospaced)).foregroundColor(color)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .foregroundColor(enabled ? .white : .off)
        .contentShape(Rectangle())
        .onHover { h in hover = h && enabled; if h && enabled { NSCursor.pointingHand.push() } else { NSCursor.pop() } }
        .onTapGesture { if enabled { action() } }
        .axButton(word, id: id, value: note) { if enabled { action() } }
    }
}

struct ContentView: View {
    @ObservedObject var m: Model
    @State private var onTop = false
    let margin: CGFloat = 16

    var body: some View {
        GeometryReader { g in
            VStack(spacing: 0) {
                topRow.padding(.horizontal, margin).padding(.vertical, 8)
                line
                ScrollView(.vertical) {
                    VStack(alignment: .leading, spacing: 10) {
                        Step(n: 1, word: m.busy == "STARTING" || m.busy == "STOPPING" ? m.busy : (m.running ? "STOP" : "START"),
                             note: m.running ? "ROUTER RUNNING  127.0.0.1:\(m.port)  pid \(m.pid)  v\(m.version)" : "ROUTER NOT RUNNING",
                             enabled: m.busy.isEmpty, color: m.running ? .on : .off, id: "start") { m.startStop() }
                        line
                        Step(n: 2, word: m.busy == "CHECKING" ? "CHECKING" : "CHECK",
                             note: m.check.isEmpty ? "two test sessions, a background tab of their own, a refusal, closed" : m.check,
                             enabled: m.running && m.busy.isEmpty, color: m.check.isEmpty ? .off : (m.checkOK ? .on : .alarm),
                             id: "check") { m.runCheck() }
                        line
                        table
                        line
                        sessionsList
                        line
                        eventsList
                    }
                    .frame(width: max(g.size.width - 2 * margin, 200), alignment: .leading)
                    .padding(margin)
                }
            }
        }
        .background(Color.ground)
        .foregroundColor(.white)
        .frame(minWidth: 560, idealWidth: 860, maxWidth: .infinity, minHeight: 440, idealHeight: 680, maxHeight: .infinity)
    }

    var line: some View { Rectangle().fill(Color.hair).frame(height: 1) }

    func word(_ s: String, _ c: Color, id: String, _ action: @escaping () -> Void) -> some View {
        Text(s).font(.system(size: 13, weight: .bold, design: .monospaced)).foregroundColor(c)
            .contentShape(Rectangle()).onTapGesture(perform: action).axButton(s, id: id, action)
    }

    var topRow: some View {
        HStack(spacing: 14) {
            Text("VM ROUTER").font(.system(size: 13, weight: .bold, design: .monospaced))
            word("ON", .on, id: "on") {}
            word("OFF", .off, id: "off") { DispatchQueue.main.async { NSApp.terminate(nil) } }
            word("TOP", onTop ? .on : .off, id: "top") {
                onTop.toggle(); NSApp.windows.forEach { $0.level = onTop ? .floating : .normal }
            }
            Text("v\(VERSION)").font(.system(size: 12, design: .monospaced)).foregroundColor(.off)
            Spacer(minLength: 0)
            Image(systemName: "xmark").foregroundColor(.off).frame(width: 28, height: 28).contentShape(Rectangle())
                .onTapGesture { NSApp.keyWindow?.orderOut(nil) }
                .axButton("CLOSE", id: "close") { NSApp.windows.first?.orderOut(nil) }
        }
    }

    var table: some View {
        VStack(spacing: 10) {
            HStack(alignment: .top, spacing: 14) {
                Cell(label: "SESSIONS", value: "\(m.sessions.count)")
                Cell(label: "TABS", value: "\(m.sessions.reduce(0) { $0 + $1.tabs.count })")
                Cell(label: "GLOBAL LOCK", value: m.lock, color: m.lock == "FREE" ? .on : .amber)
                Cell(label: "WAITING", value: "\(m.waiting)", color: m.waiting > 0 ? .amber : .white)
            }
            Cell(label: "IMAGES PER ACCOUNT (LAST REQUEST)", value: m.accounts)
        }
    }

    var sessionsList: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("SESSIONS").font(.system(size: 10, weight: .semibold, design: .monospaced)).foregroundColor(.off)
            if m.sessions.isEmpty {
                Text(m.running ? "none yet: a session starts with  vmr -s NAME session" : "the router is not running")
                    .font(.system(size: 12, design: .monospaced)).foregroundColor(.off)
            }
            ForEach(m.sessions) { s in
                VStack(alignment: .leading, spacing: 6) {
                    HStack(alignment: .top, spacing: 14) {
                        Cell(label: "NAME", value: s.name)
                        Cell(label: "ACCOUNT", value: s.account)
                        Cell(label: "TAB", value: s.tabs.isEmpty ? "—" : s.tabs.map { String($0.prefix(8)) }.joined(separator: " "))
                    }
                    HStack(alignment: .top, spacing: 14) {
                        Cell(label: "FOLDER", value: "Downloads/" + s.folder)
                        Cell(label: "ACTIONS", value: "\(s.actions)")
                        Cell(label: "LAST", value: s.last.isEmpty ? "—" : "\(s.last) · \(Model.span(s.lastAgo)) ago")
                        Cell(label: "NEXT IMAGE", value: s.pacing > 0 ? "waiting \(Int(s.pacing))s" : (s.nextImage > 0 ? "in \(s.nextImage)s" : "now"),
                             color: s.pacing > 0 ? .amber : .white)
                    }
                }
                .padding(.vertical, 4)
            }
        }
    }

    var eventsList: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("LAST EVENTS").font(.system(size: 10, weight: .semibold, design: .monospaced)).foregroundColor(.off)
            ForEach(m.events) { e in
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text(e.time).foregroundColor(.off)
                    Text(e.session).foregroundColor(.amber)
                    Text(e.what).fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                }.font(.system(size: 11, design: .monospaced))
            }
        }
    }
}

final class Delegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ s: NSApplication, hasVisibleWindows: Bool) -> Bool {
        NSApp.windows.first?.makeKeyAndOrderFront(nil); return true
    }
    func applicationDidFinishLaunching(_ n: Notification) {
        DispatchQueue.main.async {
            for w in NSApp.windows where w.canBecomeMain { w.setFrameAutosaveName("VMRouterWindow"); w.title = APP_NAME }
            // started by the Star at login (Swift Matrix ALWAYS): the router starts, the window stays hidden
            if CommandLine.arguments.contains("--login") { NSApp.windows.forEach { $0.orderOut(nil) } }
        }
    }
}

@main
struct VMRouterApp: App {
    @NSApplicationDelegateAdaptor(Delegate.self) var delegate
    @StateObject var model = Model()
    var body: some Scene {
        Window(APP_NAME, id: "main") {
            ContentView(m: model).onAppear {
                model.begin()
                if CommandLine.arguments.contains("--login") { model.start() }
            }
        }
        .defaultSize(width: 860, height: 680)
        .windowResizability(.contentMinSize)
    }
}
