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
    // v26 (Marko, 5.11.2026: "I want to keep Command Tab for my macOS ... so I can switch between a remote viewer and any
    // other application locally. Please don't send this combination there, and change it to switch applications with Alt
    // Tab"): the Mac's global hotkeys are never suspended any more, so ⌘Tab (and Spotlight, Rectangle, Speechify's keys)
    // stay with macOS while the viewer is in front. ⌥Tab switches the VM's programs (ScreenView.keyDown). The callers
    // stay; capture(true) now only makes sure the Mac's hotkeys are on.
    static func capture(_ on: Bool) {
        _ = CGSSetGlobalHotKeyOperatingMode(CGSMainConnectionID(), 0)   // 0 = the Mac's hotkeys on (1 would suspend them)
        captured = false
    }
}
