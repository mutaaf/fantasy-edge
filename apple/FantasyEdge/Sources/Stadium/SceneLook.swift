import Foundation

// The scene's `look`: every visual-only number the renderer reads, decoded
// from `design/tokens.json` as the API embeds it, one section per actor.
//
// This file is the renderer's whole vocabulary of appearance. A size, an
// opacity, a light's lumens or a crowd's density that is not a field here is
// not allowed in `Stadium/`, and `tests/test_replay_scene.py` holds that line:
// it reads every `let` between the markers below and fails if tokens.json does
// not carry the same key, so a web or Android renderer can always reach the
// value the headset used.
//
// This file holds only the top-level `Look`, which the director owns. Each
// actor's structs live in Actors/<Actor>/<Actor>Look.swift, owned by that
// actor's specialist with their own block of tokens.json.

// LOOK-BEGIN


extension SceneSpec {
    /// A value that differs between the stadium and the tabletop.
    public struct PerMode<T: Decodable & Equatable & Sendable>: Decodable, Equatable, Sendable {
        public let stadium: T
        public let tabletop: T
        public func value(tabletop isTabletop: Bool) -> T { isTabletop ? tabletop : stadium }
    }

    public struct Look: Decodable, Equatable, Sendable {
        public let experience: ExperienceLook
        public let field: FieldLook
        public let sideline: SidelineLook
        public let bowl: BowlLook
        public let crowd: CrowdLook
        public let lighting: LightingLook
        public let sky: SkyLook
        public let broadcast: BroadcastLook
        public let moments: MomentsLook
        public let audio: AudioLook
    }
}

// LOOK-END

extension SceneSpec.Look {
    /// Every section's asset map, keyed by actor, for the loader.
    public var assetSections: [(String, [String: String])] {
        [("experience", experience.assets), ("field", field.assets), ("sideline", sideline.assets),
         ("bowl", bowl.assets), ("crowd", crowd.assets), ("lighting", lighting.assets),
         ("sky", sky.assets), ("broadcast", broadcast.assets), ("audio", audio.assets)]
    }

    /// Every section's model map (`.usdz` for Apple, a `.glb` sibling for the
    /// web and Android), keyed by actor.
    public var modelSections: [(String, [String: String])] {
        [("experience", experience.models), ("field", field.models), ("sideline", sideline.models),
         ("bowl", bowl.models), ("crowd", crowd.models), ("lighting", lighting.models),
         ("sky", sky.models), ("broadcast", broadcast.models), ("audio", audio.models)]
    }

    /// The look the app bundles, for a 1.0 server that sends none. It is the
    /// same tokens.json file, so there is still one source.
    public static func bundled(_ bundle: Bundle = .main) -> SceneSpec.Look? {
        guard let url = bundle.url(forResource: "tokens", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return nil }
        struct Tokens: Decodable { let visual: SceneSpec.Look }
        return try? JSONDecoder().decode(Tokens.self, from: data).visual
    }
}
