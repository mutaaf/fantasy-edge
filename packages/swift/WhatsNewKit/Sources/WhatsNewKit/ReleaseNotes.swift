import Foundation

/// One app's release notes: the single source for the in-app sheet and for
/// the store's "What's New" text.
///
/// It is JSON rather than a Swift table so `make test` (Python, no Xcode) can
/// hold the copy to the rules - the current version has an entry, there are two
/// to four cards, and no word on the app's `avoid` list appears - without
/// building anything.
public struct ReleaseNotes: Decodable, Equatable, Sendable {
    public var releases: [Release]

    public func release(for version: String) -> Release? {
        releases.first { $0.version == version }
    }

    public static func load(from url: URL) throws -> ReleaseNotes {
        try JSONDecoder().decode(ReleaseNotes.self, from: Data(contentsOf: url))
    }

    /// The notes bundled into the app, or nil when the file is missing or
    /// does not decode. A broken notes file costs the sheet, never the launch.
    public static func bundled(_ name: String = "WhatsNew", in bundle: Bundle = .main) -> ReleaseNotes? {
        guard let url = bundle.url(forResource: name, withExtension: "json") else { return nil }
        return try? load(from: url)
    }
}

public struct Release: Decodable, Equatable, Sendable, Identifiable {
    public var id: String { version }
    public var version: String
    /// A small line above the headline: the season beat.
    public var kicker: String
    public var headline: String
    public var subhead: String
    public var cards: [Card]
    /// The full notes, one change per line, behind the accordion.
    public var notes: [String]
    /// The plain paragraph a store's "What's New" field takes.
    public var store: String

    public struct Card: Decodable, Equatable, Sendable, Identifiable {
        public var id: String { title }
        /// An SF Symbol the app already uses for the surface the card is about.
        public var icon: String
        public var title: String
        public var line: String
        /// `green`, `gold`, `red` or `blue`: which opaque chip the icon sits on.
        public var tint: String
    }
}
