// Checks the crowd's pose decision (CrowdChoreography) exhaustively.
//
//     swiftc -parse-as-library -o /tmp/verify-crowd apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdChoreography.swift \
//         apple/verify_crowd.swift && /tmp/verify-crowd
//
// The contract: while either team's touchdown or field goal is on, and as it
// settles, the side that was scored on never celebrates - whatever cues
// Moments sends, whatever the surge, phase, ring, wave, third-down stand or
// reduce motion. And the scoring side does celebrate on at least most frames.

import Foundation

typealias C = CrowdChoreography

@main
struct VerifyCrowd {
    static func main() {
        var checks = 0
        var failures: [String] = []

        let cueSets: [[C.CueKind]] = [[], [.stand], [.clap], [.groan], [.sit], [.stand, .groan], [.clap, .sit]]
        for scorer in ["home", "away"] {
            for kind in ["touchdown", "fieldGoal"] {
                var scoringCelebrated = 0, scoringFrames = 0
                for groupAway in [false, true] {
                    let isScoring = (scorer == "away") == groupAway
                    for isCard in [false, true] {
                        for reduce in [false, true] {
                            for cues in cueSets {
                                for standingSide in [nil, false, true] as [Bool?] {
                                    for phaseStep in 0..<10 {
                                        for t in stride(from: 0.0, through: 12.0, by: 0.25) {
                                            let phase = Double(phaseStep) / 10
                                            // Moment on for 6 s, then settling.
                                            let on = t < 6
                                            let input = C.Input(
                                                away: groupAway, isCard: isCard, phase: phase, standing: phaseStep % 4 == 0,
                                                slice: phaseStep, slices: 12, time: t, reduceMotion: reduce,
                                                tintSide: on ? scorer : nil, lastScoringAway: on ? nil : scorer == "away",
                                                lastScoringEnded: 6, surgeAway: t < 4.5 ? scorer == "away" : nil,
                                                standingSideAway: standingSide, cues: cues)
                                            let p = C.pose(input)
                                            checks += 1
                                            let scoredOnDuringMoment = !isScoring && on
                                            if scoredOnDuringMoment && C.celebrates(p) {
                                                failures.append("\(kind) by \(scorer): \(groupAway ? "away" : "home") group celebrated (\(p.rawValue)) at t=\(t) phase=\(phase) cues=\(cues) card=\(isCard) reduce=\(reduce)")
                                            }
                                            if isScoring && on && !reduce && cues.allSatisfy({ $0 != .sit && $0 != .groan }) {
                                                scoringFrames += 1
                                                if C.celebrates(p) { scoringCelebrated += 1 }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                // Near slots with the ripple and the staged rise: the scored-on side never shows a
                // celebrating slot; the scoring side is up by its delay plus two stages.
                for groupAway in [false, true] {
                    let isScoring = (scorer == "away") == groupAway
                    for delay in [0.0, 0.4, 1.2] {
                        for look in [-1, 0, 1] {
                            for t in stride(from: 0.0, through: 6.0, by: 0.05) {
                                let input = C.Input(away: groupAway, phase: 0.3, time: 10 + t, tintSide: scorer,
                                                    surgeAway: scorer == "away", momentStarted: 10, delay: delay,
                                                    riseStageSeconds: 0.35, look: look)
                                let slot = C.slot(input)
                                checks += 1
                                if !isScoring && C.celebrates(slot) {
                                    failures.append("\(kind) by \(scorer): scored-on near group showed \(slot.rawValue) at t=\(t)")
                                }
                                if isScoring && t < delay && C.celebrates(slot) {
                                    failures.append("\(kind) by \(scorer): celebrated at t=\(t) before its ripple delay \(delay)")
                                }
                                if isScoring && t >= delay + 0.75 && !C.celebrates(slot) {
                                    failures.append("\(kind) by \(scorer): still seated (\(slot.rawValue)) at t=\(t), delay \(delay)")
                                }
                            }
                        }
                    }
                }
                checks += 1
                if scoringFrames == 0 || Double(scoringCelebrated) / Double(scoringFrames) < 0.9 {
                    failures.append("\(kind) by \(scorer): the scoring side celebrated on only \(scoringCelebrated)/\(scoringFrames) frames")
                }
            }
        }

        if failures.isEmpty {
            print("\(checks) crowd choreography checks\nOK")
        } else {
            for f in failures.prefix(20) { print("FAIL", f) }
            print("\(failures.count) failures in \(checks) checks")
            exit(1)
        }
    }
}
