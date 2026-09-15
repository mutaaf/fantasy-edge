// Replays real games through the stadium's geometry and checks where it puts
// things - the sibling of verify_placement.swift, for the 3D scene.
//
// The stadium renderer draws exactly what `SceneMath` computes from a scene
// the API served, so this decodes real scenes with the same `SceneSpec` the
// app uses and asserts the geometry against the contract stated in
// fantasyedge/scene.py: every arc peaks at its apex at the middle of the play
// and lands on the field at both ends, the ball and the lasers sit on their
// yard lines, the horizon stays between its rails, the seat puts the
// wearer's eyes where the stands are, and the ball's queue flies plays in
// order.
//
//     python3 tools/scene_samples.py /tmp/scenes     # writes replayed scenes
//     swiftc -o /tmp/verify-scene \
//         apple/FantasyEdge/Sources/Stadium/SceneSpec.swift \
//         apple/FantasyEdge/Sources/Stadium/SceneLook.swift \
//         apple/FantasyEdge/Sources/Stadium/Actors/*/*Look.swift \
//         apple/FantasyEdge/Sources/Stadium/SceneMath.swift \
//         apple/verify_scene.swift && /tmp/verify-scene /tmp/scenes/*.json
//
// Nothing is synthetic: a scene that does not decode fails, because a
// hand-made one would prove nothing about what the server sends.

import Foundation
import simd

var failures: [String] = []
var checks = 0

func expect(_ ok: Bool, _ what: @autoclosure () -> String) {
    checks += 1
    if !ok { failures.append(what()) }
}

func near(_ a: Float, _ b: Float, _ tol: Float = 1e-3) -> Bool { abs(a - b) <= tol }

