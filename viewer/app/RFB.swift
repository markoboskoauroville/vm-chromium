// RFB.swift: the VNC (RFB 3.8) client of Chromium Virtual Machine (Mantra). Modelled on Mantra Remote's Rfb.kt.
// VncAuth (DES), 32-bit true colour, Raw / CopyRect / ZRLE, DesktopSize + ExtendedDesktopSize (the VM follows the
// window), pointer and keys. The clipboard does not go through RFB's Latin-1 cut text: a ServerCutText only says
// "the VM clipboard changed", and the text itself comes as UTF-8 from vm-agent (Agent.swift).
import Foundation
import CommonCrypto
import zlib

protocol RFBDelegate: AnyObject {
    func rfbConnected(name: String, width: Int, height: Int)
    func rfbFrame()
    func rfbResized(width: Int, height: Int)
    func rfbClipboardChanged()
    func rfbClosed(reason: String)
}

final class RFB {
    weak var delegate: RFBDelegate?
    private var input: InputStream?
    private var output: OutputStream?
    private let writeLock = NSLock()
    private var rbuf = [UInt8](repeating: 0, count: 1 << 16)
    private var rpos = 0, rlen = 0
    private var closed = false

    // The picture: 0xXXRRGGBB per pixel, read by the view under `lock`.
    let lock = NSLock()
    private(set) var width = 0, height = 0
    private(set) var pixels = [UInt32]()
    private(set) var bytesIn: Int64 = 0

    private(set) var canResize = false        // the server announced ExtendedDesktopSize
    private var screenId: UInt32 = 0
    private var zs = z_stream()
    private var zInit = false

    // MARK: connect

    func connect(host: String, port: Int, password: String) {
        Thread.detachNewThread { [weak self] in
            guard let self else { return }
            do { try self.run(host: host, port: port, password: password) }
            catch { self.finish("\(error)") }
        }
    }

    func close() {
        closed = true
        input?.close(); output?.close()
    }

    private func finish(_ why: String) {
        input?.close(); output?.close()
        if zInit { inflateEnd(&zs); zInit = false }
        let wasClosed = closed
        DispatchQueue.main.async { [weak self] in if !wasClosed { self?.delegate?.rfbClosed(reason: why) } }
    }

    struct Failure: Error, CustomStringConvertible { let description: String }

    private func run(host: String, port: Int, password: String) throws {
        var i: InputStream?, o: OutputStream?
        Stream.getStreamsToHost(withName: host, port: port, inputStream: &i, outputStream: &o)
        guard let i, let o else { throw Failure(description: "no connection") }
        input = i; output = o
        i.open(); o.open()
        // Unscheduled streams open in the background: a write before .open fails and the server sees no version.
        let t0 = Date()
        while o.streamStatus == .opening || o.streamStatus == .notOpen {
            if Date().timeIntervalSince(t0) > 10 { throw Failure(description: "no answer from \(host):\(port)") }
            Thread.sleep(forTimeInterval: 0.02)
        }
        if o.streamStatus == .error { throw Failure(description: o.streamError?.localizedDescription ?? "cannot connect") }

        let version = try read(12)
        guard String(bytes: version, encoding: .ascii)?.hasPrefix("RFB ") == true else { throw Failure(description: "not a VNC server") }
        try write(Array("RFB 003.008\n".utf8))

        let n = Int(try u8())
        if n == 0 { throw Failure(description: try reason()) }
        let types = try read(n)
        guard types.contains(2) else { throw Failure(description: "the server does not offer VNC password auth (types \(types))") }
        try write([2])
        let challenge = try read(16)
        try write(des(challenge, key: password))
        if try u32() != 0 { throw Failure(description: "VNC password refused: " + ((try? reason()) ?? "")) }

        try write([1])                                            // ClientInit: shared
        let w = Int(try u16()), h = Int(try u16())
        _ = try read(16)                                          // the server's pixel format: we set ours
        let name = String(decoding: try read(Int(try u32())), as: UTF8.self)
        resize(w, h)

        // SetPixelFormat: 32 bpp, depth 24, little endian, true colour, R<<16 G<<8 B
        var pf: [UInt8] = [0, 0, 0, 0, 32, 24, 0, 1]
        pf += be16(255) + be16(255) + be16(255) + [16, 8, 0, 0, 0, 0]
        try write(pf)
        // SetEncodings: ZRLE, CopyRect, Raw, ExtendedDesktopSize, DesktopSize, LastRect
        let enc: [Int32] = [16, 1, 0, -308, -223, -224]
        var se: [UInt8] = [2, 0] + be16(enc.count)
        for e in enc { se += be32(UInt32(bitPattern: e)) }
        try write(se)
        DispatchQueue.main.async { self.delegate?.rfbConnected(name: name, width: w, height: h) }
        try request(incremental: false)

        while !closed {
            let t = try u8()
            switch t {
            case 0: try framebufferUpdate(); try request(incremental: true)
            case 1: _ = try read(1); _ = try u16(); let k = Int(try u16()); _ = try read(k * 6)
            case 2: break                                            // bell
            case 3: _ = try read(3); _ = try read(Int(try u32()))   // the VM clipboard changed: fetch it as UTF-8
                    DispatchQueue.main.async { self.delegate?.rfbClipboardChanged() }
            default: throw Failure(description: "unknown server message \(t)")
            }
        }
        finish("closed")
    }

