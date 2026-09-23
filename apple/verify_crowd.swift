// Checks the crowd's pose decision (CrowdChoreography) exhaustively.
//
//     swiftc -parse-as-library -o /tmp/verify-crowd packages/swift/StadiumKit/Sources/StadiumKit/Actors/Crowd/CrowdChoreography.swift \
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
        // Third down with no moment on: the defending side is up, the side at the line is hushed.
        for hushAway in [false, true] {
            for phaseStep in 0..<10 {
                for t in stride(from: 0.0, through: 8.0, by: 0.1) {
                    let phase = Double(phaseStep) / 10
                    let i = C.Input(away: hushAway, isCard: phaseStep % 2 == 0, phase: phase, standing: phaseStep % 3 == 0,
                                    slice: phaseStep, time: t, standingSideAway: !hushAway, hush: true)
                    let p = C.pose(i)
                    checks += 1
                    if C.celebrates(p) {
                        failures.append("hush: a side whose own offence is at the line showed \(p.rawValue) at t=\(t) phase=\(phase)")
                    }
                    let up = C.Input(away: !hushAway, isCard: phaseStep % 2 == 0, phase: phase, slice: phaseStep,
                                     time: t, standingSideAway: !hushAway)
                    checks += 1
                    if C.pose(up) == .sit || C.pose(up) == .sitB {
                        failures.append("third down: the defending side stayed seated at t=\(t) phase=\(phase)")
                    }
                }
            }
        }
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
                // Round 5: a neutral section watches, it does not celebrate; a visiting section
                // celebrates its own score but smaller than a home crowd does; and a side whose own
                // offence is at the line on third down is in its seats, not roaring.
                for groupAway in [false, true] {
                    let isScoring = (scorer == "away") == groupAway
                    var homeLike = 0, visitorLike = 0, frames = 0
                    for phaseStep in 0..<10 {
                        for t in stride(from: 0.0, through: 6.0, by: 0.1) {
                            let phase = Double(phaseStep) / 10
                            let base = C.Input(away: groupAway, isCard: true, phase: phase, slice: phaseStep, time: t,
                                               tintSide: scorer, surgeAway: scorer == "away")
                            var neutral = base; neutral.neutral = true
                            checks += 1
                            if C.celebrates(C.pose(neutral)) {
                                failures.append("\(kind) by \(scorer): a neutral section celebrated (\(C.pose(neutral).rawValue)) at t=\(t)")
                            }
                            guard isScoring else { continue }
                            var visiting = base; visiting.visitorsScoring = true; visiting.visitorCelebration = 0.55
                            frames += 1
                            if C.celebrates(C.pose(base)) { homeLike += 1 }
                            if C.pose(visiting) == .cheer { visitorLike += 1 }
                        }
                    }
                    if isScoring {
                        checks += 1
                        let homeCheer = Double(homeLike) / Double(max(1, frames))
                        let visitorCheer = Double(visitorLike) / Double(max(1, frames))
                        if visitorCheer >= homeCheer {
                            failures.append("\(kind) by \(scorer): a visiting section cheered as hard as a home one (\(visitorCheer) vs \(homeCheer))")
                        }
                        if visitorCheer == 0 {
                            failures.append("\(kind) by \(scorer): a visiting section did not celebrate its own score at all")
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
