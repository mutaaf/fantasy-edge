// Replays a real game through Gridiron and checks where it puts people.
//
// The live tab's whole claim is that a man is drawn on the grass exactly when
// his club can score him points on the next snap - and for a defence that is
// the snaps his club is *not* attacking on. No Sunday is guaranteed to have a
// game running when somebody wants to check that, so this takes a finished
// game's drives, turns each play back into the situation the live tier would
// have reported while it was live, and asserts the placement for every
// position on both sides of the ball.
//
//     curl -s http://127.0.0.1:8770/api/gamecast/401872657 > /tmp/gamecast.json
//     swiftc -o /tmp/verify-placement \
//         apple/FantasyEdge/Sources/Gridiron.swift \
//         apple/FantasyEdge/Sources/Gamecast.swift \
//         apple/verify_placement.swift && /tmp/verify-placement /tmp/gamecast.json
//
// Nothing here is bundled or mocked: it fails if the file is not a real
// gamecast, because a synthetic one would prove nothing about the feed.

import Foundation

var failures: [String] = []
var checks = 0

func expect(_ ok: Bool, _ what: @autoclosure () -> String) {
    checks += 1
    if !ok { failures.append(what()) }
}

@main
struct VerifyPlacement {
  static func main() throws {
    let path = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "/tmp/gamecast.json"
    guard let blob = FileManager.default.contents(atPath: path) else {
        FileHandle.standardError.write(Data("no gamecast at \(path)\n".utf8))
        exit(2)
    }
    let gc = try JSONDecoder().decode(Gamecast.self, from: blob)
    let clubs = [gc.home.mark, gc.away.mark]
    print("replaying \(gc.away.mark) at \(gc.home.mark) — \(gc.drives.count) drives, "
          + "\(gc.drives.reduce(0) { $0 + $1.plays.count }) plays")

    let skill = ["QB", "RB", "WR", "TE", "K"]
    var snaps = 0

    for drive in gc.drives {
        let offence = drive.team
        guard let defence = clubs.first(where: { $0 != offence }) else { continue }
        for play in drive.plays {
            // Only scrimmage downs: a kickoff comes through with down 0 or -1 and
            // the feed reports no possession for it, which is a different state.
            guard let down = play.down, down > 0, let from = play.from else { continue }
            snaps += 1
            let los = Gridiron.alongField(from)

            func place(_ pos: String, _ club: String) -> Gridiron.Spot {
                Gridiron.place(.init(pos: pos, state: "in",
                                     attacking: club == offence, toEndzone: from))
            }

            for pos in skill {
                let on = place(pos, offence), off = place(pos, defence)
                expect(on.station == .field,
                       "\(pos) of \(offence) should be on the field with the ball")
                expect(off.station == .bench,
                       "\(pos) of \(defence) should be benched while \(offence) attack")
                if let x = on.x {
                    // Behind the ball for everyone who lines up behind it, and
                    // never off the end of the field.
                    expect(x >= 0 && x <= 1, "\(pos) placed off the field at \(x)")
                    if Gridiron.depth(pos) < 0 && los > 0.10 {
                        expect(x < los, "\(pos) should start behind the ball (\(x) vs \(los))")
                    }
                    // Exactly on the ball, except within half a yard of either
                    // goal line, where the clamp that keeps a token inside the
                    // drawing wins - a receiver painted on the goal post would
                    // be worse than one painted half a yard off it.
                    if Gridiron.depth(pos) == 0 && los > 0.01 && los < 0.99 {
                        expect(abs(x - los) < 1e-9, "\(pos) should be on the ball")
                    }
                } else {
                    expect(false, "\(pos) on the field with no spot, from a play that has one")
                }
            }

            // The inversion. Exactly one of the two defences is playing, and it
            // is the one whose club does not have the ball - the bug this whole
            // file exists to catch is this pair coming out the other way round.
            let attackingDST = place("DEF", offence), defendingDST = place("DEF", defence)
            expect(defendingDST.station == .field,
                   "\(defence) D/ST should be on the field while \(offence) attack")
            expect(attackingDST.station == .bench,
                   "\(offence) D/ST should be benched while its own offence has the ball")
            if let x = defendingDST.x, los < 0.93 {
                expect(x > los, "a defence should line up beyond the ball (\(x) vs \(los))")
            }
        }
    }

    // The states that are not a snap. Every one of these is a real thing the live
    // payload says, and each has to come out somewhere other than the field.
    for pos in skill + ["DEF"] {
        expect(Gridiron.station(.init(pos: pos, state: "pre", attacking: nil,
                                      toEndzone: nil)) == .sideline,
               "\(pos) before kickoff should be on the sideline")
        expect(Gridiron.station(.init(pos: pos, state: "post", attacking: nil,
                                      toEndzone: nil)) == .done,
               "\(pos) after the whistle should be done")
        expect(Gridiron.station(.init(pos: pos, state: "in", attacking: nil,
                                      toEndzone: nil)) == .sideline,
               "\(pos) with nobody holding the ball should not be on the field")
    }
    // A man the feed says is attacking but gives no ball spot for is out there
    // without a place to stand, and must not be drawn on the fifty.
    expect(Gridiron.place(.init(pos: "WR", state: "in", attacking: true,
                                toEndzone: nil)).x == nil,
           "an unreported ball spot must not be filled in")

    // Lanes: two receivers from two different games must not overlap.
    expect(Gridiron.place(.init(pos: "WR", state: "in", attacking: true, toEndzone: 50),
                          index: 0).y
           != Gridiron.place(.init(pos: "WR", state: "in", attacking: true, toEndzone: 50),
                             index: 1).y,
           "two receivers at the same yardline landed in the same lane")

    // The scoreboard reading of a ball spot, both sides of midfield.
    expect(Gridiron.spot(toEndzone: 83, offence: "LAR", defence: "SF") == "LAR 17",
           "own half should read as the offence's own yard line")
    expect(Gridiron.spot(toEndzone: 12, offence: "LAR", defence: "SF") == "SF 12",
           "opposition half should read as the defence's yard line")
    expect(Gridiron.down(3, 7, toEndzone: 40) == "3rd & 7", "down and distance")
    expect(Gridiron.down(1, 10, toEndzone: 6) == "1st & Goal", "goal to go")
    expect(Gridiron.down(0, 0, toEndzone: 65) == nil, "a kickoff has no down")

    // ---- what is a snap, and where its three marks land ----
    //
    // Both halves of the bug this section was added for. The field drew the
    // feed's last row straight into geometry, and in a finished game that row
    // is END GAME with `down 0, distance 0, from 0, to 13`: a line of
    // scrimmage on the goal line and a gain line most of the way down the
    // field. Testing the down alone is not enough - a timeout in this same
    // feed comes through as `down 3, distance 1, from 0, to 48` - so `from`
    // has to be positive too, which it always is for a real snap because a
    // play from the zero has already scored.
    expect(!Gridiron.isSnap(down: 0, from: 0), "END GAME is not a snap")
    expect(!Gridiron.isSnap(down: 3, from: 0), "a timeout is not a snap")
    expect(!Gridiron.isSnap(down: 1, from: 0), "the two-minute warning is not a snap")
    expect(!Gridiron.isSnap(down: 0, from: 65), "a kickoff is not a scrimmage snap")
    expect(Gridiron.isSnap(down: 2, from: 6), "2nd and goal from the six is a snap")

    // The mapping, checked numerically rather than by eye - which is how the
    // stray marker survived a review in the first place. A twelve-hundred unit
    // box puts the goal lines at 100 and 1100, so a field coordinate x lands
    // at 100 + 1000x. From the 63 with three to gain, gaining eight:
    let m = Gridiron.marks(from: 63, to: 55, down: 3, distance: 3)
    let box: CGFloat = 1200
    expect(abs(FieldGeometry.px(m.los, box) - 470) < 1e-9,
           "line of scrimmage from the 63 should be 470, was \(FieldGeometry.px(m.los, box))")
    expect(abs(FieldGeometry.px(m.toGain ?? -1, box) - 500) < 1e-9,
           "line to gain with three to go should be 500, was "
           + "\(FieldGeometry.px(m.toGain ?? -1, box))")
    expect(abs(FieldGeometry.px(m.ball, box) - 550) < 1e-9,
           "ball at the 55 should be 550, was \(FieldGeometry.px(m.ball, box))")

    // Every one of them on the same mapping, so the ball cannot drift from the
    // markers it is drawn between.
    expect(FieldGeometry.px(Gridiron.alongField(0), box) == 1100, "the end zone is at 1100")
    expect(FieldGeometry.px(Gridiron.alongField(100), box) == 100, "the own goal is at 100")
    expect(FieldGeometry.px(Gridiron.alongField(50), box) == 600, "midfield is at 600")

    // Goal to go: the line to gain is the end zone, not four yards past it.
    let goal = Gridiron.marks(from: 8, to: 3, down: 3, distance: 12)
    expect(goal.toGain == Gridiron.alongField(0),
           "3rd and 12 from the eight should put the line to gain in the end zone")
    // A row with no down has no line to gain to draw.
    expect(Gridiron.marks(from: 20, to: 20, down: 0, distance: 0).toGain == nil,
           "a play with no down should draw no line to gain")

    // The red-zone zoom, which is the same coordinate at a different scale.
    // A man on the twenty is at the left edge, the goal line at the right, and
    // anybody further back than the twenty is pinned rather than drawn off it.
    expect(FieldGeometry.redZone(Gridiron.alongField(20)) == 0,
           "the twenty should be the left edge of the red-zone view")
    // A tolerance rather than equality: (1.0 - 0.8) / 0.2 is 0.9999999999999998
    // in binary floating point, and the drawing clamps to the view anyway.
    expect(abs(FieldGeometry.redZone(Gridiron.alongField(0)) - 1) < 1e-12,
           "the goal line should be the right edge of the red-zone view")
    expect(abs(FieldGeometry.redZone(Gridiron.alongField(10)) - 0.5) < 1e-9,
           "the ten should be halfway across the red-zone view")
    expect(FieldGeometry.redZone(Gridiron.alongField(35)) == 0,
           "a man behind the twenty should be pinned to the edge, not drawn off it")

    print("\(snaps) scrimmage snaps replayed, \(checks) assertions")
    if failures.isEmpty {
        print("OK")
    } else {
        for f in Set(failures).sorted() { print("FAIL: \(f)") }
        print("\(failures.count) failures")
        exit(1)
    }
  }
}
