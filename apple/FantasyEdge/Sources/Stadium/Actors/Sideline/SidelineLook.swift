import Foundation

// visual.sideline: Sideline's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Sideline specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
    public struct Boards: Decodable, Equatable, Sendable {
        public let brightness: Double
        /// How long one repeat of the ribbon's content is. The wall tiles it,
        /// the way a real ribbon repeats rather than stretching one message
        /// around the bowl.
        public let panelYards: Double
        /// Texture height. With square texels the width follows from
        /// `panelYards` over the wall's height, so this alone sets the
        /// resolution: 128 over a 1.4 yd wall is 91 texels per yard.
        public let heightPixels: Int
        /// How far in front of the wall's face the boards hang. Bowl draws the
        /// wall from the same `bowl.wall` spec, so boards laid exactly on it
        /// are the surface that loses - which is why they had never been seen.
        public let proudYards: Double
    }

    public struct PropMaterial: Decodable, Equatable, Sendable {
        public let color: String
        public let roughness: Double
        public let metallic: Double
        /// "team": the club whose side the prop stands on wears it.
        public let tint: String?
        /// An asset id whose grey channel cuts the surface out (nets).
        public let mask: String?
        /// Draw with another palette entry instead, sharing its bin.
        public let alias: String?
        /// Scales the mask, for surfaces that are mostly air.
        public let opacity: Double?
    }

    public struct SidelineLodSuffix: Decodable, Equatable, Sendable {
        public let stadium: String
        public let tabletop: String
        /// Per model, the suffix the stadium uses instead of `stadium`. The
        /// team-area dressing is never approached: a cooler on the far
        /// sideline is 40+ yd from every seat, and its LOD1 - which was
        /// exported all along and used by nothing - costs 45% of its full
        /// mesh. Which props a viewer gets close to is a judgement about this
        /// stadium, so it is stated here rather than decided in the renderer.
        public let stadiumByModel: [String: String]?
    }

    public struct SidelineBenches: Decodable, Equatable, Sendable {
        public let count: Int
        public let spacing: Double
        public let centreGap: Double
    }

    public struct PropPlacement: Decodable, Equatable, Sendable {
        public let model: String
        /// Yards along the line from the team area's centre (sideline) or
        /// across the field from its centre (end line).
        public let along: Double
        /// Yards beyond the sideline or end line.
        public let offset: Double
    }

    public struct SidelineChains: Decodable, Equatable, Sendable {
        public let set: String
        public let box: String
        public let ground: String
        public let offset: Double
        public let boxOffset: Double
    }

    public struct SidelineShadow: Decodable, Equatable, Sendable {
        public let footprintScale: Double
        public let footprintBelowMetres: Double
        public let minYards: Double
        public let maxYards: Double
        /// visual.lighting.response.bowlContactAO, so props and seats share one occlusion.
        public let strength: Double
        public let lift: Double
    }

    public struct NetSway: Decodable, Equatable, Sendable {
        public let model: String
        public let pivotHeightMetres: Double
        public let maxDegrees: Double
        public let frequency: Double
        public let decaySeconds: Double
        /// How much of the swing is in the net's own plane (sideways), the part
        /// a viewer behind the goal sees.
        public let lateralShare: Double
    }

    public struct NetLook: Decodable, Equatable, Sendable {
        /// Opacity a net keeps seen face-on.
        public let minOpacity: Double
        /// Opacity seen edge-on.
        public let grazingOpacity: Double
    }

    public struct SidelineLook: Decodable, Equatable, Sendable {
        public let assets: [String: String]
        public let models: [String: String]
        public let boards: Boards
        public let palette: [String: PropMaterial]
        public let lodSuffix: SidelineLodSuffix
        public let metresPerYard: Double
        public let benches: SidelineBenches
        public let dressing: [PropPlacement]
        public let endLine: [PropPlacement]
        public let chains: SidelineChains
        public let shadow: SidelineShadow
        public let sway: NetSway
        /// shaderGraph.materials id the nets use when it loads.
        public let netMaterial: String
        public let net: NetLook
    }
}

// LOOK-END
