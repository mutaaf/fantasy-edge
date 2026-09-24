#if os(visionOS)
import SwiftUI

/// The red-zone channel at the wearer's right hand: every game, the most
/// urgent first, and the switch that lets the bowl follow the ball.
///
/// The Elsewhere panel this sits beside answers "what else is on". This
/// answers "where should I be", which is a different question and the reason
/// the channel exists: on a sixteen-game Sunday nobody can watch the right
/// game by reading a list of scores, and on a Saturday there are seventy-four
/// of them and thirty running at once.
///
/// It lives in the package because both products show the same panel over the
/// same payload. Nothing in it is a Sunday's or a Saturday's: the ranking, the
/// order, the reason and the wording all arrive from `/api/redzone`.
public struct RedZonePanel: View {
    let channel: RedZoneChannel
    /// The game the bowl is showing, which is not always the one wanted: a
    /// changeover takes a moment and the panel must not lie during it.
    let showing: String
    var rows = 6
    @Binding var following: Bool
    let watch: (String) -> Void

    public init(channel: RedZoneChannel, showing: String, rows: Int = 6,
                following: Binding<Bool>, watch: @escaping (String) -> Void) {
        self.channel = channel
        self.showing = showing
        self.rows = rows
        self._following = following
        self.watch = watch
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Text("Red Zone").font(.system(size: 20, weight: .semibold))
                if let day = channel.day {
                    // A rebuilt day is marked beside its own name, not once
                    // on a screen the wearer may never have seen.
                    Text("REBUILT \(day.label)")
                        .font(.system(size: 10, weight: .heavy))
                        .padding(.horizontal, 5).padding(.vertical, 2)
                        .background(.orange.opacity(0.28), in: .capsule)
                        .accessibilityLabel("Rebuilt from timestamps, \(day.label)")
                }
                Spacer()
                Text(headline).font(.system(size: 14)).foregroundStyle(.secondary)
            }
            if let day = channel.day, let first = day.caveats.first {
                Text("Rebuilt from play timestamps, not recorded. \(first)")
                    .font(.system(size: 12)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Toggle("Follow the ball", isOn: $following)
                .font(.system(size: 15))
                .frame(minHeight: 44)
            if following, !channel.reason.isEmpty {
                // Why the bowl is where it is. A channel that cuts without
                // saying why reads as random, and on a headset the wearer
                // cannot see the producer's reasoning anywhere else.
                Text("Here because: \(channel.reason)")
                    .font(.system(size: 14)).foregroundStyle(.secondary)
            }
            if let error = channel.error {
                Text(error).font(.system(size: 13)).foregroundStyle(.secondary)
            }
            ForEach(ranked.prefix(rows)) { g in
                Button { if g.openable { watch(g.event) } } label: {
                    HStack(spacing: 10) {
                        if g.redZone {
                            Text("RED ZONE")
                                .font(.system(size: 10, weight: .heavy))
                                .padding(.horizontal, 5).padding(.vertical, 2)
                                .background(.red.opacity(0.85), in: .capsule)
                        }
                        VStack(alignment: .leading, spacing: 2) {
                            Text(g.line).font(.system(size: 16, weight: .semibold))
                            if !g.situation.isEmpty {
                                Text(g.situation).font(.system(size: 12)).foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                        }
                        Spacer()
                        Text(g.live ? g.score : g.kickoffShort)
                            .font(.system(size: 16, weight: .bold)).monospacedDigit()
                        // A game this source cannot draw says so here rather
                        // than letting the row look like every other one and
                        // then opening onto nothing.
                        Text(g.event == showing ? "▶" : g.openable ? " " : "—")
                            .font(.system(size: 12)).foregroundStyle(.secondary)
                    }
                    .frame(minHeight: 44)
                    .contentShape(.rect)
                    .opacity(g.openable ? 1 : 0.45)
                }
                .buttonStyle(.plain)
                .disabled(!g.openable)
                .accessibilityHint(g.openable ? "" : "Not recorded from this source")
            }
        }
        .padding(22)
        .frame(width: 420, alignment: .leading)
        .glassBackgroundEffect()
    }

    /// Live games by urgency - the channel's own order - then the rest by
    /// kickoff. A final is not a destination and sinks to the bottom.
    private var ranked: [RedZoneChannel.Game] {
        let live = channel.games.filter(\.live)
        let rest = channel.games.filter { !$0.live }
            .sorted { ($0.state == "post" ? 1 : 0, $0.kickoff) < ($1.state == "post" ? 1 : 0, $1.kickoff) }
        return live + rest
    }

    private var headline: String {
        let c = channel.counts
        if c.live == 0 { return c.total == 0 ? "" : "nothing live yet" }
        let zone = c.redZone > 0 ? ", \(c.redZone) in the red zone" : ""
        return "\(c.live) live\(zone)"
    }
}
#endif
