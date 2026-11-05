// RectangleKeys.swift: v24 (Marko, 5.11.2026: "read my shortcut for my application called Rectangle ... don't forward these
// shortcuts to the remote session ... now I cannot manage the windows"). While the viewer is in front the Mac's global
// hotkeys are suspended (HotKeys.swift, so ⌘Tab reaches the VM), and Rectangle never heard its keys. Its shortcuts are
// read from its own settings (com.knollsoft.Rectangle): a combination set there is Rectangle's, an empty entry is switched
// off, an action not written there has Rectangle's default (⌃⌥ …). Such a key is never sent to the VM; App hands it back
// to the Mac (hotkeys on for a moment, the same key pressed again), so Rectangle moves the viewer window.
import AppKit

enum RectangleKeys {
    struct Combo: Hashable { let code: UInt16; let mods: UInt }
    static let ctrl: UInt = 262144, opt: UInt = 524288, cmd: UInt = 1048576, shift: UInt = 131072
    /// Rectangle's own defaults ("alternateDefaultShortcuts"), used for an action its settings do not mention
    static let defaults: [String: Combo] = {
        let co = ctrl | opt
        return ["leftHalf": .init(code: 123, mods: co), "rightHalf": .init(code: 124, mods: co),
                "topHalf": .init(code: 126, mods: co), "bottomHalf": .init(code: 125, mods: co),
                "topLeft": .init(code: 32, mods: co), "topRight": .init(code: 34, mods: co),
                "bottomLeft": .init(code: 38, mods: co), "bottomRight": .init(code: 40, mods: co),
                "firstThird": .init(code: 2, mods: co), "centerThird": .init(code: 3, mods: co),
                "lastThird": .init(code: 5, mods: co), "firstTwoThirds": .init(code: 14, mods: co),
                "lastTwoThirds": .init(code: 17, mods: co), "maximize": .init(code: 36, mods: co),
                "maximizeHeight": .init(code: 126, mods: co | shift), "smaller": .init(code: 27, mods: co),
                "larger": .init(code: 24, mods: co), "center": .init(code: 8, mods: co), "restore": .init(code: 51, mods: co),
                "nextDisplay": .init(code: 124, mods: co | cmd), "previousDisplay": .init(code: 123, mods: co | cmd)]
    }()
    private(set) static var combos: Set<Combo> = []

    /// read again each time the viewer comes to the front (Rectangle's settings may have changed)
    static func load() {
        let d = UserDefaults(suiteName: "com.knollsoft.Rectangle")?.dictionaryRepresentation() ?? [:]
        var out = Set<Combo>()
        for (name, v) in d {
            guard let m = v as? [String: Any] else { continue }
            if let c = (m["keyCode"] as? NSNumber)?.uint16Value, let f = (m["modifierFlags"] as? NSNumber)?.uintValue {
                out.insert(Combo(code: c, mods: f & (ctrl | opt | cmd | shift)))
            } else if defaults[name] != nil { continue }      // an empty entry: switched off in Rectangle
        }
        for (name, c) in defaults where d[name] == nil { out.insert(c) }
        combos = out
    }

    static func matches(_ e: NSEvent) -> Bool {
        let f = UInt(e.modifierFlags.intersection([.control, .option, .command, .shift]).rawValue)
        return f != 0 && combos.contains(Combo(code: e.keyCode, mods: f))
    }
}
