import Foundation

/// Who has earned a plinth, and the record that put them on it.
///
/// A hall of fame that ranks people by nothing is a screensaver. Everything
/// below is a *claim*: a number that exists in `/api/player/<id>`, the field it
/// was measured against, and the season it came from. If a man has no claim he
/// gets no plinth, and the alcove stands empty rather than being filled with a
/// name.
///
/// Pure functions over `Profile`, no I/O and no RealityKit, for the same
/// reason `leverage.py` is: the arithmetic that decides who is honoured has to
/// be readable on its own, and a room is a bad place to debug a sort.
enum Hall {

    /// The four ways in, one per wing of the rotunda.
    ///
    /// Four rather than one composite score. A single "greatness" number would
    /// have to weigh a positional finish against a draft steal, and there is
    /// no honest exchange rate between them - so the hall does not invent one.
    /// Each wing ranks on its own record and says which record it is.
    enum Honour: String, CaseIterable, Hashable {
        /// Where he finished at his position, out of the field that actually
        /// scored. The most complete single statement a season log makes.
        case finish
        /// The best week he had. A season rank rewards the grind; this is the
        /// afternoon somebody remembers.
        case week
        /// Picked later than the market had him. `reach = adp - overall`, so a
        /// steal is a *negative* reach - see CLAUDE.md, this is the sign
        /// everybody gets backwards.
        case steal
        /// Weeks he actually put a score on the board. Availability is a
        /// skill and nothing else here measures it.
        case tenure

        /// The inscription over the alcove.
        var wing: String {
            switch self {
            case .finish: return "THE FINISH"
            case .week:   return "THE AFTERNOON"
            case .steal:  return "THE STEAL"
            case .tenure: return "THE INNINGS"
            }
        }
        /// What the wing honours, said once so a wearer knows what they are
        /// looking at without reading four plinths to work it out.
        var premise: String {
            switch self {
            case .finish: return "highest finish at his position"
            case .week:   return "biggest single week"
            case .steal:  return "furthest past his ADP"
            case .tenure: return "most weeks on the board"
            }
        }
        var glyph: String {
            switch self {
            case .finish: return "trophy.fill"
            case .week:   return "bolt.fill"
            case .steal:  return "arrow.down.right.circle.fill"
            case .tenure: return "calendar"
            }
        }
    }

    /// Which hall you are standing in. The fourth dimension, and the only one
    /// this app can honestly claim: seven seasons are in the database, and
    /// each of them inducts a different ten men off its own records.
    enum Era: Hashable, Identifiable {
        case season(Int)
        case allTime

        var id: String {
            switch self {
            case .season(let y): return "s\(y)"
            case .allTime:       return "all"
            }
        }
        var label: String {
            switch self {
            case .season(let y): return String(y)
            case .allTime:       return "ALL-TIME"
            }
        }
        var year: Int? {
            if case .season(let y) = self { return y }
            return nil
        }
    }

    /// One man's case for one wing.
    struct Claim {
        let honour: Honour
        /// Higher is better. Only ever compared against other claims in the
        /// same wing - a rank of 3 and a week of 42.1 are not on one scale and
        /// are never put on one.
        let strength: Double
        /// The record, as short as it can be said. Goes on the plinth in the
        /// large size.
        let headline: String
        /// Where the record came from, in enough detail to check it.
        let detail: String
    }

    /// A man with a plinth.
    struct Inductee: Identifiable, Equatable {
        let id: String
        let name: String
        let pos: String
        let team: String
        let img: String?
        let honour: Honour
        /// 1 is the leader of that wing for this era. Printed, because "second
        /// best week of 2021" is a different claim from "best week of 2021"
        /// and a plinth that hides the difference is overstating him.
        let place: Int
        let headline: String
        let detail: String

        static func == (a: Inductee, b: Inductee) -> Bool {
            a.id == b.id && a.honour == b.honour && a.place == b.place
                && a.headline == b.headline
        }
    }

    // MARK: - claims

