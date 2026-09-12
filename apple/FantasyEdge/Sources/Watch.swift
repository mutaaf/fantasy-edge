import AVFoundation
import Foundation
import Observation

/// Playing whatever the wearer pointed the board at, and saying why when it
/// will not play.
///
/// This exists because a stream that failed was indistinguishable from a
/// stream that had not been set. `startWatching()` used to be four lines: a
/// `guard` on the URL, `replaceCurrentItem`, `play()`. Nothing observed
/// `AVPlayerItem.status`, so a 404, a timeout, a codec the simulator cannot
/// decode, a typo and a cleartext URL the system had already refused all
/// produced the identical symptom - a black rectangle in the middle of the
/// room, forever. The habit everywhere else in this app is that a failure
/// states itself rather than looking like emptiness; this is that habit
/// applied to video.
@Observable
final class GameFeed {

    enum State: Equatable {
        case idle
        /// The item is loading. Not "playing" yet - saying so before the first
        /// frame is how a stalled stream reads as a working one.
        case opening
        case playing
        /// Something went wrong and this is what it was, in a sentence.
        case failed(String)
    }

    private(set) var state: State = .idle
    let player = AVPlayer()

    @ObservationIgnored private var statusToken: NSKeyValueObservation?
    @ObservationIgnored private var endToken: NSObjectProtocol?

    /// What is wrong with this URL before AVFoundation is even involved.
    ///
    /// Pure and synchronous so the settings field can show the same sentence
    /// the room would, at the moment the wearer types it rather than after
    /// they have put a headset on and pressed play.
    ///
    /// **On cleartext.** A plain `http://` stream is refused by App Transport
    /// Security before `AVPlayer` sees it, and the failure surfaces as an
    /// opaque `-1022`. There are two ways out: add `NSAppTransportSecurity`
    /// exceptions to the generated Info.plist, or say so. This app says so. A
    /// blanket arbitrary-loads exemption weakens every request the app makes,
    /// including the ones to the read API on the wearer's own network, in
    /// order to rescue one optional convenience feature - and the honest
    /// sentence costs nothing and tells the wearer something they can act on.
    static func fault(in raw: String) -> String? {
        let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.isEmpty { return nil }
        guard let u = URL(string: s), let scheme = u.scheme?.lowercased() else {
            return "That is not a URL AVPlayer can open."
        }
        switch scheme {
        case "https", "file":
            if scheme == "https" && (u.host ?? "").isEmpty {
                return "No host in that address - it needs to look like "
                    + "https://example.com/stream.m3u8."
            }
            return nil
        case "http":
            return "Plain http is blocked by the system before playback starts. "
                + "Use the https address for the same stream, or a local file "
                + "URL."
        default:
            return "\(scheme):// is not something AVPlayer will open here. "
                + "Use https or a local file."
        }
    }

    /// A one-line verdict for the settings field, including the empty case.
    static func verdict(_ raw: String) -> String {
        let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.isEmpty { return "Nothing set - the screen in the room will say so." }
        if let f = fault(in: s) { return f }
        return "Looks openable. Whether it actually plays is only known when it "
            + "runs, and the room will name the error if it does not."
    }

    /// Start, and wire up the two things that can tell us it went wrong.
    func start(_ raw: String) {
        stop()
        let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !s.isEmpty else {
            state = .failed("No video source set. Add a stream or file URL in "
                            + "the window's settings.")
            return
        }
        if let fault = GameFeed.fault(in: s) { state = .failed(fault); return }
        guard let url = URL(string: s) else {
            state = .failed("That is not a URL AVPlayer can open."); return
        }

        let item = AVPlayerItem(url: url)
        state = .opening
        // KVO rather than `item.error` after the fact: the failure arrives
        // asynchronously, often seconds later, and reading the property once
        // at `play()` time always finds nil.
        statusToken = item.observe(\.status, options: [.new]) { [weak self] it, _ in
            Task { @MainActor in
                switch it.status {
                case .readyToPlay: self?.state = .playing
                case .failed:
                    self?.state = .failed(GameFeed.describe(it.error, url: url))
                default: break
                }
            }
        }
        // An item can reach `readyToPlay` and then die mid-stream - a segment
        // that 404s partway through an m3u8 does exactly this, and without
        // this notification the room would sit on a frozen frame claiming to
        // be playing.
        endToken = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemFailedToPlayToEndTime, object: item,
            queue: .main) { [weak self] note in
                let e = note.userInfo?[AVPlayerItemFailedToPlayToEndTimeErrorKey] as? Error
                Task { @MainActor in
                    self?.state = .failed(GameFeed.describe(e, url: url))
                }
            }
        player.replaceCurrentItem(with: item)
        player.play()
    }

    func stop() {
        player.pause()
        player.replaceCurrentItem(with: nil)
        statusToken?.invalidate()
        statusToken = nil
        if let t = endToken { NotificationCenter.default.removeObserver(t) }
        endToken = nil
        state = .idle
    }

    /// AVFoundation's own words, plus the one piece of context it never gives:
    /// which address failed. "The operation could not be completed" on its own
    /// is what made this bug take an afternoon to find.
    private static func describe(_ error: Error?, url: URL) -> String {
        let host = url.host ?? url.lastPathComponent
        guard let e = error as NSError? else {
            return "Playback failed and AVFoundation reported no reason. "
                + "Check that \(host) is reachable from the headset."
        }
        var line = e.localizedDescription
        if let why = e.localizedFailureReason, !why.isEmpty { line += " " + why }
        if e.code == NSURLErrorAppTransportSecurityRequiresSecureConnection
            || e.code == -1022 {
            line = "The system refused the connection as insecure. Use the "
                + "https address for this stream."
        }
        return "\(line) (\(host), code \(e.code))"
    }

    deinit {
        statusToken?.invalidate()
        if let t = endToken { NotificationCenter.default.removeObserver(t) }
    }
}
