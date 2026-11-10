import SwiftUI
import WhatsNewKit

/// Fantasy Edge's side of the "What's new" sheet. The sheet and the
/// once-per-version rule live in `packages/swift/WhatsNewKit`; the notes live
/// in `FantasyEdge/WhatsNew.json`, filed under `VERSION` in
/// `apple/generate_project.py`.
enum WhatsNew {
    static let notes = ReleaseNotes.bundled()

    /// The ball off the app icon's front layer.
    static let art = Image("WhatsNewBall")

    /// Keys only a used install has written. Builds before 1.0 recorded no
    /// version, so without these their upgrade would read as a first launch.
    /// `fe.host` is written the moment somebody points the app at a board,
    /// which every real install has had to do.
    static let priorStateKeys = ["fe.host", "fe.watch", "live.pinField"]

    /// Every launch flag this app and StadiumKit read is a screenshot, look-dev
    /// or demo switch, and they share these prefixes (`-shot`, `-stadiumStats`,
    /// `-openTabletop`, `-trailHold`, ...). `-fe.host` is configuration and
    /// deliberately not here. `FE_LEAGUE_COUNT` is the debug demo of league
    /// counts; the `*_SKIP` variables are look-dev.
    static let suppression = WhatsNewSuppression(
        argumentPrefixes: ["-shot", "-stadium", "-open", "-replay", "-trail", "-tabletop",
                           "-bowl", "-light", "-sideline", "-crowd", "-arrival", "-shaderGraph"],
        environmentKeys: ["FE_LEAGUE_COUNT", "BOWL_SKIP", "LIGHT_SKIP", "SIDELINE_SKIP"])
}

/// Where a "What's new" card can take you: the `destination` values
/// `WhatsNew.json` may use. A card naming anything else is drawn plain, and
/// `tests/test_whats_new.py` reads these cases to hold the notes to them.
enum WhatsNewDestination: String, CaseIterable {
    /// Live tab, Game mode, with last week's picker open - scores hidden.
    case lastWeek
    /// Live tab, Game mode: the field, the slate and "View in 3D".
    case game
}

/// A callout's destination, waiting for the view that owns it.
///
/// The tab is `CommandView`'s state, the mode `LiveView`'s and the picker
/// `GameFieldView`'s, and the last two do not exist until the tab before them
/// has switched. So each takes its own step and passes the rest on: the
/// command centre goes to Live, Live goes to Game, and the game view opens
/// the picker and clears the route. A board with no league loaded yet keeps
/// it until the rails appear, which is where it was going anyway.
@Observable
final class WhatsNewRoute {
    var pending: WhatsNewDestination?
}

extension View {
    func fantasyEdgeWhatsNew(_ route: WhatsNewRoute) -> some View {
        whatsNew(WhatsNew.notes, art: WhatsNew.art,
                 priorStateKeys: WhatsNew.priorStateKeys, suppression: WhatsNew.suppression,
                 destinations: Set(WhatsNewDestination.allCases.map(\.rawValue)),
                 open: { route.pending = WhatsNewDestination(rawValue: $0) })
    }
}
