import XCTest
import Foundation
@testable import UsageKit

/// The label's promises, held: numbers and enums only, off clears everything,
/// and the queue survives a relaunch, caps itself and keeps a failed send.
final class InsightsTests: XCTestCase {
    func testVocabularyIsSmallAndCarriesNoPerson() {
        XCTAssertEqual(Set(Insights.EVENTS.keys), ["session_start", "space_open"])
        for (_, props) in Insights.EVENTS {
            for (k, _) in props {
                XCTAssertFalse(["league", "team", "player", "host", "url", "name", "id", "text"].contains(k), k)
            }
        }
        XCTAssertNil(Insights.clean("page_view", [:]))
        XCTAssertEqual(Insights.clean("space_open", ["space": .text("stadium"), "league": .text("mine")]),
                       ["space": .text("stadium")])
        XCTAssertEqual(Insights.clean("space_open", ["space": .text("192.168.1.20:8770")]), [:])
        XCTAssertEqual(Insights.clean("session_start", ["returning": .num(2), "days_since_last": .num(.nan)]), [:])
    }

    func testOffSendsNothingAndClearsTheQueueAndTheId() {
        var q = Insights.Queue()
        XCTAssertFalse(q.add("session_start", [:], at: 1, on: false))
        XCTAssertNil(q.installId)
        q.add("space_open", ["space": .text("board")], at: 1, on: true)
        let id = q.installId
        XCTAssertNotNil(UUID(uuidString: id ?? ""))
        XCTAssertTrue(q.next(on: false).isEmpty)
        q.clear()
        XCTAssertTrue(q.events.isEmpty); XCTAssertNil(q.installId)
        q.add("session_start", [:], at: 2, on: true)
        XCTAssertNotEqual(q.installId, id, "a new id once it is on again")
        XCTAssertTrue(Insights.isOn(stored: nil), "on by default")
        XCTAssertFalse(Insights.isOn(stored: false))
    }

    func testTheQueueSurvivesARelaunchCapsItselfAndKeepsAFailedSend() {
        var q = Insights.Queue()
        for i in 0..<(Insights.QUEUE_CAP + 20) { q.add("session_start", ["days_since_last": .num(Double(i % 3000))], at: Double(i), on: true) }
        XCTAssertEqual(q.events.count, Insights.QUEUE_CAP)
        XCTAssertEqual(q.events.first?.at, 20, "the oldest go first")
        let back = Insights.Queue.decode(q.encoded())
        XCTAssertEqual(back, q)
        XCTAssertEqual(Insights.Queue.decode(Data("junk".utf8)), Insights.Queue())
        var r = back
        let batch = r.next(on: true)
        XCTAssertEqual(batch.count, Insights.BATCH_MAX)
        XCTAssertEqual(r.next(on: true), batch, "unsent: the same batch next time")
        r.add("space_open", ["space": .text("tabletop")], at: 99_999, on: true)
        r.sent(batch)
        XCTAssertEqual(r.events.count, Insights.QUEUE_CAP - Insights.BATCH_MAX + 1)
        XCTAssertEqual(r.events.last?.name, "space_open")
    }

    func testTheBatchIsPostHogsShapeWithTheAppsProps() throws {
        var q = Insights.Queue()
        q.add("space_open", ["space": .text("stadium")], at: 1_763_000_000_000, on: true)
        let body = try XCTUnwrap(Insights.body(q.events, installId: "abc", release: "1.0.1"))
        let j = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(j["api_key"] as? String, Insights.token)
        let e = try XCTUnwrap((j["batch"] as? [[String: Any]])?.first)
        XCTAssertEqual(e["event"] as? String, "space_open")
        XCTAssertNotNil(e["timestamp"] as? String)
        let p = try XCTUnwrap(e["properties"] as? [String: Any])
        XCTAssertEqual(p["distinct_id"] as? String, "abc")
        XCTAssertEqual(p["app"] as? String, "fantasy-edge")
        XCTAssertEqual(p["platform"] as? String, "visionos")
        XCTAssertEqual(p["surface"] as? String, "app")
        XCTAssertEqual(p["audience"] as? String, "general")
        XCTAssertEqual(p["release"] as? String, "1.0.1")
        XCTAssertEqual(p["$geoip_disable"] as? Bool, true)
        XCTAssertEqual(p["space"] as? String, "stadium")
        XCTAssertTrue(Insights.endpoint.hasPrefix("https://mutaafaziz.com/boxoffice/e/"))
        XCTAssertEqual(Insights.referer, "https://mutaaf.github.io/fantasy-edge/")
    }

    func testTheVisitCounters() {
        var v = Insights.Visits()
        let day: Double = 86_400_000
        XCTAssertEqual(v.start(at: 100 * day), ["returning": .num(0), "days_since_last": .num(0)])
        XCTAssertEqual(v.start(at: 103 * day + 5), ["returning": .num(1), "days_since_last": .num(3)])
        XCTAssertEqual(Insights.Visits.decode(v.encoded()), v)
    }
}
