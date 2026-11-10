import XCTest
@testable import WhatsNewKit

final class GateTests: XCTestCase {
    private func decide(_ current: String?, seen: String?, prior: Bool = false,
                        notes: Bool = true, suppressed: Bool = false) -> WhatsNewGate.Decision {
        WhatsNewGate.decide(current: current, seen: seen, priorInstall: prior,
                            hasNotes: notes, suppressed: suppressed)
    }

    func testFirstLaunchShowsNothingAndRecords() {
        XCTAssertEqual(decide("1.0", seen: nil), .init(show: false, record: "1.0"))
    }

    func testUpgradeShowsOnceThenNever() {
        let first = decide("1.1", seen: "1.0")
        XCTAssertEqual(first, .init(show: true, record: "1.1"))
        XCTAssertEqual(decide("1.1", seen: first.record), .init(show: false, record: nil))
    }

    func testSameVersionShowsNothing() {
        XCTAssertEqual(decide("1.0", seen: "1.0", prior: true), .init(show: false, record: nil))
    }

    func testUpgradeFromABuildThatNeverRecordedShows() {
        XCTAssertEqual(decide("1.0", seen: nil, prior: true), .init(show: true, record: "1.0"))
    }

    func testNoNotesRecordsWithoutShowing() {
        XCTAssertEqual(decide("1.2", seen: "1.1", notes: false), .init(show: false, record: "1.2"))
    }

    func testSuppressedLaunchNeitherShowsNorRecords() {
        XCTAssertEqual(decide("1.1", seen: "1.0", suppressed: true), .init(show: false, record: nil))
        XCTAssertEqual(decide("1.1", seen: nil, suppressed: true), .init(show: false, record: nil))
    }

    func testForcedShowsWithoutRecordingWhateverTheStoreSays() {
        let forced = { (seen: String?, suppressed: Bool) in
            WhatsNewGate.decide(current: "1.0", seen: seen, priorInstall: false,
                                hasNotes: true, suppressed: suppressed, forced: true)
        }
        XCTAssertEqual(forced(nil, false), .init(show: true, record: nil))     // fresh install
        XCTAssertEqual(forced("1.0", false), .init(show: true, record: nil))   // already seen
        XCTAssertEqual(forced("0.9", true), .init(show: true, record: nil))    // under a capture flag
        XCTAssertEqual(WhatsNewGate.decide(current: "1.0", seen: nil, priorInstall: false, hasNotes: false,
                                           suppressed: false, forced: true), .init(show: false, record: nil))
    }

    func testMissingVersionDoesNothing() {
        XCTAssertEqual(decide(nil, seen: "1.0"), .init(show: false, record: nil))
        XCTAssertEqual(decide("", seen: nil), .init(show: false, record: nil))
    }
}

final class SuppressionTests: XCTestCase {
    let app = WhatsNewSuppression(argumentPrefixes: ["-shot", "-stadium", "-open"],
                                  environmentKeys: ["FE_LEAGUE_COUNT"])

    func testOrdinaryLaunchIsNotSuppressed() {
        XCTAssertFalse(app.isSuppressed(arguments: ["/path/App"], environment: [:]))
        // A defaults value on the launch line is configuration, not a capture.
        XCTAssertFalse(app.isSuppressed(arguments: ["/path/App", "-fe.host", "127.0.0.1:8770"], environment: [:]))
    }

    func testCaptureAndDemoFlagsSuppress() {
        XCTAssertTrue(app.isSuppressed(arguments: ["/a", "-shot", "tabletop"], environment: [:]))
        XCTAssertTrue(app.isSuppressed(arguments: ["/a", "-stadiumStats"], environment: [:]))
        XCTAssertTrue(app.isSuppressed(arguments: ["/a", "-openLastWeek"], environment: [:]))
        XCTAssertTrue(app.isSuppressed(arguments: ["/a"], environment: ["FE_LEAGUE_COUNT": "10"]))
    }

    func testTestsAndTheOffSwitchAlwaysSuppress() {
        let bare = WhatsNewSuppression()
        XCTAssertTrue(bare.isSuppressed(arguments: ["/a"], environment: ["XCTestConfigurationFilePath": "x"]))
        XCTAssertTrue(bare.isSuppressed(arguments: ["/a", "-whatsNewOff"], environment: [:]))
        XCTAssertTrue(bare.isSuppressed(arguments: ["/a"], environment: ["WHATS_NEW_OFF": "1"]))
    }

    func testTheExecutablePathIsNeverAFlag() {
        XCTAssertFalse(app.isSuppressed(arguments: ["-shot"], environment: [:]))
    }
}

