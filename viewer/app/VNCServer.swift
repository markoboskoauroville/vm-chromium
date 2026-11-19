// VNCServer.swift: v39 (Marko, 19.11.2026: "update my application to have built in server and viewer for VNC inside the
// app ... The user does not need to install anything"). "Share this Mac (VNC)": an RFB 3.8 server inside the app, port
// 5901 on every interface (5900 belongs to macOS Screen Sharing when that is on), so Tailscale peers (the Android app,
// another Mac) reach it. VNC password auth, the password shown in the app. The picture comes from ScreenCaptureKit (the
// main display, in points), the pointer and keys go in as CGEvents. Encodings: ZRLE (64×64 tiles, zlib), Raw, DesktopSize.
// Needs Screen Recording (the picture) and Accessibility (pointer and keys): the amber PERMISSIONS button opens them.
import AppKit
import Network
import ScreenCaptureKit
import CoreMedia
import zlib
import Security
import SystemConfiguration

let SHARE_PORT: UInt16 = 5901

/// the share's settings: on/off and the password (8 characters, VNC's limit), kept in the app's defaults
enum Share {
    static var on: Bool {
        get { UserDefaults.standard.bool(forKey: "shareOn") }
        set { UserDefaults.standard.set(newValue, forKey: "shareOn") }
    }
    /// v43 (Marko, 19.11.2026: "custom password without any security limitations. It can be even one one number"): any
    /// password he types, one character is fine, no rules; empty = no password at all (RFB security type None).
    /// Only when none was ever set is one made up. VNC itself uses the first 8 characters.
    static var password: String {
        if let p = UserDefaults.standard.string(forKey: "sharePassword") { return p }
        let alphabet = Array("abcdefghjkmnpqrstuvwxyz23456789")
        var b = [UInt8](repeating: 0, count: 8); _ = SecRandomCopyBytes(kSecRandomDefault, 8, &b)
        let p = String(b.map { alphabet[Int($0) % alphabet.count] })
        UserDefaults.standard.set(p, forKey: "sharePassword"); return p
    }
    static func setPassword(_ p: String) { UserDefaults.standard.set(p, forKey: "sharePassword") }
    static func newPassword() { UserDefaults.standard.removeObject(forKey: "sharePassword"); _ = password }
    static var screenAllowed: Bool { CGPreflightScreenCaptureAccess() }
    static var inputAllowed: Bool { CGPreflightPostEventAccess() }
}

/// The latest picture of the main display: 0x00RRGGBB per pixel
final class Frame {
    let width: Int, height: Int
    var px: [UInt32]
    init(width: Int, height: Int, px: [UInt32]) { self.width = width; self.height = height; self.px = px }
}

final class VNCServer: NSObject, SCStreamOutput, SCStreamDelegate {
    static let shared = VNCServer()
    let q = DispatchQueue(label: "vnc.server")
    private var listener: NWListener?
    private var clients: [ObjectIdentifier: VNCClient] = [:]
    private(set) var frame: Frame?
    private var stream: SCStream?
    private var capturing = false
    private(set) var displayBounds = CGRect.zero   // global points, top-left origin (CGEvent's coordinates)
    var onChange: (() -> Void)?                     // main thread: listening / client count changed
    private(set) var listening = false
    private(set) var lastError = ""
    private var clipTimer: Timer?
    private var clipCount = NSPasteboard.general.changeCount

    var clientCount: Int { q.sync { clients.values.filter { $0.ready }.count } }

