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
//         apple/FantasyEdge/Sources/Stadium/Actors/Field/FieldArtSpec.swift \
//         apple/FantasyEdge/Sources/Stadium/SceneMath.swift \
//         apple/FantasyEdge/Sources/Stadium/Actors/Broadcast/BroadcastFlight.swift \
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
    /// Every scene's venue and livery, by event, for the check below.
    var venues: [String: (venue: StadiumVenue, livery: String, name: String)] = [:]
    for path in paths {
        guard let blob = FileManager.default.contents(atPath: path) else {
            FileHandle.standardError.write(Data("no scene at \(path)\n".utf8))
            exit(2)
        }
        let spec = try JSONDecoder().decode(SceneSpec.self, from: blob)
        let name = URL(fileURLWithPath: path).lastPathComponent
        expect(spec.version == "1.3", "\(name): unexpected scene version \(spec.version)")
        venues[spec.event] = (StadiumVenue(spec), StadiumVenue.livery(spec), name)

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

            // ---- goal kicks: the ball crosses the posts' plane as the text says ----
            if let post = spec.field.props?.goalpost {
                for arc in spec.drives.flatMap(\.arcs) where arc.type.lowercased().contains("field goal") {
                    let text = arc.text.lowercased()
                    guard !text.contains("blocked"), arc.toX != arc.fromX else { continue }
                    let plane = arc.toX > arc.fromX ? spec.field.length + spec.field.endZone : -spec.field.endZone
                    let t = (plane - arc.fromX) / (arc.toX - arc.fromX)
                    guard t > 0, t < 1 else {
                        expect(text.contains("short"), "\(name): kick \(arc.id) never reaches the posts")
                        continue
                    }
                    let kickFlight = look.broadcast.ball.flight
                    let p = BallFlight.pose(arc, t: t, elapsed: 0, manner: BallFlight.manner(arc, kickFlight), flight: kickFlight, lift: 0).position
                    let half = Float(spec.field.goalPostWidth / 2)
                    if text.contains("good") && !text.contains("no good") {
                        expect(abs(p.z) < half && p.y > Float(post.crossbar),
                               "\(name): good kick \(arc.id) crosses the posts at z \(p.z), y \(p.y)")
                    } else if text.contains("wide") {
                        expect(abs(p.z) > half, "\(name): wide kick \(arc.id) goes between the uprights")
                    }
                }
            }

            // ---- the ball: BallFlight against every arc of the game ----
            let flight = look.broadcast.ball.flight
            for arc in spec.drives.flatMap(\.arcs) {
                let manner = BallFlight.manner(arc, flight)
                for t in [0.0, 0.25, 0.5, 0.75, 1.0] {
                    let pose = BallFlight.pose(arc, t: t, elapsed: t * arc.duration, manner: manner, flight: flight, lift: 0)
                    let onArc = SceneMath.point(on: arc, at: t)
                    expect(pose.position.y >= -1e-4, "\(name): arc \(arc.id) puts the ball under the grass at t \(t)")
                    expect(abs(pose.position.x - onArc.x) <= 1e-3 && abs(pose.position.z - onArc.z) <= 1e-3,
                           "\(name): arc \(arc.id) (\(manner)) leaves its line at t \(t)")
                    let nose = pose.orientation.act(SIMD3<Float>(1, 0, 0))
                    let laces = pose.orientation.act(SIMD3<Float>(0, 1, 0))
                    expect(abs(simd_length(nose) - 1) < 1e-3, "\(name): arc \(arc.id) orientation is not a rotation")
                    let travel: Float = arc.toX >= arc.fromX ? 1 : -1
                    var tangent = SceneMath.point(on: arc, at: min(1, t + 0.02)) - SceneMath.point(on: arc, at: max(0, t - 0.02))
                    if simd_length(tangent) < 1e-5 { tangent = SIMD3(travel, 0, 0) }
                    tangent = simd_normalize(tangent)
                    switch manner {
                    case .spiral:
                        // A spiral points down its flight and never flips end for end.
                        expect(simd_dot(nose, tangent) > 0.999, "\(name): pass \(arc.id) spiral off its flight at t \(t): nose \(nose)")
                    case .wobble:
                        let limit = Float(cos((flight.wobbleDegrees + 0.5) * .pi / 180))
                        expect(simd_dot(nose, tangent) >= limit, "\(name): wobble \(arc.id) turned more than a wobble at t \(t)")
                    case .carry:
                        expect(nose.x * travel > 0.9 && laces.y > 0.9,
                               "\(name): carry \(arc.id) is not tucked nose-forward, laces up at t \(t)")
                    case .tumble, .bounce:
                        break
                    }
                    if manner != .bounce {
                        expect(abs(pose.position.y - onArc.y) <= 0.5,
                               "\(name): arc \(arc.id) (\(manner)) leaves its height at t \(t)")
                    }
                }
            }

            // ---- the play's path: scene.play_path flown by SceneMath and BallFlight ----
            let play = look.broadcast.play
            let floor: Float = 0.1
            for arc in spec.drives.flatMap(\.arcs) {
                guard let path = arc.path else {
                    expect(false, "\(name): arc \(arc.id) has no path")
                    continue
                }
                expect(!path.segments.isEmpty && path.segments[0].phase == "presnap",
                       "\(name): arc \(arc.id) does not start on its spot")
                let start = SceneMath.ball(on: arc, at: 0).position
                expect(abs(start.x - Float(arc.fromX - 50)) < 1e-3, "\(name): arc \(arc.id) snaps at \(start.x + 50), not \(arc.fromX)")
                var previous: SIMD3<Float>? = nil
                let steps = 60
                for i in 0...steps {
                    let t = path.seconds * Double(i) / Double(steps)
                    let pose = BallFlight.pose(arc, seconds: t, flight: flight, floor: floor)
                    expect(pose.position.y >= floor - 1e-4, "\(name): arc \(arc.id) puts the ball in the grass at \(t)s")
                    expect(abs(simd_length(pose.orientation.act(SIMD3<Float>(1, 0, 0))) - 1) < 1e-3,
                           "\(name): arc \(arc.id) orientation is not a rotation at \(t)s")
                    if let prev = previous {
                        // At most a hundred yards a second: nothing on a play teleports.
                        let step = simd_distance(SIMD2(prev.x, prev.z), SIMD2(pose.position.x, pose.position.z))
                        expect(Double(step) <= 100 * path.seconds / Double(steps) + 0.05,
                               "\(name): arc \(arc.id) jumps \(step) yd at \(t)s")
                    }
                    previous = pose.position
                    if let seg = SceneMath.ball(on: arc, at: t).segment, seg.kind == "air", seg.phase != "snap" {
                        let heading = pose.orientation.act(SIMD3<Float>(1, 0, 0))
                        if BallFlight.manner(arc, flight) == .spiral {
                            let ahead = SceneMath.ball(on: arc, at: t + 0.02).position - SceneMath.ball(on: arc, at: max(0, t - 0.02)).position
                            if simd_length(ahead) > 1e-3 {
                                expect(simd_dot(simd_normalize(ahead), heading) > 0.95,
                                       "\(name): pass \(arc.id) spiral off its flight at \(t)s")
                            }
                        }
                    }
                }
                // A kick at the posts leaves play where SceneMath.kickCut says:
                // inside its flight, past the plane, and before the arc's end.
                if let cut = SceneMath.kickCut(arc, field: spec.field, netYards: play.goalKick.netYards) {
                    expect(cut > 0 && cut < path.seconds, "\(name): kick \(arc.id) cut \(cut) outside its path")
                    let attack: Double = arc.toX > arc.fromX ? 1 : -1
                    let plane = attack > 0 ? spec.field.length + spec.field.endZone : -spec.field.endZone
                    let at = Double(SceneMath.ball(on: arc, at: cut).position.x) + 50
                    expect((at - plane) * attack >= play.goalKick.netYards - 0.2,
                           "\(name): kick \(arc.id) cut at \(at), short of the posts at \(plane)")
                    expect(SceneMath.ball(on: arc, at: cut).position.y > 0.5,
                           "\(name): kick \(arc.id) is already down at the posts")
                }
                let line = SceneMath.trace(arc, count: 72, lift: play.heights.trailLift)
                expect(line.count > 1 && line.allSatisfy { $0.y >= -1e-4 }, "\(name): arc \(arc.id) trail under the grass")
                if ["run"].contains(arc.shape) && !arc.type.lowercased().contains("interception") && !arc.type.lowercased().contains("fumble") {
                    expect(line.allSatisfy { Double($0.y) <= play.heights.trailLift + 1e-3 },
                           "\(name): run \(arc.id) trail stands off the grass")
                }
                let cap = 2.0
                let low = SceneMath.lowered(arc, cap: cap)
                let airTops = (low.path?.segments ?? []).filter { $0.kind == "air" }
                    .map { max($0.from?[1] ?? 0, $0.to?[1] ?? 0) + ($0.rise ?? 0) }
                expect(airTops.allSatisfy { $0 <= max(cap, 2.2) + 1e-6 }, "\(name): arc \(arc.id) lowered still flies high")
                let partial = SceneMath.trace(arc, count: 72, lift: play.heights.trailLift, until: path.seconds / 2)
                expect(partial.count <= line.count + 2, "\(name): arc \(arc.id) half a trail is longer than the whole")
            }
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

        // ---- the crowd faces the field ----
        // Every seat, placed the way CrowdActor places a kit fan (CrowdFacing), must look
        // toward the field. The kit's forward axis comes from its manifest, where build.py
        // records what it measured in each exported file: in round 3 the headset's USDZ
        // faced -Z while its glTF twin faced +Z, and every near fan sat facing its chair back.
        if let seating = spec.bowl.seating {
            var fansChecked = 0
            for tier in seating.tiers {
                for row in tier.rows {
                    let ring = SceneMath.Ring(spec.bowl.shape, offset: row.feet)
                    for (run, span) in row.runs.enumerated() where span.count == 2 {
                        for k in stride(from: 0, to: Int(span[1]), by: 5) {
                            let got = SceneMath.seat(row, run: run, k: k, shape: spec.bowl.shape, ring: ring)
                            let facing = SIMD3<Float>(Float(got.facing.x), 0, Float(got.facing.y))
                            let looks = CrowdFacing.placedForward(facing: facing)
                            let toField = simd_normalize(SIMD3<Float>(-got.position.x, 0, -got.position.z))
                            fansChecked += 1
                            expect(simd_dot(looks, toField) > 0.2,
                                   "\(name): a fan in \(tier.tier) row \(row.row) seat \(k) would look \(looks), away from the field \(toField)")
                        }
                    }
                }
            }
            expect(fansChecked > 1000, "\(name): only \(fansChecked) seats checked for facing")
        }
        struct KitManifest: Decodable { let forward: [String: String]? }
        if let blob = FileManager.default.contents(atPath: "assets/actors/crowd/manifest.json"),
           let kit = try? JSONDecoder().decode(KitManifest.self, from: blob) {
            let files = (kit.forward ?? [:]).filter { $0.key != "about" }
            expect(files.count == 6, "the crowd kit's manifest should record the measured forward of all six pose files, has \(files.keys.sorted())")
            for (file, axis) in files {
                expect(axis == "+Z", "the crowd kit's \(file) faces \(axis): CrowdFacing turns +Z onto the seat, so those fans sit backwards")
            }
        } else {
            expect(false, "run verify_scene from the repository root: assets/actors/crowd/manifest.json not found")
        }

        // ---- a stand wears its own club's colour ----
        // The crowd dresses from `teams.*.color`, the club's stated colour, and is allowed
        // to move exactly one thing about it: HSV value, up to the measured floor. Round 9
        // found both sides dressed instead from `bowl.crowd`'s panel chips, which are solved
        // for white text on a card - so a club that paints its field black had a mid-grey
        // crowd, and two clubs whose chips collided were pushed apart in hue.
        let floor = Float(spec.look?.crowd.clubValue.floor ?? 0)
        for team in [spec.teams.home, spec.teams.away] where spec.look != nil {
            let stated = SceneMath.rgba(team.color), worn = CrowdCloth.of(stated, floor: floor)
            let vIn = max(stated.x, max(stated.y, stated.z)), vOut = max(worn.x, max(worn.y, worn.z))
            expect(vOut >= min(floor, max(vIn, floor)) - 1e-4,
                   "\(name): \(team.abbr) is worn at value \(vOut), under the floor \(floor)")
            expect(vOut <= max(vIn, floor) + 1e-4,
                   "\(name): \(team.abbr) is worn at value \(vOut), lighter than its own \(vIn) and the floor \(floor)")
            // Hue and saturation survive a value lift exactly, because the lift is one
            // scale of all three channels. Compare the channel ratios, which is what a hue is.
            if vIn > 1e-4 && vOut > 1e-4 {
                for c in 0..<3 {
                    let a = stated[c] / vIn, b = worn[c] / vOut
                    expect(abs(a - b) < 2e-3,
                           "\(name): dressing \(team.abbr) moved channel \(c) from \(a) to \(b) of its value: that is a hue or saturation shift, not a lift")
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
            expect(first?.0.id == fresh.first?.id && abs((first?.1 ?? 0) - (fresh.first?.flightSeconds ?? -1)) < 1e-9,
                   "\(name): the oldest new play flies first, for its stated duration")
            let second = motion.next(reduceMotion: true, floor: spec.motion.floorSeconds)
            expect(second?.1 == 0, "\(name): reduce motion lands the ball rather than flying it")
            expect(motion.next(reduceMotion: false, floor: 0) == nil, "\(name): the queue drains")
            expect(motion.arrive(drive, initial: false).isEmpty, "\(name): a play never flies twice")
        }
    }

    // ---- a venue is the building, not the clubs in it ----
    //
    // The whole reason the stadium can follow a red-zone channel: three
    // different matchups in one league share one venue, so moving between
    // them repaints rather than rebuilds - a fifth of a second against four.
    // If a club-bearing value ever leaks into `StadiumVenue`, this is what
    // says so, and the cost would otherwise only show up as a stadium that
    // stutters every time the channel moves.
    if venues.count > 1 {
        let sorted = venues.sorted { $0.key < $1.key }
        let (firstEvent, first) = sorted[0]
        for (event, other) in sorted.dropFirst() {
            expect(other.venue == first.venue,
                   "\(other.name): \(event) is the same league and bowl as \(firstEvent) "
                   + "but a different venue, so every switch between them rebuilds")
            expect(other.livery != first.livery,
                   "\(other.name): \(event) and \(firstEvent) are different clubs but the "
                   + "same livery, so a switch between them would not repaint")
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
