// HotKeys.swift: while the viewer is the active app, the Mac's global hotkeys (⌘Tab, Rectangle's ⌃⌥ keys,
// Spotlight ...) are suspended so these keys reach the VM. Private but long-standing WindowServer call (used by
// remote-desktop and game-streaming apps); the mode belongs to this app's connection, so the WindowServer restores
// it by itself if the app quits or crashes.
import Foundation

private typealias CGSConnectionID = Int32
@_silgen_name("CGSMainConnectionID") private func CGSMainConnectionID() -> CGSConnectionID
@_silgen_name("CGSSetGlobalHotKeyOperatingMode")
private func CGSSetGlobalHotKeyOperatingMode(_ cid: CGSConnectionID, _ mode: Int32) -> Int32

enum HotKeys {
    static private(set) var captured = false
    static func capture(_ on: Bool) {
        _ = CGSSetGlobalHotKeyOperatingMode(CGSMainConnectionID(), on ? 1 : 0)   // 1 = disable, 0 = enable
        captured = on
    }
}
