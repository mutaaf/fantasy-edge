import Foundation
import SwiftUI
import UIKit
import UsageKit

/// The thin sender around `UsageKit.Insights` (1.0.1; Box Office rule 6).
///
/// Events are kept at launch and when a space opens - never from a render or
/// RealityKit update - and go in one batch right then and on the way to the
/// background, over an ephemeral session with no cookies, to Box Office's
/// relay on mutaafaziz.com. That relay is the one host this sends to; the board
/// the app reads stays on the wearer's own Mac and is never told about this.
/// A failed send keeps its events for next time. The switch in "Where is the
/// board?" turns it off: nothing kept or sent, and the queue and id deleted.
@MainActor
final class Usage {
    static let shared = Usage()
    static let KEY = "fe.insights.v1"
    static let VISITS = "fe.visits.v1"

    private let defaults = UserDefaults.standard
    private var queue: Insights.Queue
    private var sending = false
    private var backgroundAt: Date?

    /// Our own runs never count as people: a Debug build (captures, look-dev,
    /// Xcode runs) sends nothing unless launched with `-insights`, and
    /// `-insights-dry` prints each batch instead. Release builds under XCTest
    /// send nothing either.
    private let allowed: Bool
    private let dry: Bool

    init() {
        queue = Insights.Queue.decode(defaults.data(forKey: Usage.KEY))
        #if DEBUG
        let args = ProcessInfo.processInfo.arguments
        dry = args.contains("-insights-dry")
        allowed = args.contains("-insights") || dry
        #else
        allowed = ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] == nil
        dry = false
        #endif
    }

    var enabled: Bool { Insights.isOn(stored: defaults.object(forKey: Insights.switchKey)) }
    var on: Bool { allowed && enabled }

    /// Name an event; one outside the vocabulary is dropped.
    func track(_ name: String, _ props: [String: Insights.Value] = [:]) {
        guard queue.add(name, props, at: Date().timeIntervalSince1970 * 1000, on: on) else { return }
        save()
        flush()
    }

    /// One of the four places opened (`Insights.SPACES`).
    func opened(_ space: String) { track("space_open", ["space": .text(space)]) }

    /// A session: at launch, and on coming back after half an hour away.
    func sessionStart() {
        guard on else { return }
        var v = Insights.Visits.decode(defaults.data(forKey: Usage.VISITS))
        let props = v.start(at: Date().timeIntervalSince1970 * 1000)
        if let d = v.encoded() { defaults.set(d, forKey: Usage.VISITS) }
        track("session_start", props)
    }

    func phase(_ old: ScenePhase, _ new: ScenePhase) {
        if new == .background {
            backgroundAt = Date()
            let id = UIApplication.shared.beginBackgroundTask(withName: "usage") {}
            flush { UIApplication.shared.endBackgroundTask(id) }
        } else if new == .active, old == .background {
            if let t = backgroundAt, Date().timeIntervalSince(t) > 30 * 60 { sessionStart() }
            backgroundAt = nil
        }
    }

    /// The switch. Off deletes the queue and the install id.
    func setOn(_ v: Bool) {
        defaults.set(v, forKey: Insights.switchKey)
        if !v { queue.clear(); save() }
    }

    /// One batch, off the main thread; one at a time; nothing when off.
    func flush(done: (() -> Void)? = nil) {
        let batch = queue.next(on: on)
        guard !sending, !batch.isEmpty, let id = queue.installId,
              let body = Insights.body(batch, installId: id, release: Usage.release) else { done?(); return }
        if dry {
            for e in batch { print("INSIGHTS \(e.name) \(e.props.sorted { $0.key < $1.key })") }
            queue.sent(batch); save(); done?(); return
        }
        sending = true
        Task.detached(priority: .utility) {
            let ok = await Usage.post(body)
            await MainActor.run {
                self.sending = false
                if ok { self.queue.sent(batch); self.save() }
                done?()
            }
        }
    }

    /// No cookies, no cache, no shared state: one plain POST.
    nonisolated private static let session: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.httpShouldSetCookies = false
        c.httpCookieAcceptPolicy = .never
        c.requestCachePolicy = .reloadIgnoringLocalCacheData
        c.timeoutIntervalForRequest = 10
        c.timeoutIntervalForResource = 15
        return URLSession(configuration: c)
    }()

    nonisolated private static func post(_ body: Data) async -> Bool {
        guard let url = URL(string: Insights.endpoint) else { return false }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.httpBody = body
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // The relay admits an event by its Referer: this app's own page in Cast List.
        req.setValue(Insights.referer, forHTTPHeaderField: "Referer")
        guard let (_, r) = try? await session.data(for: req), let http = r as? HTTPURLResponse else { return false }
        return (200..<300).contains(http.statusCode)
    }

    private func save() { if let d = queue.encoded() { defaults.set(d, forKey: Usage.KEY) } }

    static let release = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
}