    func start() {
        guard listener == nil else { return }
        lastError = ""
        do {
            let params = NWParameters.tcp
            params.allowLocalEndpointReuse = true
            let l = try NWListener(using: params, on: NWEndpoint.Port(rawValue: SHARE_PORT)!)
            l.stateUpdateHandler = { [weak self] st in
                guard let self else { return }
                switch st {
                case .ready: self.listening = true
                case .failed(let e): self.listening = false; self.lastError = "port \(SHARE_PORT): \(e)"; self.listener?.cancel(); self.listener = nil
                case .cancelled: self.listening = false
                default: break
                }
                DispatchQueue.main.async { self.onChange?() }
            }
            l.newConnectionHandler = { [weak self] c in self?.accept(c) }
            l.start(queue: q)
            listener = l
        } catch {
            lastError = "port \(SHARE_PORT): \(error)"
        }
        clipTimer?.invalidate()
        clipTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.clipTick() }
        onChange?()
    }

    func stop() {
        listener?.cancel(); listener = nil; listening = false
        clipTimer?.invalidate(); clipTimer = nil
        q.async {
            for c in self.clients.values { c.close() }
            self.clients = [:]
            self.stopCapture()
        }
        DispatchQueue.main.async { self.onChange?() }
    }

    private func accept(_ c: NWConnection) {
        let client = VNCClient(conn: c, server: self)
        clients[ObjectIdentifier(client)] = client
        client.start()
    }

    func removed(_ c: VNCClient) {   // on q
        clients.removeValue(forKey: ObjectIdentifier(c))
        if !clients.values.contains(where: { $0.ready }) { stopCapture() }
        DispatchQueue.main.async { self.onChange?() }
    }

    /// a client logged in: the picture starts (only while someone watches)
    func clientReady(_ c: VNCClient) {   // on q
        DispatchQueue.main.async { self.onChange?() }
        startCapture()
    }

    // MARK: the picture (ScreenCaptureKit)

    private func startCapture() {   // on q
        guard !capturing else { return }
        capturing = true
        SCShareableContent.getExcludingDesktopWindows(false, onScreenWindowsOnly: true) { [weak self] content, err in
            guard let self else { return }
            let main = CGMainDisplayID()
            guard let content, let d = content.displays.first(where: { $0.displayID == main }) ?? content.displays.first else {
                self.q.async { self.capturing = false; self.lastError = "no display to capture: \(err?.localizedDescription ?? "Screen Recording not allowed")" }
                DispatchQueue.main.async { self.onChange?() }
                return
            }
            let cfg = SCStreamConfiguration()
            cfg.width = d.width; cfg.height = d.height          // points: the Mac's own size, a quarter of the Retina pixels
            cfg.pixelFormat = kCVPixelFormatType_32BGRA
            cfg.minimumFrameInterval = CMTime(value: 1, timescale: 15)
            cfg.showsCursor = true
            cfg.queueDepth = 3
            let filter = SCContentFilter(display: d, excludingWindows: [])
            let s = SCStream(filter: filter, configuration: cfg, delegate: self)
            do { try s.addStreamOutput(self, type: .screen, sampleHandlerQueue: DispatchQueue(label: "vnc.capture")) }
            catch { self.q.async { self.capturing = false; self.lastError = "capture: \(error)" }; return }
            self.q.async { self.displayBounds = CGDisplayBounds(d.displayID); self.stream = s }
            s.startCapture { e in
                if let e { self.q.async { self.capturing = false; self.stream = nil; self.lastError = "capture: \(e.localizedDescription)" }
                    DispatchQueue.main.async { self.onChange?() } }
            }
        }
    }

    private func stopCapture() {   // on q
        guard capturing else { return }
        capturing = false
        stream?.stopCapture { _ in }
        stream = nil
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        q.async { self.capturing = false; self.stream = nil; self.lastError = "capture stopped: \(error.localizedDescription)" }
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen, sb.isValid else { return }
        if let att = (CMSampleBufferGetSampleAttachmentsArray(sb, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]])?.first,
           let raw = att[.status] as? Int, let st = SCFrameStatus(rawValue: raw), st != .complete { return }
        guard let pb = CMSampleBufferGetImageBuffer(sb) else { return }
        CVPixelBufferLockBaseAddress(pb, .readOnly)
        let w = CVPixelBufferGetWidth(pb), h = CVPixelBufferGetHeight(pb), bpr = CVPixelBufferGetBytesPerRow(pb)
        guard let base = CVPixelBufferGetBaseAddress(pb) else { CVPixelBufferUnlockBaseAddress(pb, .readOnly); return }
        var px = [UInt32](repeating: 0, count: w * h)
        px.withUnsafeMutableBytes { dst in
            for r in 0..<h { memcpy(dst.baseAddress! + r * w * 4, base + r * bpr, w * 4) }
        }
        CVPixelBufferUnlockBaseAddress(pb, .readOnly)
        let f = Frame(width: w, height: h, px: px)
        q.async {
            self.frame = f
            for c in self.clients.values where c.ready { c.frameArrived() }
        }
    }

    // MARK: the clipboard: the Mac's text goes to every viewer when it changes

    private func clipTick() {
        let pb = NSPasteboard.general
        guard pb.changeCount != clipCount else { return }
        clipCount = pb.changeCount
        guard let t = pb.string(forType: .string) else { return }
        q.async { for c in self.clients.values where c.ready { c.sendCutText(t) } }
    }
    func clientCut(_ text: String) {
        DispatchQueue.main.async {
            let pb = NSPasteboard.general
            pb.clearContents(); pb.setString(text, forType: .string)
            self.clipCount = pb.changeCount
        }
    }

    // MARK: input (CGEvent)

    private var buttons: UInt8 = 0
    private var lastClick = (time: Date.distantPast, x: 0.0, y: 0.0, count: 1)
    private var flags = CGEventFlags()

    func pointer(_ fx: Int, _ fy: Int, _ mask: UInt8, fbW: Int, fbH: Int) {   // on q
        guard Share.inputAllowed, fbW > 0, fbH > 0 else { return }
        let b = displayBounds
        let p = CGPoint(x: b.minX + Double(fx) * b.width / Double(fbW), y: b.minY + Double(fy) * b.height / Double(fbH))
        let src = CGEventSource(stateID: .hidSystemState)
        let changed = mask ^ buttons
        func post(_ t: CGEventType, _ btn: CGMouseButton, clicks: Int = 1) {
            let e = CGEvent(mouseEventSource: src, mouseType: t, mouseCursorPosition: p, mouseButton: btn)
            e?.setIntegerValueField(.mouseEventClickState, value: Int64(clicks)); e?.flags = flags
            e?.post(tap: .cghidEventTap)
        }
        // wheel: buttons 4/5 up/down, 6/7 left/right (pressed = one notch)
        let wheel: [(UInt8, Int32, Int32)] = [(8, 3, 0), (16, -3, 0), (32, 0, 3), (64, 0, -3)]
        for (bit, dy, dx) in wheel where mask & bit != 0 && buttons & bit == 0 {
            CGEvent(scrollWheelEvent2Source: src, units: .line, wheelCount: 2, wheel1: dy, wheel2: dx, wheel3: 0)?.post(tap: .cghidEventTap)
        }
        let pairs: [(UInt8, CGEventType, CGEventType, CGMouseButton)] = [
            (1, .leftMouseDown, .leftMouseUp, .left), (4, .rightMouseDown, .rightMouseUp, .right), (2, .otherMouseDown, .otherMouseUp, .center)]
        var clicked = false
        for (bit, down, up, btn) in pairs where changed & bit != 0 {
            clicked = true
            if mask & bit != 0 {
                let now = Date()
                if now.timeIntervalSince(lastClick.time) < 0.4 && abs(lastClick.x - p.x) < 5 && abs(lastClick.y - p.y) < 5 {
                    lastClick.count += 1 } else { lastClick.count = 1 }
                lastClick.time = now; lastClick.x = p.x; lastClick.y = p.y
                post(down, btn, clicks: lastClick.count)
            } else {
                post(up, btn, clicks: lastClick.count)
            }
        }
        if !clicked {
            if mask & 1 != 0 { post(.leftMouseDragged, .left) }
            else if mask & 4 != 0 { post(.rightMouseDragged, .right) }
            else if mask & 2 != 0 { post(.otherMouseDragged, .center) }
            else { post(.mouseMoved, .left) }
        }
        buttons = mask
    }

    // X keysyms → Mac virtual key codes (ANSI layout); characters not here are typed as Unicode
    static let specials: [UInt32: UInt16] = [
        0xff08: 51, 0xff09: 48, 0xff0d: 36, 0xff1b: 53, 0xffff: 117, 0xff50: 115, 0xff51: 123, 0xff52: 126, 0xff53: 124,
        0xff54: 125, 0xff55: 116, 0xff56: 121, 0xff57: 119, 0xff63: 114, 0xff8d: 76, 0x20: 49,
        0xffbe: 122, 0xffbf: 120, 0xffc0: 99, 0xffc1: 118, 0xffc2: 96, 0xffc3: 97, 0xffc4: 98, 0xffc5: 100, 0xffc6: 101,
        0xffc7: 109, 0xffc8: 103, 0xffc9: 111]
    static let modifiers: [UInt32: (UInt16, CGEventFlags)] = [
        0xffe1: (56, .maskShift), 0xffe2: (60, .maskShift), 0xffe3: (59, .maskControl), 0xffe4: (62, .maskControl),
        0xffe7: (55, .maskCommand), 0xffe8: (54, .maskCommand), 0xffeb: (55, .maskCommand), 0xffec: (54, .maskCommand),
        0xffe9: (58, .maskAlternate), 0xffea: (61, .maskAlternate)]
    static let plain: [Character: UInt16] = [
        "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14,
        "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27,
        "8": 28, "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "l": 37, "j": 38, "'": 39, "k": 40, ";": 41,
        "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47, "`": 50]
    static let shifted: [Character: Character] = [
        "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8", "(": "9", ")": "0", "_": "-", "+": "=",
        "{": "[", "}": "]", "|": "\\", ":": ";", "\"": "'", "<": ",", ">": ".", "?": "/", "~": "`"]

    func key(_ ks: UInt32, down: Bool) {   // on q
        guard Share.inputAllowed else { return }
        let src = CGEventSource(stateID: .hidSystemState)
        if let m = VNCServer.modifiers[ks] {
            let (code, f) = m
            if down { flags.insert(f) } else { flags.remove(f) }
            let e = CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: down)
            e?.type = .flagsChanged; e?.flags = flags; e?.post(tap: .cghidEventTap)
            return
        }
        var code: UInt16? = VNCServer.specials[ks]
        var extra = CGEventFlags()
        var unicode: String?
        if code == nil {
            let scalar = ks >= 0x0100_0000 ? ks - 0x0100_0000 : ks
            if ks <= 0xff || ks >= 0x0100_0000, let u = Unicode.Scalar(scalar) {
                let ch = Character(u)
                let lower = ch.lowercased().first ?? ch
                if let c = VNCServer.plain[ch] { code = c }
                else if ch.isUppercase, let c = VNCServer.plain[lower] { code = c; extra = .maskShift }
                else if let base = VNCServer.shifted[ch], let c = VNCServer.plain[base] { code = c; extra = .maskShift }
                else { unicode = String(ch) }
            }
        }
        if code == nil && unicode == nil { return }   // a keysym this Mac has no key for
        let e = CGEvent(keyboardEventSource: src, virtualKey: code ?? 0, keyDown: down)
        e?.flags = flags.union(extra)
        if let unicode {
            let utf16 = Array(unicode.utf16)
            e?.keyboardSetUnicodeString(stringLength: utf16.count, unicodeString: utf16)
        }
        e?.post(tap: .cghidEventTap)
    }
}

