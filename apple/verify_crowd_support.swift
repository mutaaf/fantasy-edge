// Checks whose crowd it is, against real scenes - the sibling of verify_crowd.swift, which
// checks what the crowd does.
//
//     python3 tools/scene_samples.py /tmp/scenes     # writes replayed scenes
//     swiftc -o /tmp/verify-crowd-support \
//         apple/FantasyEdge/Sources/Stadium/SceneSpec.swift \
//         apple/FantasyEdge/Sources/Stadium/SceneLook.swift \
//         apple/FantasyEdge/Sources/Stadium/Actors/*/*Look.swift \
//         apple/FantasyEdge/Sources/Stadium/Actors/Field/FieldArtSpec.swift \
//         apple/FantasyEdge/Sources/Stadium/SceneMath.swift \
//         apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdSupport.swift \
//         apple/verify_crowd_support.swift && /tmp/verify-crowd-support /tmp/scenes/*.json
//
// The contract, after integration-13 read the visiting support as a painted wedge:
//
//  1. Every visiting seat is on the visitors' side of the bowl, the side the scene names.
//  2. No seat within `clearance` of a wearer's seat preset wears the visitors' colours, so the
//     rows a wearer looks along are the home crowd's.
//  3. The visitors hold a minority of the seats, in the share the tokens ask for.
//  4. The boundary is mixed rather than painted: the sections that carry visitors also carry
//     home shirts, and no section is unanimous.
//  5. Empty seats come in blocks: a run of taken seats is longer than one seat on average.

import Foundation
import simd

