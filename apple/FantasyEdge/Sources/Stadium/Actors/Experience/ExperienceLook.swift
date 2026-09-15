import Foundation

// visual.experience: Experience's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Experience specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.
// tests/test_experience.py holds the layout inside the comfort limits.

// LOOK-BEGIN

extension SceneSpec.Look {
    public struct Camera: Decodable, Equatable, Sendable {
        public let eyeMeters: Double
        public let seatFadeSeconds: Double
    }

    public struct Baseplate: Decodable, Equatable, Sendable {
        public let marginScale: Double
        public let thicknessMeters: Double
        public let rimOpacity: Double
        public let rimRadiusYards: Double
        public let bevelYards: Double?
        public let edgeOpacity: Double?
        public let groundingShadow: Bool?
    }

    public struct Cutaway: Decodable, Equatable, Sendable {
        public let side: String
        public let from: Double
        public let to: Double
    }

    public struct TabletopLook: Decodable, Equatable, Sendable {
        public let cutaway: Cutaway
        public let minScale: Double?
        public let maxScale: Double?
        public let closerTiltDegrees: Double?
        public let closerSeconds: Double?
    }

    /// Tabletop to seat: the gate of light, the dimmed table, the Crown hint.
    public struct Arrival: Decodable, Equatable, Sendable {
        public let gateSeconds: Double
        public let gateRadiusYards: Double
        public let gateHeightYards: Double
        public let gateOpacity: Double
        public let tabletopDim: Double
        public let crownHintSeconds: Double
        public let crownHintOnce: Bool
        public let swellLeadSeconds: Double
    }

    /// One panel's place: degrees to the right, flat metres out, metres above the eye.
    public struct Slot: Decodable, Equatable, Sendable {
        public let yaw: Double
        public let distance: Double
        public let height: Double
    }

    public struct Slots: Decodable, Equatable, Sendable {
        public let scorebug: Slot
        public let status: Slot
        public let drive: Slot
        public let trailing: Slot
        public let controls: Slot
        public let picker: Slot
        public let hint: Slot
    }

    public struct Layout: Decodable, Equatable, Sendable {
        public let maxSideDegrees: Double
        public let maxBelowDegrees: Double
        public let slots: Slots
        public let restOpacity: Double
        public let hoverOpacity: Double
    }

    public struct Folded: Decodable, Equatable, Sendable {
        public let drive: Bool
        public let trailing: Bool
    }

    public struct Panels: Decodable, Equatable, Sendable {
        public let elsewhereRows: Int
        public let startFolded: Folded
        public let momentOpacity: Double
        public let momentFadeSeconds: Double
        public let momentReturnSeconds: Double
    }

    public struct Catcher: Decodable, Equatable, Sendable {
        public let distance: Double
        public let width: Double
        public let height: Double
    }

    public struct Controls: Decodable, Equatable, Sendable {
        public let autoHideSeconds: Double
        public let targetPoints: Double
        public let revealCatcher: Catcher
    }

    public struct SeatPicker: Decodable, Equatable, Sendable {
        public let widthPoints: Double
        public let heightPoints: Double
        public let dotPoints: Double
        public let insetPoints: Double
    }

    public struct ExperienceLook: Decodable, Equatable, Sendable {
        public let assets: [String: String]
        public let models: [String: String]
        public let camera: Camera
        public let baseplate: Baseplate
        public let tabletop: TabletopLook
        public let arrival: Arrival?
        public let layout: Layout?
        public let panels: Panels?
        public let controls: Controls?
        public let seatPicker: SeatPicker?
    }
}

// LOOK-END