    // MARK: client → server

    func request(incremental: Bool) throws {
        lock.lock(); let w = width, h = height; lock.unlock()
        try write([3, incremental ? 1 : 0] + be16(0) + be16(0) + be16(w) + be16(h))
    }

    func pointer(x: Int, y: Int, buttons: UInt8) {
        try? write([5, buttons] + be16(max(0, x)) + be16(max(0, y)))
    }

    func key(_ keysym: UInt32, down: Bool) {
        try? write([4, down ? 1 : 0, 0, 0] + be32(keysym))
    }

    /// Asks the VM to take this size (the window's). Only after the server said it can.
    func setDesktopSize(_ w: Int, _ h: Int) {
        guard canResize, w >= 200, h >= 150 else { return }
        var m: [UInt8] = [251, 0] + be16(w) + be16(h) + [1, 0]
        m += be32(screenId) + be16(0) + be16(0) + be16(w) + be16(h) + be32(0)
        try? write(m)
    }

    // MARK: server → client

    private func framebufferUpdate() throws {
        _ = try read(1)
        let n = Int(try u16())
        for _ in 0..<n {
            let x = Int(try u16()), y = Int(try u16()), w = Int(try u16()), h = Int(try u16())
            let e = Int32(bitPattern: try u32())
            switch e {
            case 0:    try raw(x, y, w, h)
            case 1:    try copyRect(x, y, w, h)
            case 16:   try zrle(x, y, w, h)
            case -223: resize(w, h); DispatchQueue.main.async { self.delegate?.rfbResized(width: w, height: h) }
            case -308:
                let k = Int(try u8()); _ = try read(3)
                for j in 0..<k { let s = try read(16); if j == 0 { screenId = UInt32(s[0]) << 24 | UInt32(s[1]) << 16 | UInt32(s[2]) << 8 | UInt32(s[3]) } }
                canResize = true
                if y == 0 && (w != width || h != height) {           // status 0: the size took
                    resize(w, h); DispatchQueue.main.async { self.delegate?.rfbResized(width: w, height: h) }
                }
            case -224: DispatchQueue.main.async { self.delegate?.rfbFrame() }; return
            default: throw Failure(description: "unexpected encoding \(e)")
            }
        }
        DispatchQueue.main.async { self.delegate?.rfbFrame() }
    }

    private func resize(_ w: Int, _ h: Int) {
        lock.lock(); width = w; height = h; pixels = [UInt32](repeating: 0xFF202124, count: w * h); lock.unlock()
    }

    private func raw(_ x: Int, _ y: Int, _ w: Int, _ h: Int) throws {
        let b = try read(w * h * 4)
        lock.lock(); defer { lock.unlock() }
        b.withUnsafeBytes { p in
            let s = p.bindMemory(to: UInt32.self)
            for r in 0..<h where y + r < height {
                for c in 0..<w where x + c < width { pixels[(y + r) * width + x + c] = s[r * w + c] | 0xFF000000 }
            }
        }
    }

