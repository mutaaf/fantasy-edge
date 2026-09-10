import SwiftUI
import WidgetKit

/// A glanceable widget: your matchup, and the one player who can still move it.
///
/// It reads a snapshot the app writes into the shared container rather than
/// calling the API itself - a widget has a tight time budget and no business
/// holding a network connection open, and the app is already polling.
struct Snapshot: Codable {
    var league: String = "—"
    var you: String = "You"
    var opp: String = "Opponent"
    var yourScore: Double = 0
    var oppScore: Double = 0
    var winProb: Double = 0.5
    var phase: String = "pre"
    var leadName: String = ""
    var leadReason: String = ""
    var updated: Date = .now

    static let key = "fe.snapshot"
    static let suite = "group.fantasyedge"

    static func load() -> Snapshot {
        guard let d = UserDefaults(suiteName: suite)?.data(forKey: key),
              let s = try? JSONDecoder().decode(Snapshot.self, from: d)
        else { return Snapshot() }
        return s
    }
    func save() {
        guard let d = try? JSONEncoder().encode(self) else { return }
        UserDefaults(suiteName: Snapshot.suite)?.set(d, forKey: Snapshot.key)
        WidgetCenter.shared.reloadAllTimelines()
    }
}

struct Entry: TimelineEntry { let date: Date; let snap: Snapshot }

struct Provider: TimelineProvider {
    func placeholder(in c: Context) -> Entry { Entry(date: .now, snap: Snapshot()) }
    func getSnapshot(in c: Context, completion: @escaping (Entry) -> Void) {
        completion(Entry(date: .now, snap: Snapshot.load()))
    }
    func getTimeline(in c: Context, completion: @escaping (Timeline<Entry>) -> Void) {
        // Refresh often while games run, rarely when nothing is happening -
        // the widget budget is not spent on a board that cannot change.
        let snap = Snapshot.load()
        let next = snap.phase == "live" ? 60.0 * 5 : 60.0 * 30
        completion(Timeline(entries: [Entry(date: .now, snap: snap)],
                            policy: .after(.now.addingTimeInterval(next))))
    }
}

struct FantasyEdgeWidgetView: View {
    var entry: Entry
    @Environment(\.widgetFamily) private var family

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(entry.snap.league)
                .font(.system(size: 10, weight: .heavy)).kerning(1.1)
                .textCase(.uppercase).foregroundStyle(.secondary).lineLimit(1)
            HStack(alignment: .lastTextBaseline) {
                Text(entry.snap.yourScore, format: .number.precision(.fractionLength(1)))
                    .font(.system(size: 30, weight: .black))
                    .foregroundStyle(Color(red: 0.357, green: 0.761, blue: 0.212))
                Text("–").foregroundStyle(.tertiary)
                Text(entry.snap.oppScore, format: .number.precision(.fractionLength(1)))
                    .font(.system(size: 30, weight: .black))
                    .foregroundStyle(Color(red: 1.0, green: 0.294, blue: 0.294))
                Spacer()
                Text(entry.snap.winProb, format: .percent.precision(.fractionLength(0)))
                    .font(.system(size: 17, weight: .bold))
            }
            .monospacedDigit()
            if family != .systemSmall, !entry.snap.leadName.isEmpty {
                Divider().opacity(0.4)
                Text("MOST AT STAKE").font(.system(size: 8, weight: .heavy))
                    .kerning(1.1).foregroundStyle(.tertiary)
                Text(entry.snap.leadName).font(.system(size: 13, weight: .bold))
                    .lineLimit(1)
                Text(entry.snap.leadReason).font(.system(size: 11))
                    .foregroundStyle(.secondary).lineLimit(2)
            }
        }
        .padding(12)
        .containerBackground(for: .widget) {
            Color(red: 0.039, green: 0.102, blue: 0.373)
        }
    }
}

@main
struct FantasyEdgeWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "FantasyEdgeWidget", provider: Provider()) {
            FantasyEdgeWidgetView(entry: $0)
        }
        .configurationDisplayName("Your matchup")
        .description("Where your week stands, and who can still move it.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}