final class ForceTests: XCTestCase {
    func testPreviewAndTapAreReadInADebugBuild() {
        let f = WhatsNewForce(arguments: ["/a", "-whatsNewPreview", "-whatsNewTap", "lastWeek"], isDebug: true)
        XCTAssertTrue(f.preview)
        XCTAssertEqual(f.tap, "lastWeek")
    }

    func testAReleaseBuildIgnoresBoth() {
        let f = WhatsNewForce(arguments: ["/a", "-whatsNewPreview", "-whatsNewTap", "lastWeek"], isDebug: false)
        XCTAssertFalse(f.preview)
        XCTAssertNil(f.tap)
    }

    func testAnOrdinaryLaunchIsNotForced() {
        let f = WhatsNewForce(arguments: ["/a", "-fe.host", "127.0.0.1:8770"], isDebug: true)
        XCTAssertFalse(f.preview)
        XCTAssertNil(f.tap)
        // A dangling tap with no destination is no tap.
        XCTAssertNil(WhatsNewForce(arguments: ["/a", "-whatsNewTap"], isDebug: true).tap)
        // The executable path is never a flag.
        XCTAssertFalse(WhatsNewForce(arguments: ["-whatsNewPreview"], isDebug: true).preview)
    }

    func testTheForceFlagsAreNotSuppressionFlags() {
        // -whatsNewPreview must not hide the sheet it asks for.
        let app = WhatsNewSuppression(argumentPrefixes: ["-shot", "-stadium", "-open"])
        XCTAssertFalse(app.isSuppressed(arguments: ["/a", "-whatsNewPreview", "-whatsNewTap", "game"],
                                        environment: [:]))
    }
}

final class DestinationTests: XCTestCase {
    private func card(_ destination: String?) -> Release.Card {
        .init(icon: "eye.slash", title: "T", line: "L", tint: "blue", destination: destination)
    }

    func testAKnownDestinationIsACallout() {
        XCTAssertEqual(card("lastWeek").callout(known: ["lastWeek", "game"]), "lastWeek")
    }

    func testNoDestinationIsAPlainCard() {
        XCTAssertNil(card(nil).callout(known: ["lastWeek"]))
        XCTAssertNil(card("").callout(known: ["lastWeek", ""]))
    }

    func testAnUnknownDestinationStaysPlainRatherThanGoingNowhere() {
        XCTAssertNil(card("trades").callout(known: ["lastWeek", "game"]))
    }

    func testDestinationIsOptionalInTheJSON() throws {
        let json = """
        {"releases":[{"version":"1.0","kicker":"k","headline":"h","subhead":"s","notes":["n"],"store":"x",
          "cards":[{"icon":"a","title":"A","line":"l","tint":"green"},
                   {"icon":"b","title":"B","line":"l","tint":"blue","destination":"lastWeek"}]}]}
        """
        let notes = try JSONDecoder().decode(ReleaseNotes.self, from: Data(json.utf8))
        XCTAssertEqual(notes.releases[0].cards.map(\.destination), [nil, "lastWeek"])
    }
}

final class StoreTests: XCTestCase {
    func testPriorStateReadsThePersistentDomainOnly() {
        let domain = "whatsnewkit.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: domain)!
        defer { defaults.removePersistentDomain(forName: domain) }
        XCTAssertFalse(WhatsNewStore.hasPriorState(["fe.host"], defaults: defaults, domain: domain))
        defaults.setPersistentDomain(["fe.host": "10.0.0.2:8770"], forName: domain)
        XCTAssertTrue(WhatsNewStore.hasPriorState(["fe.host"], defaults: defaults, domain: domain))
        XCTAssertFalse(WhatsNewStore.hasPriorState(["fe.watch"], defaults: defaults, domain: domain))
    }
}

/// The app's real notes, read from the repo rather than a copy.
final class FantasyEdgeNotesTests: XCTestCase {
    private var repo: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    }

    /// `MARKETING_VERSION` lives in the project generator; read it from there.
    private func marketingVersion() throws -> String {
        let src = try String(contentsOf: repo.appendingPathComponent("apple/generate_project.py"), encoding: .utf8)
        let m = try XCTUnwrap(src.firstMatch(of: #/\nVERSION = "([^"]+)"/#))
        return String(m.1)
    }

    func testCurrentVersionHasNotesThatDecode() throws {
        let notes = try ReleaseNotes.load(from: repo.appendingPathComponent("apple/FantasyEdge/WhatsNew.json"))
        let release = try XCTUnwrap(notes.release(for: try marketingVersion()),
                                    "no WhatsNew.json entry for the version the app builds as")
        XCTAssertTrue((2...4).contains(release.cards.count))
        XCTAssertFalse(release.notes.isEmpty)
        XCTAssertFalse(release.store.isEmpty)
    }
}
