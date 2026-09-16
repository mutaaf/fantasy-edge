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
        public let gateWiden: Double
        public let gateHeightYards: Double
        public let gateOpacity: Double
        public let gateWallOpacity: Double?
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

    /// Where a folded panel's tab or pill stands on the dock's rail. `scale`
    /// below 1 means it was brought in front of something near (a chair, the
    /// press box glass) and draws smaller, so it subtends the same angle.
    public struct TabSlot: Decodable, Equatable, Sendable {
        public let yaw: Double
        public let distance: Double
        public let height: Double
        public let scale: Double?

        public var slot: Slot { Slot(yaw: yaw, distance: distance, height: height) }
    }

    /// A panel's places from one seat, worked out by scene.py's seat_panels():
    /// open in the dock's gallery, folded on its rail. `clear` false: there is
    /// nowhere open that keeps off the field, the boards and the lights, so it
    /// starts folded and opens over its tab only when asked.
    public struct PanelSlot: Decodable, Equatable, Sendable {
        public let yaw: Double
        public let distance: Double
        public let height: Double
        public let scale: Double?
        public let folded: Bool
        public let clear: Bool?
        public let tab: TabSlot?

        public var slot: Slot { Slot(yaw: yaw, distance: distance, height: height) }

        /// The place and scale to draw at, open or folded. A scene from before
        /// the dock has no tab, and its one place stands for both.
        public func place(folded: Bool) -> (slot: Slot, scale: Double) {
            if folded, let tab { return (tab.slot, tab.scale ?? 1) }
            return (slot, scale ?? 1)
        }
    }

    public struct SeatPanels: Decodable, Equatable, Sendable {
        public let drive: PanelSlot
        public let trailing: PanelSlot
        public let controls: PanelSlot
        /// The video board carries the score from this seat; the glass scorebug yields.
        public let scorebugHidden: Bool
    }

    /// A panel's footprint contract: exactly this wide, at most this tall.
    public struct PanelSize: Decodable, Equatable, Sendable {
        public let widthPoints: Double
        public let maxHeightPoints: Double
    }

    public struct PanelSizes: Decodable, Equatable, Sendable {
        public let drive: PanelSize
        public let trailing: PanelSize
        public let controls: PanelSize
        public let tab: PanelSize
    }

    public struct Layout: Decodable, Equatable, Sendable {
        public let maxSideDegrees: Double
        public let maxBelowDegrees: Double
        public let slots: Slots
        /// Present on scenes that work panels out per seat; absent, the slots stand.
        public let perSeat: [String: SeatPanels]?
        public let panelSizes: PanelSizes?
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
        public let listWidthPoints: Double?
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