/// One viewer connected to this Mac
final class VNCClient {
    let conn: NWConnection
    unowned let server: VNCServer
    private var inbox = Data()
    private enum Stage { case version, security, auth, clientInit, normal }
    private var stage = Stage.version
    private var challenge = [UInt8](repeating: 0, count: 16)
    private(set) var ready = false
    // the viewer's pixel format
    private var bpp = 32, bigEndian = false, trueColour = true
    private var rmax = 255, gmax = 255, bmax = 255, rs = 16, gs = 8, bs = 0
    private var zrle = false, desktopSize = false
    private var pending = false, pendingFull = false
    private var sent: [UInt32] = []          // what the viewer has, to send only the tiles that changed
    private var fbW = 0, fbH = 0
    private var zs = z_stream(), zInit = false
    private var closed = false

    init(conn: NWConnection, server: VNCServer) { self.conn = conn; self.server = server }

    func start() {
        conn.stateUpdateHandler = { [weak self] st in
            switch st {
            case .failed, .cancelled: self?.close()
            default: break
            }
        }
        conn.start(queue: server.q)
        send(Array("RFB 003.008\n".utf8))
        receive()
    }

    func close() {   // on q
        guard !closed else { return }
        closed = true; ready = false
        conn.cancel()
        if zInit { deflateEnd(&zs); zInit = false }
        server.removed(self)
    }