    private func copyRect(_ x: Int, _ y: Int, _ w: Int, _ h: Int) throws {
        let sx = Int(try u16()), sy = Int(try u16())
        lock.lock(); defer { lock.unlock() }
        var tmp = [UInt32](repeating: 0, count: w * h)
        for r in 0..<h { for c in 0..<w { tmp[r * w + c] = pixels[(sy + r) * width + sx + c] } }
        for r in 0..<h { for c in 0..<w { pixels[(y + r) * width + x + c] = tmp[r * w + c] } }
    }

    // ZRLE: one zlib stream for the whole connection; 64×64 tiles; CPIXEL = 3 bytes (B, G, R).
    private var zout = [UInt8](), zp = 0

    private func zrle(_ x: Int, _ y: Int, _ w: Int, _ h: Int) throws {
        let len = Int(try u32())
        var comp = try read(len)
        if !zInit {
            guard inflateInit_(&zs, ZLIB_VERSION, Int32(MemoryLayout<z_stream>.size)) == Z_OK else { throw Failure(description: "zlib") }
            zInit = true
        }
        zout.removeAll(keepingCapacity: true); zp = 0
        var chunk = [UInt8](repeating: 0, count: 1 << 18)
        try comp.withUnsafeMutableBytes { cp in
            zs.next_in = cp.baseAddress!.assumingMemoryBound(to: Bytef.self); zs.avail_in = uInt(len)
            repeat {
                let ret: Int32 = chunk.withUnsafeMutableBytes { op in
                    zs.next_out = op.baseAddress!.assumingMemoryBound(to: Bytef.self); zs.avail_out = uInt(op.count)
                    return inflate(&zs, Z_SYNC_FLUSH)
                }
                if ret != Z_OK && ret != Z_BUF_ERROR && ret != Z_STREAM_END { throw Failure(description: "zlib inflate \(ret)") }
                let got = chunk.count - Int(zs.avail_out)
                zout.append(contentsOf: chunk[0..<got])
                if got == 0 { break }
            } while zs.avail_in > 0 || zs.avail_out == 0
        }
        lock.lock(); defer { lock.unlock() }
        var ty = y
        while ty < y + h {
            let th = min(64, y + h - ty)
            var tx = x
            while tx < x + w {
                let tw = min(64, x + w - tx)
                try tile(tx, ty, tw, th)
                tx += 64
            }
            ty += 64
        }
    }

    @inline(__always) private func zb() throws -> Int {
        guard zp < zout.count else { throw Failure(description: "ZRLE data ran out") }
        defer { zp += 1 }; return Int(zout[zp])
    }
    @inline(__always) private func cpixel() throws -> UInt32 {
        guard zp + 3 <= zout.count else { throw Failure(description: "ZRLE data ran out") }
        let v = UInt32(zout[zp]) | UInt32(zout[zp + 1]) << 8 | UInt32(zout[zp + 2]) << 16
        zp += 3; return v | 0xFF000000
    }
    @inline(__always) private func put(_ x: Int, _ y: Int, _ c: UInt32) {
        if x < width && y < height { pixels[y * width + x] = c }
    }

