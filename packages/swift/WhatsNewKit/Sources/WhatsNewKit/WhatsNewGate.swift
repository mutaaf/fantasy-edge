import Foundation

/// Whether the sheet shows, and what to remember. Pure, so it can be tested
/// without a simulator: the store and the process are read by the caller.
///
/// The rules:
/// - **First launch shows nothing.** Somebody who has just installed the app
///   has nothing to compare against, so "what's new" means nothing to them.
///   Their version is recorded as seen.
/// - **An upgrade shows once.** The version is recorded the moment the sheet
///   is decided on, so a relaunch, a second window or a crash mid-sheet never
///   shows it again.
/// - **No notes, no sheet** - but the version is still recorded, so notes
///   added to a later build are not shown for a version the reader is past.
/// - **Suppressed launches change nothing.** A screenshot, a test or a demo
///   neither shows the sheet nor records a version, so the next ordinary
///   launch behaves as if that run never happened.
/// - **A forced launch shows and records nothing.** `-whatsNewPreview` in a
///   debug build, so the sheet can be looked at on a simulator or a device
///   without spending the real upgrade's one showing.
public enum WhatsNewGate {
    public struct Decision: Equatable, Sendable {
        public var show: Bool
        /// The version to store as seen, or nil to leave the store alone.
        public var record: String?
        public init(show: Bool, record: String?) { self.show = show; self.record = record }
    }

    /// - Parameters:
    ///   - current: this build's `CFBundleShortVersionString`.
    ///   - seen: the last version recorded, if any.
    ///   - priorInstall: whether this install has state from before the gate
    ///     existed. A build from before versions were recorded has no `seen`,
    ///     and without this its upgrade would look like a first launch.
    ///   - hasNotes: whether `current` has an entry in the notes.
    ///   - suppressed: a test, capture or demo launch.
    ///   - forced: the debug preview flag. Wins over everything, because it
    ///     is only ever typed on purpose, and never records.
    public static func decide(current: String?, seen: String?, priorInstall: Bool,
                              hasNotes: Bool, suppressed: Bool, forced: Bool = false) -> Decision {
        if forced { return Decision(show: hasNotes, record: nil) }
        guard !suppressed, let current, !current.isEmpty else {
            return Decision(show: false, record: nil)
        }
        if seen == current { return Decision(show: false, record: nil) }
        let upgraded = seen != nil || priorInstall
        return Decision(show: upgraded && hasNotes, record: current)
    }
}

/// Which launches never see the sheet.
///
/// Each app passes the launch-argument prefixes and environment keys it
/// already uses for screenshots, look-dev and demos, so a new capture flag
/// that follows the app's naming is covered without touching this file.
public struct WhatsNewSuppression: Sendable {
    public var argumentPrefixes: [String]
    public var environmentKeys: [String]

    /// Always suppressed, whatever the app passes: XCTest's own markers and
    /// the kit's explicit off switch.
    public static let alwaysArguments = ["-whatsNewOff"]
    public static let alwaysEnvironment = ["XCTestConfigurationFilePath", "XCTestSessionIdentifier",
                                           "XCTestBundlePath", "WHATS_NEW_OFF"]

    public init(argumentPrefixes: [String] = [], environmentKeys: [String] = []) {
        self.argumentPrefixes = argumentPrefixes
        self.environmentKeys = environmentKeys
    }

    public func isSuppressed(arguments: [String], environment: [String: String]) -> Bool {
        let prefixes = Self.alwaysArguments + argumentPrefixes
        // The first argument is the executable's path, never a flag.
        if arguments.dropFirst().contains(where: { arg in prefixes.contains { arg.hasPrefix($0) } }) {
            return true
        }
        return (Self.alwaysEnvironment + environmentKeys).contains { environment[$0] != nil }
    }
}

/// The debug-only switches, read off the launch line.
///
/// - `-whatsNewPreview` shows the sheet whatever the store says and records
///   nothing (see `WhatsNewGate.decide(forced:)`).
/// - `-whatsNewTap <destination>` presses that card's callout once the sheet
///   is up, through the same action a tap runs - a simulator cannot tap, and
///   "it lands on the feature" is the claim worth seeing.
///
/// Both are compiled out of a release build by the caller (`isDebug`), so a
/// shipped app cannot be talked into either.
public struct WhatsNewForce: Equatable, Sendable {
    public var preview: Bool
    public var tap: String?

    public static let previewArgument = "-whatsNewPreview"
    public static let tapArgument = "-whatsNewTap"

    public init(arguments: [String], isDebug: Bool) {
        guard isDebug else { preview = false; tap = nil; return }
        let args = Array(arguments.dropFirst())
        preview = args.contains(Self.previewArgument)
        if let i = args.firstIndex(of: Self.tapArgument), i + 1 < args.count {
            tap = args[i + 1]
        } else {
            tap = nil
        }
    }
}

/// The one key the gate owns in `UserDefaults`.
public enum WhatsNewStore {
    public static let seenKey = "whatsNew.seenVersion"

    /// Whether this install wrote any of `keys` before the gate existed.
    /// Reads the app's persistent domain only, so a value passed on the launch
    /// line (`-fe.host 127.0.0.1:8770`) does not make a fresh install look old.
    public static func hasPriorState(_ keys: [String], defaults: UserDefaults = .standard,
                                     domain: String? = Bundle.main.bundleIdentifier) -> Bool {
        guard let domain, let stored = defaults.persistentDomain(forName: domain) else { return false }
        return keys.contains { stored[$0] != nil }
    }
}
