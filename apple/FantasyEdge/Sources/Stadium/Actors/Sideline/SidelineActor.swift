import RealityKit
import simd

/// The sideline: goal posts, pylons, benches and the LED boards along the
/// front wall. The chains live with the broadcast package because they move
/// with the ball. Reads `field.props` and `visual.sideline`.
@MainActor
final class SidelineActor: StadiumActor {
    let name = "sideline"
    let root = Entity()

    init() { root.name = "actor.sideline" }

    func build(_ c: StadiumContext) {
        clear()
        let s = c.spec
        buildProps(s)
        buildBoards(c)
    }

    private func buildProps(_ s: SceneSpec) {
        guard let p = s.field.props else { return }
        let f = s.field, half = f.width / 2, pal = s.palette

        var pylons = MeshBuilder()
        let ps = Float(p.pylon.size / 2)
        for x in [-f.endZone, 0, f.length, f.length + f.endZone] {
            for z in [-half, half] {
                let c = SceneMath.local(x: x, y: 0, z: z)
                pylons.box(min: c + SIMD3(-ps, 0, -ps), max: c + SIMD3(ps, Float(p.pylon.height), ps))
            }
        }
        root.addChild(pylons.entity("pylons", StadiumLook.solid(pal[p.pylon.color] ?? "#FF6A13", roughness: 0.5)))

        // Goal posts: base behind the end line, a gooseneck forward, crossbar,
        // uprights. They cast the only dynamic shadows in the stadium.
        let g = p.goalpost
        var posts = MeshBuilder()
        var pads = MeshBuilder()
        for (xe, dir) in [(-f.endZone, -1.0), (f.length + f.endZone, 1.0)] {
            let xb = xe + dir * g.baseBehind
            let bar = Float(g.crossbar)
            var neck: [SIMD3<Float>] = [SceneMath.local(x: xb, y: 0, z: 0), SceneMath.local(x: xb, y: g.crossbar - 1.4, z: 0)]
            for k in 1...10 {
                let t = Double(k) / 10
                let px = xb + (xe - xb) * t * t
                let py = (g.crossbar - 1.4) + 1.4 * sin(t * .pi / 2)
                neck.append(SceneMath.local(x: px, y: py, z: 0))
            }
            posts.tube(neck, radius: Float(g.radius.base), sides: 10)
            let w = f.goalPostWidth / 2
            posts.tube([SceneMath.local(x: xe, y: g.crossbar, z: -w - 0.05), SceneMath.local(x: xe, y: g.crossbar, z: w + 0.05)],
                       radius: Float(g.radius.crossbar), sides: 10)
            for z in [-w, w] {
                posts.tube([SceneMath.local(x: xe, y: g.crossbar, z: z),
                            SceneMath.local(x: xe, y: g.crossbar + g.uprightAbove, z: z)], radius: Float(g.radius.upright), sides: 8)
            }
            let base = SceneMath.local(x: xb, y: 0, z: 0)
            let pw = Float(g.padWidth / 2)
            pads.box(min: base + SIMD3(-pw, 0, -pw), max: base + SIMD3(pw, min(bar - 1.6, Float(g.padHeight)), pw))
        }
        let postEntity = posts.entity("goalposts", StadiumLook.solid(pal[g.color] ?? "#F2C21B", roughness: 0.32,
                                                                     metallic: 0.15, cull: false))
        postEntity.components.set(DynamicLightShadowComponent(castsShadow: true))
        root.addChild(postEntity)
        root.addChild(pads.entity("goalpost.pads", StadiumLook.solid(pal[p.benches.color] ?? "#23272E", roughness: 0.8)))

        // Benches, each club's on its own sideline, a chip-coloured back.
        let b = p.benches
        for (team, sign) in [(s.teams.home, 1.0), (s.teams.away, -1.0)] {
            var seat = MeshBuilder(), back = MeshBuilder()
            let z = sign * (half + b.offset)
            seat.box(min: SceneMath.local(x: b.fromX, y: 0, z: z - b.depth / 2),
                     max: SceneMath.local(x: b.toX, y: b.height, z: z + b.depth / 2))
            let bz = Float(sign * b.depth / 2)
            back.box(min: SceneMath.local(x: b.fromX, y: b.height, z: z) + SIMD3(0, 0, bz - 0.06),
                     max: SceneMath.local(x: b.toX, y: b.height + b.backHeight, z: z) + SIMD3(0, 0, bz + 0.06))
            root.addChild(seat.entity("bench.\(team.abbr)", StadiumLook.solid(pal[b.color] ?? "#23272E", roughness: 0.6)))
            root.addChild(back.entity("bench.back.\(team.abbr)", StadiumLook.solid(team.chip, roughness: 0.55)))
        }
    }

    /// LED boards on the face of the stands' front wall, all the way round.
    private func buildBoards(_ c: StadiumContext) {
        let s = c.spec, V = c.look.sideline
        guard let wall = s.bowl.wall else { return }
        let shape = s.bowl.shape
        let S = c.look.bowl.segments
        let angles = (0...S).map { Double($0) / Double(S) * 2 * .pi }
        var board = MeshBuilder()
        var run: Float = 0
        for k in 0..<S {
            if c.cut(angles[k], angles[k + 1]) { continue }
            let a = SceneMath.bowlPoint(shape, offset: wall.offset, angle: angles[k])
            let b = SceneMath.bowlPoint(shape, offset: wall.offset, angle: angles[k + 1])
            let seg = Float(hypot(b.x - a.x, b.z - a.z))
            let panel = Float(V.boards.panelYards)
            let u0 = run / panel, u1 = (run + seg) / panel
            run += seg
            let h = Float(wall.height)
            // v runs up the image, so the board text reads upright.
            board.quad(SIMD3(Float(a.x), 0, Float(a.z)), SIMD3(Float(b.x), 0, Float(b.z)),
                       SIMD3(Float(b.x), h, Float(b.z)), SIMD3(Float(a.x), h, Float(a.z)),
                       uv: (SIMD2(u0, 0), SIMD2(u1, 0), SIMD2(u1, 1), SIMD2(u0, 1)))
        }
        let material: any Material = StadiumText.boards(s).map { StadiumLook.emissive("#FFFFFF", scale: V.boards.brightness, texture: $0) }
            ?? StadiumLook.solid(s.palette[wall.color] ?? "#07090D")
        root.addChild(board.entity("wall.boards", material))
    }
}