    private func tile(_ x: Int, _ y: Int, _ w: Int, _ h: Int) throws {
        let sub = try zb()
        switch sub {
        case 0:
            for r in 0..<h { for c in 0..<w { put(x + c, y + r, try cpixel()) } }
        case 1:
            let c = try cpixel(); for r in 0..<h { for k in 0..<w { put(x + k, y + r, c) } }
        case 2...16:
            var pal = [UInt32](); for _ in 0..<sub { pal.append(try cpixel()) }
            let bits = sub == 2 ? 1 : (sub <= 4 ? 2 : 4)
            let mask = (1 << bits) - 1
            for r in 0..<h {
                var byte = 0, left = 0
                for c in 0..<w {
                    if left == 0 { byte = try zb(); left = 8 }
                    left -= bits
                    put(x + c, y + r, pal[(byte >> left) & mask])
                }
            }
        case 128:
            var i = 0; let n = w * h
            while i < n {
                let c = try cpixel()
                var run = 1, b = 255
                while b == 255 { b = try zb(); run += b }
                for _ in 0..<run where i < n { put(x + i % w, y + i / w, c); i += 1 }
            }
        case 130...255:
            var pal = [UInt32](); for _ in 0..<(sub - 128) { pal.append(try cpixel()) }
            var i = 0; let n = w * h
            while i < n {
                var idx = try zb(), run = 1
                if idx & 128 != 0 { idx &= 127; var b = 255; while b == 255 { b = try zb(); run += b } }
                let c = pal[idx]
                for _ in 0..<run where i < n { put(x + i % w, y + i / w, c); i += 1 }
            }
        default:
            throw Failure(description: "ZRLE subencoding \(sub)")
        }
    }

    // MARK: bytes

    private func fill() throws {
        guard let input else { throw Failure(description: "closed") }
        let k = rbuf.withUnsafeMutableBytes { input.read($0.baseAddress!.assumingMemoryBound(to: UInt8.self), maxLength: $0.count) }
        if k <= 0 { throw Failure(description: k == 0 ? "the VM closed the connection" : (input.streamError?.localizedDescription ?? "read error")) }
        rpos = 0; rlen = k; bytesIn += Int64(k)
    }

    private func read(_ n: Int) throws -> [UInt8] {
        var out = [UInt8](); out.reserveCapacity(n)
        while out.count < n {
            if rpos == rlen { try fill() }
            let take = min(n - out.count, rlen - rpos)
            out.append(contentsOf: rbuf[rpos..<(rpos + take)]); rpos += take
        }
        return out
    }
    private func u8() throws -> UInt8 { if rpos == rlen { try fill() }; defer { rpos += 1 }; return rbuf[rpos] }
    private func u16() throws -> UInt16 { let b = try read(2); return UInt16(b[0]) << 8 | UInt16(b[1]) }
    private func u32() throws -> UInt32 { let b = try read(4); return UInt32(b[0]) << 24 | UInt32(b[1]) << 16 | UInt32(b[2]) << 8 | UInt32(b[3]) }
    private func reason() throws -> String { String(decoding: try read(Int(try u32())), as: UTF8.self) }

    private func write(_ b: [UInt8]) throws {
        guard let output else { throw Failure(description: "closed") }
        writeLock.lock(); defer { writeLock.unlock() }
        var off = 0
        while off < b.count {
            let k = b[off...].withUnsafeBufferPointer { output.write($0.baseAddress!, maxLength: $0.count) }
            if k <= 0 { throw Failure(description: "write failed") }
            off += k
        }
    }

    private func be16(_ v: Int) -> [UInt8] { [UInt8((v >> 8) & 0xff), UInt8(v & 0xff)] }
    private func be32(_ v: UInt32) -> [UInt8] { [UInt8(v >> 24), UInt8((v >> 16) & 0xff), UInt8((v >> 8) & 0xff), UInt8(v & 0xff)] }

    /// VncAuth: DES-ECB of the challenge with the password (8 bytes, each byte's bits reversed) as the key.
    private func des(_ challenge: [UInt8], key password: String) -> [UInt8] {
        var key = [UInt8](repeating: 0, count: 8)
        for (i, b) in Array(password.utf8.prefix(8)).enumerated() {
            var r: UInt8 = 0; for bit in 0..<8 where b & (1 << bit) != 0 { r |= 1 << (7 - bit) }
            key[i] = r
        }
        var out = [UInt8](repeating: 0, count: 16 + kCCBlockSizeDES)
        var moved = 0
        CCCrypt(CCOperation(kCCEncrypt), CCAlgorithm(kCCAlgorithmDES), CCOptions(kCCOptionECBMode),
                key, kCCKeySizeDES, nil, challenge, 16, &out, out.count, &moved)
        return Array(out.prefix(16))
    }
}
