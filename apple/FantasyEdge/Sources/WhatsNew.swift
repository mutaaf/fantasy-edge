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

extension View {
    func fantasyEdgeWhatsNew() -> some View {
        whatsNew(WhatsNew.notes, art: WhatsNew.art,
                 priorStateKeys: WhatsNew.priorStateKeys, suppression: WhatsNew.suppression)
    }
}