    /// Positions whose draft price is a placeholder rather than a market.
    ///
    /// CLAUDE.md: kickers and defences sit near the bottom of every ADP board
    /// by default, so every one of them scores as an enormous steal or an
    /// enormous reach depending on where the pick landed. They are excluded
    /// from the reach aggregates in the Python analyses for exactly this
    /// reason and they are excluded here, or the steal wing would be four
    /// kickers deep and mean nothing.
    private static let noMarket: Set<String> = ["K", "DEF", "D/ST", "DST"]

    /// Every case this man can make in this era. At most one per wing.
    static func claims(_ p: Profile, era: Era) -> [Claim] {
        var out: [Claim] = []
        let rows = era.year.map { y in p.seasons.filter { $0.season == y } }
            ?? p.seasons

        // THE FINISH.
        //
        // Four weeks *scored*, and that guard is not belt and braces. The
        // server's own floor is four rows in the log with a number in them,
        // and a season in progress has a row per fixture with a zero in it -
        // so the first week of 2026 came back as a real rank, and the hall
        // duly inducted a man on "RB1 of 6" off one afternoon. A positional
        // finish means a season; below four games it is a scoreline.
        if let best = rows.compactMap({ r -> (SeasonRow, Int)? in
            guard let rank = r.rank, rank > 0, r.field > 0,
                  playedCount(r) >= 4 else { return nil }
            return (r, rank)
        }).min(by: { $0.1 < $1.1 }) {
            let (row, rank) = best
            let where_ = era.year == nil ? " in \(row.season)" : ""
            out.append(Claim(
                honour: .finish,
                // Inverted so higher is better like every other wing, and
                // scaled by the field so a QB12 of 40 does not outrank a WR12
                // of 99 just because both are twelfth.
                strength: 1 - Double(rank - 1) / Double(max(row.field, rank)),
                headline: "\(p.pos)\(rank) of \(row.field)\(where_)",
                // `row.weeks`, not the weeks he scored in. The server divides
                // the total by that to get `ppg`, and quoting a different
                // denominator beside its own average put two numbers on one
                // plinth that could not both be true - 402.5 over 17 weeks
                // next to 22.4 per game, which is 18.
                detail: "\(row.ppg.formatted(.number.precision(.fractionLength(1)))) "
                    + "per game, \(row.total.formatted(.number.precision(.fractionLength(1)))) "
                    + "points over \(count(row.weeks, "week"))"))
        }

        // THE AFTERNOON. `best` is the max of the weeks he actually played,
        // and the week number is recovered from the log so the plinth can say
        // which afternoon it was rather than just how big it got.
        if let top = rows.filter({ $0.best > 0 }).max(by: { $0.best < $1.best }) {
            let wk = (top.weekly ?? []).firstIndex(of: top.best).map { $0 + 1 }
            let when = wk.map { "week \($0) of \(top.season)" } ?? "\(top.season)"
            out.append(Claim(
                honour: .week,
                strength: top.best,
                headline: "\(top.best.formatted(.number.precision(.fractionLength(1)))) in a week",
                detail: "\(when), against a season average of "
                    + "\(top.ppg.formatted(.number.precision(.fractionLength(1))))"))
        }

        // THE STEAL. Negative reach only: a positive one means the pick came
        // *before* the market had him, which is a reach and is not an honour.
        if !noMarket.contains(p.pos.uppercased()) {
            let picks = (era.year.map { y in p.draft.filter { $0.season == y } }
                         ?? p.draft)
                .compactMap { d -> (DraftRow, Double)? in
                    guard let r = d.reach, r < 0 else { return nil }
                    return (d, -r)
                }
            if let (d, gain) = picks.max(by: { $0.1 < $1.1 }) {
                let where_ = era.year == nil ? " in \(d.season)" : ""
                let adp = d.adp.map {
                    " (ADP \($0.formatted(.number.precision(.fractionLength(0)))))"
                } ?? ""
                out.append(Claim(
                    honour: .steal,
                    strength: gain,
                    headline: "\(Int(gain.rounded())) picks past his ADP\(where_)",
                    detail: "round \(d.round.map(String.init) ?? "?"), "
                        + "pick \(d.overall.map(String.init) ?? "?")\(adp) "
                        + "in \(d.league ?? "your league")"))
            }
        }

        // THE INNINGS. Counted here rather than read off `career.totalWeeks`,
        // because that field sums `weeks`, which is rows in the log - and a
        // fixture he sat out is still a row with a zero in it. Availability
        // means weeks he put a number on the board, so the zeroes come out.
        let played = rows.reduce(0) { $0 + playedCount($1) }
        if played > 0 {
            let span = Set(rows.filter { playedCount($0) > 0 }.map(\.season))
                .sorted()
            let across = era.year == nil && span.count > 1
                ? ", \(span.first!)–\(span.last!)" : ""
            out.append(Claim(
                honour: .tenure,
                strength: Double(played),
                headline: "\(count(played, "week")) scored\(across)",
                detail: era.year == nil
                    ? "\(count(span.count, "season")) in your rooms"
                    : "out of \(count(rows.map(\.weeks).reduce(0, +), "week")) in the log"))
        }
        return out
    }

