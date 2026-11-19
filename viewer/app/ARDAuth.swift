// ARDAuth.swift: v39 (Marko, 19.11.2026: "built in server and viewer for VNC inside the app ... The user does not need to
// install anything"). Apple Remote Desktop authentication (RFB security type 30), the login a Mac's own Screen Sharing asks
// for: Diffie-Hellman with the server's generator and prime, MD5 of the shared secret as an AES-128 key, the user name and
// password (64 bytes each) encrypted with AES-128-ECB. The big numbers are done here (Montgomery), nothing external.
import Foundation
import CommonCrypto
import Security

enum ARDAuth {
    static func answer(generator: [UInt8], prime: [UInt8], serverPublic: [UInt8], user: String, password: String) -> ([UInt8], [UInt8]) {
        let n = prime.count
        var priv = [UInt8](repeating: 0, count: n)
        _ = SecRandomCopyBytes(kSecRandomDefault, n, &priv)
        let p = Big(bytes: prime), g = Big(bytes: generator), sp = Big(bytes: serverPublic), x = Big(bytes: priv)
        let myPub = Big.modPow(g, x, p).bytes(n)
        let secret = Big.modPow(sp, x, p).bytes(n)
        var key = [UInt8](repeating: 0, count: Int(CC_MD5_DIGEST_LENGTH))
        _ = CC_MD5(secret, CC_LONG(secret.count), &key)
        var creds = [UInt8](repeating: 0, count: 128)
        _ = SecRandomCopyBytes(kSecRandomDefault, 128, &creds)
        let u = Array(user.utf8.prefix(63)), pw = Array(password.utf8.prefix(63))
        for (i, b) in u.enumerated() { creds[i] = b }; creds[u.count] = 0
        for (i, b) in pw.enumerated() { creds[64 + i] = b }; creds[64 + pw.count] = 0
        var out = [UInt8](repeating: 0, count: 128 + kCCBlockSizeAES128)
        var moved = 0
        CCCrypt(CCOperation(kCCEncrypt), CCAlgorithm(kCCAlgorithmAES128), CCOptions(kCCOptionECBMode),
                key, kCCKeySizeAES128, nil, creds, 128, &out, out.count, &moved)
        return (Array(out.prefix(128)), myPub)
    }
}

/// A small unsigned big number: 32-bit limbs, least significant first. Only what modPow needs.
struct Big {
    var l: [UInt32]
    init(limbs: [UInt32]) { l = limbs }
    init(bytes b: [UInt8]) {   // big endian bytes
        var out = [UInt32](repeating: 0, count: max(1, (b.count + 3) / 4))
        for (i, byte) in b.reversed().enumerated() { out[i / 4] |= UInt32(byte) << (8 * UInt32(i % 4)) }
        l = out
    }
    /// big endian, exactly `n` bytes (left padded with zeros)
    func bytes(_ n: Int) -> [UInt8] {
        var out = [UInt8](repeating: 0, count: n)
        for i in 0..<n { let li = i / 4; if li < l.count { out[n - 1 - i] = UInt8((l[li] >> (8 * UInt32(i % 4))) & 0xff) } }
        return out
    }

    static func geq(_ a: [UInt32], _ m: [UInt32]) -> Bool {   // a has m.count limbs (+ maybe one more)
        if a.count > m.count && a[m.count] != 0 { return true }
        for i in stride(from: m.count - 1, through: 0, by: -1) where a[i] != m[i] { return a[i] > m[i] }
        return true
    }
    static func sub(_ a: inout [UInt32], _ m: [UInt32]) {
        var borrow: Int64 = 0
        for i in 0..<a.count {
            var d = Int64(a[i]) - (i < m.count ? Int64(m[i]) : 0) - borrow
            if d < 0 { d += 1 << 32; borrow = 1 } else { borrow = 0 }
            a[i] = UInt32(d)
        }
    }

    /// Montgomery product a·b·R⁻¹ mod m (CIOS), m odd, a and b < m, all `n` limbs
    static func mont(_ a: [UInt32], _ b: [UInt32], _ m: [UInt32], _ inv: UInt32) -> [UInt32] {
        let n = m.count
        var t = [UInt32](repeating: 0, count: n + 2)
        for i in 0..<n {
            var c: UInt64 = 0
            let bi = UInt64(b[i])
            for j in 0..<n {
                let s = UInt64(t[j]) + UInt64(a[j]) * bi + c
                t[j] = UInt32(truncatingIfNeeded: s); c = s >> 32
            }
            var s = UInt64(t[n]) + c
            t[n] = UInt32(truncatingIfNeeded: s); t[n + 1] = UInt32(s >> 32)
            let mm = UInt64(t[0] &* inv)
            s = UInt64(t[0]) + mm * UInt64(m[0]); c = s >> 32
            for j in 1..<n {
                s = UInt64(t[j]) + mm * UInt64(m[j]) + c
                t[j - 1] = UInt32(truncatingIfNeeded: s); c = s >> 32
            }
            s = UInt64(t[n]) + c
            t[n - 1] = UInt32(truncatingIfNeeded: s)
            t[n] = t[n + 1] + UInt32(s >> 32)
            t[n + 1] = 0
        }
        if geq(t, m) { sub(&t, m) }
        return Array(t.prefix(n))
    }

    /// base^exp mod m (m odd)
    static func modPow(_ base: Big, _ exp: Big, _ mod: Big) -> Big {
        var m = mod.l
        while m.count > 1 && m.last == 0 { m.removeLast() }
        let n = m.count
        // -m⁻¹ mod 2³²
        var x: UInt32 = 1
        for _ in 0..<5 { x = x &* (2 &- m[0] &* x) }
        let inv = 0 &- x
        // R² mod m by doubling 1, 2·32·n times
        var r = [UInt32](repeating: 0, count: n + 1); r[0] = 1
        for _ in 0..<(64 * n) {
            var carry: UInt32 = 0
            for i in 0..<(n + 1) { let v = r[i]; r[i] = (v << 1) | carry; carry = v >> 31 }
            if geq(r, m) { sub(&r, m) }
        }
        let r2 = Array(r.prefix(n))
        // base mod m (base is smaller than m in every real use; reduce by subtraction to be safe)
        var b = base.l + [UInt32](repeating: 0, count: max(0, n + 1 - base.l.count))
        if b.count > n + 1 { b = Array(b.prefix(n + 1)) }
        var guardCount = 0
        while geq(b, m) && guardCount < 64 { sub(&b, m); guardCount += 1 }
        let bm = mont(Array(b.prefix(n)), r2, m, inv)
        var one = [UInt32](repeating: 0, count: n); one[0] = 1
        var acc = mont(one, r2, m, inv)   // 1 in Montgomery form
        let e = exp.l
        for i in stride(from: e.count * 32 - 1, through: 0, by: -1) {
            acc = mont(acc, acc, m, inv)
            if (e[i / 32] >> UInt32(i % 32)) & 1 == 1 { acc = mont(acc, bm, m, inv) }
        }
        return Big(limbs: mont(acc, one, m, inv))
    }
}
