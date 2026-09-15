import Foundation
import RealityKit
import simd

// The stadium is ten actors, each owning one part of what you see and hear.
//
//   Field       turf, paint, hashes, numbers, end zones
//   Sideline    goal posts, pylons, benches, chains, LED boards
//   Bowl        tiers, seats, aisles, rails, concourse, fascia, press box, tunnels
//   Crowd       fans
//   Lighting    image-based light, rim banks, glows, haze, floodlights, strobe
//   Sky         sky dome, stars, the light dome over the rim
//   Broadcast   ball, trails, lasers, ribbon board, win-probability horizon
//   Moments     fireworks, and the choreography of strobes and surges
//   Audio       crowd bed, reactions, PA
//   Experience  seat placement, the seat fade, the tabletop baseplate
//
// An actor builds from the scene and its own `visual.<actor>` section, updates
// every frame, and hears moments. Actors never call each other: what one needs
// from another - where the banks stand, when to strobe - passes through
// `StadiumShared`, which the composer owns. That is what lets one specialist
// rework the crowd while another reworks the bowl without touching a line of
// each other's code.
//
// Only the director edits this file, the composer (`StadiumRenderer`) and
// `SceneSpec.swift`. See docs/ART_BIBLE.md.

/// Tabletop or stadium. An actor scales its detail to it.
public enum StadiumLOD: Sendable {
    case tabletop, stadium
    var isTabletop: Bool { self == .tabletop }
}

/// What every actor is given: the scene, the look, the assets, the tiers the
/// mode draws, and the shared blackboard.
@MainActor
final class StadiumContext {
    let lod: StadiumLOD
    let assets: StadiumAssets
    let shared = StadiumShared()
    /// The composer's root. Experience places it; Lighting hangs light on it.
    let stage: Entity
    /// Everything actors add lives under here, so a seat fade can fade it.
    let world: Entity
    private(set) var spec: SceneSpec
    private(set) var look: SceneSpec.Look
    private(set) var reduceMotion: Bool

    init(lod: StadiumLOD, spec: SceneSpec, look: SceneSpec.Look, assets: StadiumAssets,
         stage: Entity, world: Entity, reduceMotion: Bool) {
        self.lod = lod
        self.spec = spec
        self.look = look
        self.assets = assets
        self.stage = stage
        self.world = world
        self.reduceMotion = reduceMotion
    }

    func update(spec: SceneSpec, look: SceneSpec.Look, reduceMotion: Bool) {
        self.spec = spec
        self.look = look
        self.reduceMotion = reduceMotion
    }

    var tabletop: Bool { lod.isTabletop }

    /// The bowl tiers this mode draws.
    var tiers: [SceneSpec.Tier] {
        let names = tabletop ? spec.presentation.tabletop.bowlTiers : spec.presentation.stadium.bowlTiers
        return spec.bowl.tiers.filter { names.contains($0.name) }
    }

    /// Whether a stretch of the bowl between two angles is left out on the
    /// table - the architect's cutaway that lets the wearer look into the
    /// bowl (`visual.experience.tabletop.cutaway`). Always false in the stadium.
    func cut(_ t0: Double, _ t1: Double) -> Bool {
        guard tabletop else { return false }
        let c = look.experience.tabletop.cutaway
        let mid = (t0 + t1) / 2
        // Home is +z, which the superellipse reaches for angles in (0, pi).
        let f = (c.side == "home" ? mid : mid - .pi) / .pi
        return f > c.from && f < c.to
    }
}

/// The blackboard actors share through the composer.
@MainActor
final class StadiumShared {
    /// Seconds since the stadium was built, on the frame clock.
    var time: Double = 0
    /// Rim light banks, local yards. Published by Lighting.
    var banks: [SIMD3<Float>] = []
    /// Points in the lower bowl behind each end, for sound. Published by Bowl.
    var standsBehind: (home: SIMD3<Float>, away: SIMD3<Float>) = (.zero, .zero)
    /// The press box, for the PA. Published by Bowl.
    var pressBox: SIMD3<Float> = .zero
    /// The wearer's eyes in local yards; nil on the table. Published by Experience.
    var seat: SIMD3<Float>?
    /// Strobe the banks until this time. Written by Moments, read by Lighting.
    var strobeUntil: Double = 0
    /// Which side's section surges, and until when. Written by Moments, read by Crowd.
    var surge: (away: Bool, until: Double)?
    /// The field-goal net behind the end nearest `endX` sways, `strength` 0..1,
    /// until `until`. Written by Moments on a kick through, read by Sideline.
    var netSway: (endX: Double, strength: Double, until: Double)?
    /// What the crowd has been asked to do, and until when. Written through
    /// `stand`, `sit` and `groan` (Actors/Crowd/CrowdCues.swift), read by Crowd.
    /// It lives on the blackboard so a new stadium starts with none.
    var crowdCues: [CrowdCue] = []
    /// Sound is off. Written by the composer, read by Audio.
    var muted = false
}

/// One frame of the frame clock.
struct StadiumFrame {
    let dt: TimeInterval
    let time: Double
}

/// Something the game did, delivered once to every actor.
enum StadiumEvent {
    /// A scoring play, a turnover: the scene's newest moment.
    case moment(SceneSpec.Moment)
    /// The offense just crossed the twenty.
    case redZoneEntered
    /// A game beat that is not a score: the scene's active cue, once per id.
    case cue(SceneSpec.Cue)
}

/// A part of the stadium. See the list at the top of this file.
@MainActor
protocol StadiumActor: AnyObject {
    /// `field`, `crowd`... - matches its folder, its `visual` section and its assets.
    var name: String { get }
    /// Everything the actor draws hangs off this.
    var root: Entity { get }
    /// Build for a matchup. Called again when the clubs change; clear and rebuild.
    func build(_ c: StadiumContext)
    /// A new scene arrived: numbers moved, a play landed, a tint changed.
    func apply(_ c: StadiumContext, previous: SceneSpec?)
    /// Every rendered frame.
    func update(_ frame: StadiumFrame, _ c: StadiumContext)
    /// Something happened in the game.
    func moment(_ event: StadiumEvent, _ c: StadiumContext)
}

extension StadiumActor {
    func apply(_ c: StadiumContext, previous: SceneSpec?) {}
    func update(_ frame: StadiumFrame, _ c: StadiumContext) {}
    func moment(_ event: StadiumEvent, _ c: StadiumContext) {}

    /// Remove everything this actor drew, before a rebuild.
    func clear() { root.children.removeAll() }
}
