import Foundation

/// The building, as distinct from whose colours it is wearing tonight.
///
/// The stadium is rebuilt when this changes and repainted when it does not,
/// and the difference is three seconds of blocked main thread against a
/// texture swap. That matters because a red-zone channel leaves one game for
/// another every few seconds: a stadium that rebuilds each time is a slideshow,
/// and on a loaded machine a three-second rebuild inside a scene update is
/// exactly what a watchdog kills.
///
/// Every value here is geometry - something a builder would have poured, cut
/// or bolted down. What is deliberately *not* here is anything a club brings
/// with it: `bowl.crowd`'s four colours, `bowl.sectionTint`, and `field.art`,
/// which is where each club's name is painted on the grass. Those change on
/// every switch and none of them moves a vertex.
///
/// The league is here because it is not a label: a college field's hash marks
/// are far wider than the NFL's, the end zones and goal posts differ, and a
/// Saturday drawn as a Sunday puts every play in the wrong place across the
/// field. Changing league is changing building.
///
/// No RealityKit, so `verify_scene` can sweep it: `test_a_venue_is_the_building`
/// holds three different matchups in one bowl to the same venue, which is the
/// property the whole fast path rests on.
struct StadiumVenue: Equatable {
    // The field as a surveyor would give it.
    let league: String
    let length: Double
    let endZone: Double
    let width: Double
    let hashFromSideline: Double
    let goalPostWidth: Double
    let stripeEvery: Double
    let numbersEvery: Double
    let markings: String?
    let props: SceneSpec.Props?

    // The bowl: what is built, and where the visiting support is put. The
    // away *section* is a fact about the building - the block behind the
    // visiting bench is the same block whoever is visiting - while the colour
    // that fills it is not.
    let seating: SceneSpec.Seating?
    let shape: SceneSpec.Shape
    let tiers: [SceneSpec.Tier]
    let rimLights: SceneSpec.RimLights
    let awaySection: SceneSpec.AwaySection?
    let wall: SceneSpec.Wall?
    let ribbon: SceneSpec.Ribbon?
    let pressBox: SceneSpec.PressBox?
    let tunnels: [SceneSpec.Tunnel]?
    let videoBoard: SceneSpec.VideoBoard?

    /// Where the wearer may sit. Rings are measured from the seat and every
    /// card turns to face it, so a different set of seats is different
    /// geometry even in the same bowl.
    let seats: [SceneSpec.SeatOption]?

    init(_ s: SceneSpec) {
        league = s.league
        length = s.field.length
        endZone = s.field.endZone
        width = s.field.width
        hashFromSideline = s.field.hashFromSideline
        goalPostWidth = s.field.goalPostWidth
        stripeEvery = s.field.stripeEvery
        numbersEvery = s.field.numbersEvery
        markings = s.field.markings
        props = s.field.props
        seating = s.bowl.seating
        shape = s.bowl.shape
        tiers = s.bowl.tiers
        rimLights = s.bowl.rimLights
        awaySection = s.bowl.crowd.awaySection
        wall = s.bowl.wall
        ribbon = s.bowl.ribbon
        pressBox = s.bowl.pressBox
        tunnels = s.bowl.tunnels
        videoBoard = s.bowl.videoBoard
        seats = s.presentation.stadium.seats
    }

    /// What the same building wears tonight. Changing this is paint: new
    /// colours on the crowd, new names on the grass, nothing moved.
    static func livery(_ s: SceneSpec) -> String {
        [s.teams.home.chip, s.teams.away.chip, s.teams.home.abbr, s.teams.away.abbr,
         s.bowl.crowd.home, s.bowl.crowd.away, s.bowl.crowd.neutral, s.bowl.crowd.dark,
         s.field.art.map { "\($0.glyphs)|\($0.endZones)|\($0.midfield)" } ?? ""].joined(separator: "|")
    }
}