@main
struct VerifyScene {
  static func main() throws {
    let paths = Array(CommandLine.arguments.dropFirst())
    guard !paths.isEmpty else {
        FileHandle.standardError.write(Data("usage: verify-scene scene.json...\n".utf8))
        exit(2)
    }
    var arcsChecked = 0
    for path in paths {
        guard let blob = FileManager.default.contents(atPath: path) else {
            FileHandle.standardError.write(Data("no scene at \(path)\n".utf8))
            exit(2)
        }
        let spec = try JSONDecoder().decode(SceneSpec.self, from: blob)
        let name = URL(fileURLWithPath: path).lastPathComponent
        expect(spec.version == "1.1", "\(name): unexpected scene version \(spec.version)")

        // ---- arcs: the apex formula, drawn ----
        for drive in spec.drives {
            for arc in drive.arcs {
                arcsChecked += 1
                let start = SceneMath.point(on: arc, at: 0)
                let mid = SceneMath.point(on: arc, at: 0.5)
                let end = SceneMath.point(on: arc, at: 1)
                expect(near(start.y, 0) && near(end.y, 0),
                       "\(name) \(arc.id): an arc must leave and land on the grass")
                expect(near(mid.y, Float(arc.apex)),
                       "\(name) \(arc.id): peak \(mid.y) should be the stated apex \(arc.apex)")
                expect(near(start.x, Float(arc.fromX - 50)) && near(end.x, Float(arc.toX - 50)),
                       "\(name) \(arc.id): ends should sit on the snap and finish yard lines")
                expect(near(mid.z, Float(arc.lane)), "\(name) \(arc.id): an arc keeps its lane")
                for t in stride(from: 0.0, through: 1.0, by: 0.125) {
                    expect(SceneMath.point(on: arc, at: t).y <= Float(arc.apex) + 1e-3,
                           "\(name) \(arc.id): nothing on an arc rises above its apex")
                }
                // The stated formula, independently of the server's arithmetic.
                let d = abs(arc.toX - arc.fromX)
                let want: Double = ["pass": 3.0 + 0.35 * d, "run": 0.8 + 0.12 * d,
                                    "kick": 8.0 + 0.25 * d, "flat": 0.0][arc.shape] ?? -1
                expect(abs(arc.apex - want) < 0.01,
                       "\(name) \(arc.id): \(arc.shape) apex \(arc.apex) is not the formula's \(want)")
                expect(arc.duration >= spec.motion.floorSeconds - 1e-9
                       && arc.seconds <= spec.motion.maxSeconds + 1e-9,
                       "\(name) \(arc.id): animation time out of bounds")
                if let dash = arc.dash, dash.count == 2, abs(arc.toX - arc.fromX) > 4 {
                    let pieces = SceneMath.dashes(arc)
                    expect(pieces.count > 1, "\(name) \(arc.id): a dashed arc drew solid")
                    for piece in pieces {
                        for p in piece {
                            expect(p.y >= -1e-3 && p.y <= Float(arc.apex) + 1e-3,
                                   "\(name) \(arc.id): a dash left its arc")
                        }
                    }
                }
            }
        }

        // ---- the ball and the lasers ----
        if let ball = spec.ball {
            let at = SceneMath.local(x: ball.x, z: ball.z)
            expect(near(at.x, Float(ball.x - 50)), "\(name): the ball is off its yard line")
            let scrimmage = spec.lasers.first { $0.kind == "scrimmage" }
            expect(scrimmage.map { near(Float($0.x), Float(ball.x)) } ?? false,
                   "\(name): the scrimmage laser should sit under the ball")
            if let gain = spec.lasers.first(where: { $0.kind == "lineToGain" }),
               let dist = spec.status.distance {
                let step = gain.x - ball.x
                expect(abs(abs(step) - Double(dist)) < 1e-6,
                       "\(name): line to gain \(step) yards from the ball, distance \(dist)")
                expect((step > 0) == (spec.status.possession == "home"),
                       "\(name): the line to gain points the wrong way")
            }
            if spec.activeMoment?.celebrates == true {
                expect(ball.beacon.color == "beacon.score", "\(name): a score should light the beacon")
            }
        } else {
            expect(spec.lasers.isEmpty, "\(name): lasers with no ball")
        }

        // ---- the horizon ----
        let horizon = SceneMath.horizon(spec.winProbability)
        if spec.winProbability.series.count > 1 {
            expect(horizon.count == spec.winProbability.series.count,
                   "\(name): one horizon point per probability")
            let h = spec.winProbability.horizon
            for p in horizon {
                expect(p.y >= Float(h.y0) - 1e-3 && p.y <= Float(h.y1) + 1e-3,
                       "\(name): the horizon left its rails at \(p.y)")
            }
        }

        // ---- the seat ----
        let st = spec.presentation.stadium
        let root = SceneMath.stadiumRoot(seat: st.seat, metersPerYard: st.metersPerYard, eye: 1.2)
        let seat = SceneMath.local(x: st.seat.x, y: st.seat.y, z: st.seat.z) * Float(st.metersPerYard)
        expect(simd_distance(root + seat, SIMD3(0, 0, 0)) < 1e-3,
               "\(name): the seat's floor should land on the floor of the space, under the wearer")
        // 1.1: every seat puts the wearer's eyes at the origin, facing its
        // lookAt down -z, with the world turned about them.
        for option in st.seats ?? [] {
            let placed = SceneMath.seatRoot(option, metersPerYard: st.metersPerYard, eye: 1.2)
            let s = placed.orientation.act(SceneMath.local(x: option.x, y: option.y, z: option.z) * Float(st.metersPerYard))
            expect(simd_distance(placed.position + s, SIMD3(0, 0, 0)) < 1e-3,
                   "\(name): seat \(option.id)'s floor does not land under the wearer")
            let target = placed.orientation.act(SceneMath.local(x: option.lookAt.x, y: 1.2 / st.metersPerYard,
                                                                z: option.lookAt.z) * Float(st.metersPerYard))
            let toward = placed.position + target
            let flat = simd_normalize(SIMD3(toward.x, 0, toward.z))
            expect(flat.z < -0.999, "\(name): seat \(option.id) should face its lookAt down -z, faces \(flat)")
            if let tier = spec.bowl.tiers.first(where: { option.y >= $0.rise[0] - 1e-6 && option.y <= $0.rise[1] + 1e-6 }),
               option.y > 0 {
                expect(option.y >= tier.rise[0] - 1e-3, "\(name): seat \(option.id) floats below its tier")
            }
        }
        if let look = spec.look {
            let seatPoint = SceneMath.local(x: 50, y: 12, z: 50)
            let near = [SceneMath.local(x: 50, y: 12, z: 45)]
            let s = SceneMath.nearSeatScale(near, seat: seatPoint, rule: look.broadcast.trail.nearSeat)
            expect(abs(s - max(look.broadcast.trail.nearSeat.minScale, 5 / look.broadcast.trail.nearSeat.yards)) < 1e-6,
                   "\(name): a trail 5 yards from the seat should thin to \(5 / look.broadcast.trail.nearSeat.yards), not \(s)")
        }
        let tt = spec.presentation.tabletop
        let reach = Float((spec.bowl.shape.halfLength + (spec.bowl.tiers.first?.outer ?? 0)) * tt.metersPerYard)
        expect(reach * 2 <= Float(tt.volume[0]) + 1e-3,
               "\(name): the tabletop bowl is \(reach * 2) m across, wider than its \(tt.volume[0]) m volume")

        // ---- seats: SceneMath.seat against scene.py's own placement ----
        let samplesPath = path.replacingOccurrences(of: ".json", with: ".seats")
        if let seating = spec.bowl.seating, let blob = FileManager.default.contents(atPath: samplesPath) {
            struct Sample: Decodable { let tier, row, run, k: Int; let x, y, z, nx, nz: Double }
            for sample in try JSONDecoder().decode([Sample].self, from: blob) {
                let row = seating.tiers[sample.tier].rows[sample.row]
                let ring = SceneMath.Ring(spec.bowl.shape, offset: row.feet)
                let got = SceneMath.seat(row, run: sample.run, k: sample.k, shape: spec.bowl.shape, ring: ring)
                expect(abs(Double(got.position.x) - sample.x) < 1e-3 && abs(Double(got.position.z) - sample.z) < 1e-3
                       && abs(Double(got.position.y) - sample.y) < 1e-3,
                       "\(name): seat \(sample) placed at \(got.position)")
                expect(abs(got.facing.x - sample.nx) < 1e-3 && abs(got.facing.y - sample.nz) < 1e-3,
                       "\(name): seat \(sample) faces \(got.facing)")
            }
            for tier in seating.tiers {
                for row in tier.rows {
                    let seated = row.runs.reduce(0) { $0 + Int($1[1]) }
                    expect(seated == row.seats, "\(name): \(tier.tier) row \(row.row) runs hold \(seated), not \(row.seats)")
                }
            }
        }

        // ---- the ball's queue ----
        if let drive = spec.shownDrive, drive.arcs.count > 2 {
            var motion = PlayMotion()
            let truncated = SceneSpec.Drive(id: drive.id, team: drive.team, side: drive.side,
                                            result: drive.result, arcs: Array(drive.arcs.dropLast(2)))
            expect(motion.arrive(truncated, initial: true).isEmpty,
                   "\(name): the first scene is history, nothing should fly")
            let fresh = motion.arrive(drive, initial: false)
            expect(fresh.map(\.id) == drive.arcs.suffix(2).map(\.id),
                   "\(name): exactly the two new plays should fly, in order")
            let first = motion.next(reduceMotion: false, floor: spec.motion.floorSeconds)
            expect(first?.0.id == fresh.first?.id && abs((first?.1 ?? 0) - (fresh.first?.duration ?? -1)) < 1e-9,
                   "\(name): the oldest new play flies first, for its stated duration")
            let second = motion.next(reduceMotion: true, floor: spec.motion.floorSeconds)
            expect(second?.1 == 0, "\(name): reduce motion lands the ball rather than flying it")
            expect(motion.next(reduceMotion: false, floor: 0) == nil, "\(name): the queue drains")
            expect(motion.arrive(drive, initial: false).isEmpty, "\(name): a play never flies twice")
        }
    }

    print("\(paths.count) scenes, \(arcsChecked) arcs, \(checks) assertions")
    if failures.isEmpty {
        print("OK")
    } else {
        for f in Set(failures).sorted() { print("FAIL: \(f)") }
        print("\(failures.count) failures")
        exit(1)
    }
  }
}