    private func send(_ b: [UInt8]) { conn.send(content: Data(b), completion: .contentProcessed { _ in }) }
    private func send(_ d: Data) { conn.send(content: d, completion: .contentProcessed { _ in }) }

    private func receive() {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 1 << 16) { [weak self] d, _, done, err in
            guard let self, !self.closed else { return }
            if let d { self.inbox.append(d); self.parse() }
            if done || err != nil { self.close() } else if !self.closed { self.receive() }
        }
    }

    private func take(_ n: Int) -> [UInt8]? {
        guard inbox.count >= n else { return nil }
        let b = [UInt8](inbox.prefix(n)); inbox.removeFirst(n); return b
    }
    private func peek(_ i: Int) -> UInt8 { inbox[inbox.startIndex + i] }
    private func be16(_ v: Int) -> [UInt8] { [UInt8((v >> 8) & 0xff), UInt8(v & 0xff)] }
    private func be32(_ v: UInt32) -> [UInt8] { [UInt8(v >> 24), UInt8((v >> 16) & 0xff), UInt8((v >> 8) & 0xff), UInt8(v & 0xff)] }
    private func u16(_ b: [UInt8], _ i: Int) -> Int { Int(b[i]) << 8 | Int(b[i + 1]) }
    private func u32(_ b: [UInt8], _ i: Int) -> Int { Int(b[i]) << 24 | Int(b[i + 1]) << 16 | Int(b[i + 2]) << 8 | Int(b[i + 3]) }

    private func fail(_ why: String) {
        send(be32(1) + be32(UInt32(why.utf8.count)) + Array(why.utf8))
        server.q.asyncAfter(deadline: .now() + 0.5) { [weak self] in self?.close() }
    }

    private func parse() {
        while !closed {
            switch stage {
            case .version:
                guard let v = take(12) else { return }
                guard String(bytes: v, encoding: .ascii)?.hasPrefix("RFB 003.") == true else { close(); return }
                // one security type: VNC password, or None when the password is empty (v43)
                send([1, Share.password.isEmpty ? 1 : 2])
                stage = .security
            case .security:
                guard let t = take(1) else { return }
                if Share.password.isEmpty {
                    guard t[0] == 1 else { fail("this Mac shares without a password"); return }
                    guard Share.screenAllowed else { fail("Screen Recording not allowed on that Mac yet (PERMISSIONS there)"); return }
                    send(be32(0)); stage = .clientInit; continue
                }
                guard t[0] == 2 else { fail("only VNC password auth"); return }
                _ = SecRandomCopyBytes(kSecRandomDefault, 16, &challenge)
                send(challenge); stage = .auth
            case .auth:
                guard let r = take(16) else { return }
                guard r == RFB.des(challenge, key: Share.password) else { fail("wrong password"); return }
                guard Share.screenAllowed else {
                    fail("Screen Recording not allowed on that Mac yet (PERMISSIONS there)"); return }
                send(be32(0)); stage = .clientInit
            case .clientInit:
                guard take(1) != nil else { return }
                stage = .normal
                waitForFirstFrame(tries: 0)
                return
            case .normal:
                guard let t = inbox.first else { return }
                switch t {
                case 0:
                    guard let b = take(20) else { return }
                    bpp = Int(b[4]); bigEndian = b[6] != 0; trueColour = b[7] != 0
                    rmax = u16(b, 8); gmax = u16(b, 10); bmax = u16(b, 12); rs = Int(b[14]); gs = Int(b[15]); bs = Int(b[16])
                    if ![8, 16, 32].contains(bpp) || !trueColour { fail("only true colour pixel formats"); return }
                    sent = []                                     // everything again in the new format
                case 2:
                    guard inbox.count >= 4 else { return }
                    let n = Int(peek(2)) << 8 | Int(peek(3))
                    guard let b = take(4 + 4 * n) else { return }
                    zrle = false; desktopSize = false
                    for i in 0..<n {
                        let e = Int32(bitPattern: UInt32(u32(b, 4 + 4 * i)))
                        if e == 16 { zrle = true }
                        if e == -223 { desktopSize = true }
                    }
                case 3:
                    guard let b = take(10) else { return }
                    pending = true
                    if b[1] == 0 { pendingFull = true }
                    update()
                case 4:
                    guard let b = take(8) else { return }
                    server.key(UInt32(u32(b, 4)), down: b[1] != 0)
                case 5:
                    guard let b = take(6) else { return }
                    server.pointer(u16(b, 2), u16(b, 4), b[1], fbW: fbW, fbH: fbH)
                case 6:
                    guard inbox.count >= 8 else { return }
                    let n = Int(peek(4)) << 24 | Int(peek(5)) << 16 | Int(peek(6)) << 8 | Int(peek(7))
                    guard let b = take(8 + n) else { return }
                    let bytes = Array(b[8...])
                    server.clientCut(String(bytes: bytes, encoding: .utf8) ?? String(bytes: bytes, encoding: .isoLatin1) ?? "")
                default:
                    close(); return
                }
            }
        }
    }

    /// ServerInit needs the size: wait (up to 5 s) for the first picture from ScreenCaptureKit
    private func waitForFirstFrame(tries: Int) {
        if !ready && tries == 0 { server.clientReady(self) }
        if let f = server.frame {
            fbW = f.width; fbH = f.height
            let name = Array("\((SCDynamicStoreCopyComputerName(nil, nil) as String?) ?? "Mac") (\(APP_NAME))".utf8)
            var m = be16(fbW) + be16(fbH)
            m += [32, 24, 0, 1] + be16(255) + be16(255) + be16(255) + [16, 8, 0, 0, 0, 0]
            m += be32(UInt32(name.count)) + name
            send(m)
            ready = true
            parse()
            return
        }
        if tries > 50 { fail("no picture from the Mac (Screen Recording?)"); return }
        server.q.asyncAfter(deadline: .now() + 0.1) { [weak self] in self?.waitForFirstFrame(tries: tries + 1) }
    }

    func frameArrived() { if pending { update() } }

    // MARK: updates

    private func update() {
        guard ready, pending, let f = server.frame else { return }
        var out: [UInt8] = []
        var rects = 0
        if f.width != fbW || f.height != fbH {
            guard desktopSize else { close(); return }
            fbW = f.width; fbH = f.height; sent = []
            out += be16(0) + be16(0) + be16(fbW) + be16(fbH) + be32(UInt32(bitPattern: -223)); rects += 1
        }
        let full = pendingFull || sent.count != fbW * fbH
        var tiles: [(Int, Int, Int, Int)] = []
        let T = 64
        var ty = 0
        while ty < fbH {
            let th = min(T, fbH - ty)
            var tx = 0
            while tx < fbW {
                let tw = min(T, fbW - tx)
                if full || changed(f, tx, ty, tw, th) { tiles.append((tx, ty, tw, th)) }
                tx += T
            }
            ty += T
        }
        if tiles.isEmpty && rects == 0 { return }   // nothing new: the request waits for the next picture
        pending = false; pendingFull = false
        let useZ = zrle && bpp == 32 && cpixelFits
        if useZ && !zInit {
            if deflateInit_(&zs, 6, ZLIB_VERSION, Int32(MemoryLayout<z_stream>.size)) == Z_OK { zInit = true }
        }
        var body: [UInt8] = []
        for (x, y, w, h) in tiles {
            body += be16(x) + be16(y) + be16(w) + be16(h)
            if useZ && zInit {
                body += be32(16)
                let z = compress(zrleTile(f, x, y, w, h))
                body += be32(UInt32(z.count)) + z
            } else {
                body += be32(0) + raw(f, x, y, w, h)
            }
            rects += 1
        }
        if sent.count != fbW * fbH { sent = f.px } else { for (x, y, w, h) in tiles { copyTile(f, x, y, w, h) } }
        send([0, 0] + be16(rects) + out + body)
    }

    private func changed(_ f: Frame, _ x: Int, _ y: Int, _ w: Int, _ h: Int) -> Bool {
        for r in y..<(y + h) {
            let o = r * fbW + x
            for i in o..<(o + w) where f.px[i] & 0xFFFFFF != sent[i] & 0xFFFFFF { return true }
        }
        return false
    }
    private func copyTile(_ f: Frame, _ x: Int, _ y: Int, _ w: Int, _ h: Int) {
        for r in y..<(y + h) { let o = r * fbW + x; for i in o..<(o + w) { sent[i] = f.px[i] } }
    }

    /// the pixel in the viewer's format
    @inline(__always) private func conv(_ p: UInt32) -> UInt32 {
        let r = (p >> 16) & 0xff, g = (p >> 8) & 0xff, b = p & 0xff
        if rmax == 255 && gmax == 255 && bmax == 255 { return r << UInt32(rs) | g << UInt32(gs) | b << UInt32(bs) }
        return (r * UInt32(rmax) / 255) << UInt32(rs) | (g * UInt32(gmax) / 255) << UInt32(gs) | (b * UInt32(bmax) / 255) << UInt32(bs)
    }
    private func putPixel(_ v: UInt32, _ out: inout [UInt8]) {
        switch bpp {
        case 8: out.append(UInt8(v & 0xff))
        case 16:
            if bigEndian { out.append(UInt8((v >> 8) & 0xff)); out.append(UInt8(v & 0xff)) }
            else { out.append(UInt8(v & 0xff)); out.append(UInt8((v >> 8) & 0xff)) }
        default:
            if bigEndian { out.append(UInt8(v >> 24)); out.append(UInt8((v >> 16) & 0xff)); out.append(UInt8((v >> 8) & 0xff)); out.append(UInt8(v & 0xff)) }
            else { out.append(UInt8(v & 0xff)); out.append(UInt8((v >> 8) & 0xff)); out.append(UInt8((v >> 16) & 0xff)); out.append(UInt8(v >> 24)) }
        }
    }
    private func raw(_ f: Frame, _ x: Int, _ y: Int, _ w: Int, _ h: Int) -> [UInt8] {
        var out = [UInt8](); out.reserveCapacity(w * h * bpp / 8)
        for r in y..<(y + h) { let o = r * fbW; for c in x..<(x + w) { putPixel(conv(f.px[o + c]), &out) } }
        return out
    }

    /// ZRLE's 3-byte CPIXEL works when every colour fits in the low three bytes of the 32-bit pixel
    private var cpixelFits: Bool { rmax <= 255 && gmax <= 255 && bmax <= 255 && max(rs, gs, bs) <= 16 }
    private func cpixel(_ v: UInt32, _ out: inout [UInt8]) {
        if bigEndian { out.append(UInt8((v >> 16) & 0xff)); out.append(UInt8((v >> 8) & 0xff)); out.append(UInt8(v & 0xff)) }
        else { out.append(UInt8(v & 0xff)); out.append(UInt8((v >> 8) & 0xff)); out.append(UInt8((v >> 16) & 0xff)) }
    }
    /// one ZRLE tile (≤ 64×64): solid (1) or raw (0); zlib does the rest
    private func zrleTile(_ f: Frame, _ x: Int, _ y: Int, _ w: Int, _ h: Int) -> [UInt8] {
        let first = f.px[y * fbW + x] & 0xFFFFFF
        var solid = true
        outer: for r in y..<(y + h) { let o = r * fbW; for c in x..<(x + w) where f.px[o + c] & 0xFFFFFF != first { solid = false; break outer } }
        var out = [UInt8]()
        if solid { out.append(1); cpixel(conv(first), &out); return out }
        out.reserveCapacity(1 + w * h * 3); out.append(0)
        for r in y..<(y + h) { let o = r * fbW; for c in x..<(x + w) { cpixel(conv(f.px[o + c]), &out) } }
        return out
    }
    private func compress(_ input: [UInt8]) -> [UInt8] {
        var src = input
        var out = [UInt8]()
        var chunk = [UInt8](repeating: 0, count: 1 << 16)
        src.withUnsafeMutableBytes { sp in
            zs.next_in = sp.baseAddress!.assumingMemoryBound(to: Bytef.self); zs.avail_in = uInt(sp.count)
            repeat {
                chunk.withUnsafeMutableBytes { op in
                    zs.next_out = op.baseAddress!.assumingMemoryBound(to: Bytef.self); zs.avail_out = uInt(op.count)
                    _ = deflate(&zs, Z_SYNC_FLUSH)
                }
                out.append(contentsOf: chunk[0..<(chunk.count - Int(zs.avail_out))])
            } while zs.avail_out == 0
        }
        return out
    }

    func sendCutText(_ t: String) {
        let b = Array(t.data(using: .isoLatin1, allowLossyConversion: true) ?? Data())
        send([3, 0, 0, 0] + be32(UInt32(b.count)) + b)
    }
}