@main
struct VerifyCrowdSupport {
    static func main() {
        var checks = 0
        var failures: [String] = []
        let paths = CommandLine.arguments.dropFirst().filter { $0.hasSuffix(".json") }
        guard !paths.isEmpty else {
            print("usage: verify-crowd-support <scene.json> ...")
            exit(2)
        }
        let look: SceneSpec.Look
        do {
            let tokens = try Data(contentsOf: URL(fileURLWithPath: "design/tokens.json"))
            struct Tokens: Decodable { let visual: SceneSpec.Look }
            look = try JSONDecoder().decode(Tokens.self, from: tokens).visual
        } catch {
            print("run from the repository root: design/tokens.json (\(error))")
            exit(2)
        }
        let C = look.crowd

        for path in paths {
            let name = (path as NSString).lastPathComponent
            guard let blob = FileManager.default.contents(atPath: path) else {
                failures.append("\(name): unreadable")
                continue
            }
            let spec: SceneSpec
            do {
                spec = try JSONDecoder().decode(SceneSpec.self, from: blob)
            } catch {
                failures.append("\(name): \(error)")
                continue
            }
            guard let seating = spec.bowl.seating else {
                failures.append("\(name): the scene carries no seating")
                continue
            }
            let drawn = Set(seating.tiers.map(\.tier))
            let pulls = CrowdSupport.supportBySection(spec, look: C, drawn: drawn)
            let visitorsFar = (spec.bowl.crowd.awaySection?.side ?? "far") == "far"
            // "A wearer's seat preset", as rule 2 says: the look-dev presets
            // (the camera well behind the away end line, the wall) are places
            // the harness shoots from and the picker never offers, so the
            // colours around them are nobody's comfort. Added with those
            // seats in experience-r8; the rule itself is unchanged.
            let seats = (spec.presentation.stadium.seats ?? []).filter { $0.lookdev != true }.map {
                SIMD3<Float>(Float($0.x - 50), Float($0.y), Float($0.z))
            }
            var counts: [CrowdSupport.Kind: Int] = [:]
            var perSection: [CrowdSupport.SectionKey: [CrowdSupport.Kind: Int]] = [:]
            var runsTaken = 0, seatsTaken = 0

            for tier in seating.tiers {
                let sections = tier.sections ?? []
                for row in tier.rows {
                    let ring = SceneMath.Ring(spec.bowl.shape, offset: row.feet)
                    for (runIndex, run) in row.runs.enumerated() where run.count == 2 {
                        var takenRun = false
                        for k in 0..<Int(run[1]) {
                            let spot = SceneMath.seat(row, run: runIndex, k: k, shape: spec.bowl.shape, ring: ring)
                            let p = spot.position
                            let keep = CrowdSupport.keepChance(at: p, tier: tier.tier, row: row.row, seat: k,
                                                               seats: Int(run[1]), look: C, spec: spec)
                            // The fill draw itself is the actor's; here the shape of the chance is what matters.
                            let taken = keep > 0.5
                            if taken {
                                seatsTaken += 1
                                if !takenRun { runsTaken += 1; takenRun = true }
                            } else {
                                takenRun = false
                            }
                            let fraction = ((run[0] + Double(k) * row.pitch) / max(1e-6, row.length))
                                .truncatingRemainder(dividingBy: 1)
                            let section = sections.firstIndex { sec in
                                sec.to <= 1 ? (fraction >= sec.from && fraction < sec.to)
                                            : (fraction >= sec.from || fraction < sec.to - 1)
                            } ?? Int(fraction * Double(max(1, sections.count)))
                            let key = CrowdSupport.SectionKey(tier: tier.tier, section: section)
                            let wears = CrowdSupport.supportAt(pull: pulls[key], tierRows: tier.rows.count,
                                                               row: row.row, seat: k, section: section, look: C)
                            counts[wears, default: 0] += 1
                            perSection[key, default: [:]][wears, default: 0] += 1

                            if wears == .away {
                                checks += 1
                                let onVisitorsSide = visitorsFar ? p.z < 0 : p.z > 0
                                if !onVisitorsSide {
                                    failures.append("\(name): a visiting seat at z \(p.z) is on the home side")
                                }
                            }
                            // Neither club's colours belong beside the wearer either: at crowd-r6's
                            // first pass the unaligned were seated at midfield, a row in front of the
                            // upper seat, and read as a violet block in the wide frame.
                            if wears != .home {
                                checks += 1
                                for seat in seats where simd_distance(SIMD3(p.x, 0, p.z), SIMD3(seat.x, 0, seat.z)) < 14 {
                                    failures.append("\(name): a \(wears.name) seat sits \(Int(simd_distance(SIMD3(p.x, 0, p.z), SIMD3(seat.x, 0, seat.z)))) yd from a wearer's seat preset")
                                }
                            }
                        }
                    }
                }
            }

            let total = max(1, counts.values.reduce(0, +))
            let away = Double(counts[.away] ?? 0) / Double(total)
            let neutral = Double(counts[.neutral] ?? 0) / Double(total)
            checks += 2
            if away > C.support.visitingShare * 2 {
                failures.append("\(name): the visitors hold \(Int(away * 100))% of the seats, more than twice their share")
            }
            if away < 0.01 {
                failures.append("\(name): the visitors hold \(Int(away * 100))% of the seats: nobody travelled")
            }
            if neutral > C.support.neutralShare * 2.5 {
                failures.append("\(name): \(Int(neutral * 100))% of seats wear neither club")
            }
            // The boundary must be mixed: every section carrying visitors carries home shirts too.
            for (key, mix) in perSection where (mix[.away] ?? 0) > 0 {
                checks += 1
                let here = max(1, mix.values.reduce(0, +))
                if Double(mix[.away] ?? 0) / Double(here) > 0.97 {
                    failures.append("\(name): \(key.tier) section \(key.section) is unanimous: a painted block, not a crowd")
                }
            }
            // Empty seats in blocks: the average run of taken seats is several seats long.
            checks += 1
            let perRun = Double(seatsTaken) / Double(max(1, runsTaken))
            if perRun < 3 {
                failures.append("\(name): taken seats come in runs of \(String(format: "%.1f", perRun)): empties are scattered singly")
            }
        }

        print("\(checks) crowd support checks over \(paths.count) scenes")
        if failures.isEmpty {
            print("OK")
        } else {
            for f in Set(failures).sorted().prefix(12) { print("FAIL: \(f)") }
            print("\(failures.count) failures")
            exit(1)
        }
    }
}
