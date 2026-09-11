import SwiftUI

/// The Intel tab.
///
/// It absorbed Moves. Waivers and trades were never a peer of intel - they
/// are two of the calls it makes, alongside start/sit, matchup edges, the
/// injury wire and league trends - so two adjacent placeholders were being
/// shown where one subject exists. Merging them under the name of the subject
/// is also the arrangement the built version is heading for, which means this
/// is not a compromise between two empty tabs but the shape they were always
/// going to take.
///
/// Deliberately one line of content. The engine behind this is being built
/// server-side; when it lands, the body below is replaced and nothing in
/// `CommandView` has to be unpicked, because no placeholder state was ever
/// threaded through it.
struct IntelView: View {
    var body: some View {
        ComingSoon(
            title: "Intel",
            what: "Start and sit calls, waiver and trade opportunities, "
                + "matchup edges, the injury wire and league trends - each "
                + "one derived from your own league history rather than from "
                + "somebody else's rankings.",
            needs: [
                "The insight layer itself, which computes every call from "
                + "rows already in SQLite. It is being written now, and it "
                + "runs on the Mac, not here.",
                "A route on the read API to serve those calls, so this tab "
                + "stays credential-free like every other one - the headset "
                + "never holds a league cookie.",
                "Enough seasons pulled to reason over. A waiver call off one "
                + "week of data is a guess with a confident font on it.",
            ],
            icon: "chart.bar.doc.horizontal")
    }
}