    private static func playedCount(_ r: SeasonRow) -> Int {
        (r.weekly ?? []).filter { $0 > 0 }.count
    }

    /// "1 week", not "1 weeks". A plinth is a piece of typography and the
    /// hall had three of these on it.
    private static func count(_ n: Int, _ noun: String) -> String {
        "\(n) \(noun)\(n == 1 ? "" : "s")"
    }

    // MARK: - the induction

    /// The order the wings are filled in, so the first four plinths a wearer
    /// sees are the four leaders and not four men from one wing.
    private static let rota: [Honour] = [.finish, .week, .steal, .tenure]

    /// Fill `bays` plinths from these profiles.
    ///
    /// Round-robin across the wings, best claim first. A man is inducted once
    /// and once only: the leader of the finish wing is very often also the
    /// leader of the tenure wing, and a hall with the same face on two plinths
    /// looks like a bug even when the two records are both true. He keeps the
    /// stronger claim - the one that came up first in the rota - and the next
    /// man down takes the other.
    static func induct(_ profiles: [Profile], era: Era, bays: Int) -> [Inductee] {
        var ranked: [Honour: [(Profile, Claim)]] = [:]
        for p in profiles {
            for c in claims(p, era: era) { ranked[c.honour, default: []].append((p, c)) }
        }
        for h in ranked.keys {
            ranked[h]?.sort { $0.1.strength > $1.1.strength }
        }

        var taken = Set<String>()
        var out: [Inductee] = []
        var cursor: [Honour: Int] = [:]
        var round = 0
        // Bounded rather than `while out.count < bays`: with three profiles
        // loaded and ten bays every wing runs dry and the loop never ends.
        while out.count < bays && round < bays + rota.count {
            for h in rota where out.count < bays {
                var i = cursor[h] ?? 0
                let list = ranked[h] ?? []
                while i < list.count, taken.contains(list[i].0.id) { i += 1 }
                cursor[h] = i + 1
                guard i < list.count else { continue }
                let (p, c) = list[i]
                taken.insert(p.id)
                out.append(Inductee(id: p.id, name: p.name, pos: p.pos, team: p.team,
                                    img: p.img, honour: h, place: i + 1,
                                    headline: c.headline, detail: c.detail))
            }
            round += 1
        }
        return out
    }

    /// Which eras this hall can actually be walked through.
    ///
    /// Derived from the records rather than hardcoded to a season range: a
    /// year with nothing in it would be a door onto ten empty plinths, and the
    /// wearer would read that as the app being broken rather than as the
    /// database not going back that far.
    static func eras(_ profiles: [Profile]) -> [Era] {
        var years = Set<Int>()
        for p in profiles {
            for r in p.seasons where r.best > 0 || r.rank != nil { years.insert(r.season) }
            for d in p.draft where (d.reach ?? 0) < 0 { years.insert(d.season) }
        }
        return [.allTime] + years.sorted(by: >).map { Era.season($0) }
    }
}
