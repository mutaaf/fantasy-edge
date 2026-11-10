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
