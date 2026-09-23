import Foundation

/// The fixed look-dev shots, by name: `-shot crowd-closeup` on the launch
/// arguments opens the app straight into that view. `tools/lookdev.py` shoots
/// the same names and positions the replay for each; a test keeps the two
/// lists identical. See docs/ART_BIBLE.md for which actor each shot judges.
///
/// Debug harness only: the turn and tilt use the debug look arguments.
public enum StadiumShots {
    public struct Shot: Sendable {
        public let tabletop: Bool
        public let seat: String?
        /// Degrees to turn the viewer's head right, and to look up. The world
        /// stays level; see `StadiumSpaceView`.
        public let yaw: Float
        public let pitch: Float
    }

    // SHOTS-BEGIN
    public static let all: [String: Shot] = [
        "tabletop": Shot(tabletop: true, seat: nil, yaw: 0, pitch: 0),
        "bowl-wide": Shot(tabletop: false, seat: "upper", yaw: 0, pitch: -8),
        "field-level": Shot(tabletop: false, seat: "field", yaw: 0, pitch: 4),
        "crowd-closeup": Shot(tabletop: false, seat: "club", yaw: 55, pitch: -10),
        "lights-haze": Shot(tabletop: false, seat: "club", yaw: 10, pitch: 24),
        "sky-dome": Shot(tabletop: false, seat: "club", yaw: 0, pitch: 55),
        "td-moment": Shot(tabletop: false, seat: "club", yaw: 30, pitch: 0),
        "redzone-trails": Shot(tabletop: false, seat: "club", yaw: 22, pitch: -8),
        "sideline-props": Shot(tabletop: false, seat: "endzone", yaw: 0, pitch: -4),
        // The two views nothing else could give: a ball within the life-size
        // band, and the wall's LED boards square on rather than edge on.
        "goal-line": Shot(tabletop: false, seat: "goalLine", yaw: 0, pitch: -2),
        "wall-boards": Shot(tabletop: false, seat: "wall", yaw: 0, pitch: -6),
    ]
    // SHOTS-END

    /// The shot named on the launch arguments, if any.
    public static var current: (name: String, shot: Shot)? {
        let args = ProcessInfo.processInfo.arguments
        guard let i = args.firstIndex(of: "-shot"), i + 1 < args.count, let shot = all[args[i + 1]] else { return nil }
        return (args[i + 1], shot)
    }

    /// A launch argument's value, with a shot's presets filling in whatever
    /// was not given explicitly.
    public static func argument(_ name: String) -> String? {
        let args = ProcessInfo.processInfo.arguments
        if let i = args.firstIndex(of: name), i + 1 < args.count { return args[i + 1] }
        guard let (_, shot) = current else { return nil }
        switch name {
        case "-openTabletop": return "replay"
        case "-stadiumStyle": return shot.tabletop ? nil : "full"
        case "-stadiumSeat": return shot.seat
        case "-stadiumLook": return String(shot.yaw)
        case "-stadiumPitch": return String(shot.pitch)
        default: return nil
        }
    }

    /// Whether the launch should walk into the stadium.
    public static var opensStadium: Bool {
        ProcessInfo.processInfo.arguments.contains("-openStadium") || (current.map { !$0.shot.tabletop } ?? false)
    }
}
