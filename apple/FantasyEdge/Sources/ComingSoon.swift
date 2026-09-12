import SwiftUI

/// What a surface that has not been built yet says for itself.
///
/// Every other panel on this board refuses to fill a gap with a plausible
/// number; a tab that quietly showed the command centre instead of its own
/// content was the same lie in a larger size. This says the thing outright:
/// the name of what is coming, one line of what it will be, and the list of
/// what it is actually waiting on.
///
/// The traced network behind it is confined to exactly this view on purpose.
/// A neural motif over real figures was tried once on this board and thrown
/// out - "the neural network makes things confusing" - because a reader
/// cannot tell decoration from derivation when both are drawn in the same
/// ink. Over an empty surface there is no figure to confuse it with, which is
/// the one place the effect is honest.
struct ComingSoon: View {
    let title: String
    /// One sentence, in the register of the rest of the app: what this will
    /// answer, not what it will look like.
    let what: String
    /// What it is waiting on. Named rather than promised, because "soon" with
    /// no dependencies listed is the part nobody believes.
    var needs: [String] = []
    var icon: String = "sparkles"

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    /// Whether this view is in the hierarchy at all. The tab switch in
    /// `CommandView` tears the view down when you leave, so `onDisappear`
    /// alone would do - but a window that is merely occluded or backgrounded
    /// keeps the view alive, and an animated `TimelineView` left running
    /// there is a core burned to draw something nobody can see.
    @State private var onScreen = false

    private var animating: Bool {
        onScreen && scenePhase == .active && !reduceMotion
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                ZStack {
                    // A dark plate under the lattice, not decoration. The
                    // window is system glass and this app is used in a lit
                    // room, so a thin green line on the glass itself came out
                    // invisible against a white wall - the trace has to carry
                    // its own ground to be legible in any room.
                    RoundedRectangle(cornerRadius: 26)
                        .fill(RadialGradient(
                            colors: [Theme.navy.opacity(0.55), .black.opacity(0.82)],
                            center: .center, startRadius: 40, endRadius: 460))
                    NeuralTrace(animating: animating)
                    // The words win over the effect where they overlap it.
                    // Signals crossing behind a sentence make it flicker as
                    // you read, which is the exact failure that got the
                    // network thrown off the data views in the first place.
                    RadialGradient(colors: [.black.opacity(0.78), .clear],
                                   center: .center, startRadius: 30, endRadius: 320)
                    banner
                        .padding(.horizontal, 34)
                }
                .frame(height: 330)
                .frame(maxWidth: .infinity)
                .clipShape(.rect(cornerRadius: 26))
                .glassBackgroundEffect(in: .rect(cornerRadius: 26))

                if !needs.isEmpty { waitingOn }
            }
            .padding(.bottom, 10)
        }
        .scrollIndicators(.hidden)
        .onAppear { onScreen = true }
        .onDisappear { onScreen = false }
    }

    private var banner: some View {
        VStack(spacing: 13) {
            HStack(spacing: 8) {
                Image(systemName: icon).font(.system(size: 12))
                Text("NOT BUILT YET").font(.system(size: 9, weight: .heavy)).kerning(1.4)
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 13).padding(.vertical, 6)
            .background(Capsule().fill(Theme.greenFill))

            Text(title)
                .font(.system(size: 40, weight: .bold))
                .shadow(color: .black.opacity(0.6), radius: 14)

            Text(what)
                .font(.system(size: 14))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 520)
                .shadow(color: .black.opacity(0.7), radius: 10)
        }
    }

    private var waitingOn: some View {
        Panel(title: "What it is waiting on") {
            VStack(alignment: .leading, spacing: 9) {
                ForEach(Array(needs.enumerated()), id: \.offset) { i, line in
                    HStack(alignment: .top, spacing: 9) {
                        Text(String(format: "%02d", i + 1))
                            .font(.system(size: 10, weight: .heavy)).monospacedDigit()
                            .foregroundStyle(.secondary)
                            .padding(.top, 2)
                        Text(line).font(.system(size: 12)).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                NoSource(what: "Nothing on this tab is estimated or stubbed. "
                             + "When it can answer, it will answer from rows "
                             + "already in your database.")
            }
        }
    }
}


// MARK: - the traced network

/// A network being traced, drawn once and animated in a single `Canvas`.
///
/// The whole composition is one draw call's worth of paths rather than a
/// stack of animating views, because forty independently animating SwiftUI
/// shapes on a headset is a different cost from forty strokes in a canvas.
///
/// `animating` is not a styling flag. When it is false the `TimelineView` is
/// not built at all, so there is no schedule left holding a frame callback -
/// a paused schedule still exists, and this view has to cost nothing when its
/// tab is not the one showing.
struct NeuralTrace: View {
    var animating: Bool
    var tint: Color = Theme.green

    var body: some View {
        Group {
            if animating {
                // 30fps rather than the display's rate. Nothing here moves
                // fast enough for the other half of the frames to be visible,
                // and the canvas is redrawn in full every one of them.
                TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { ctx in
                    trace(at: ctx.date.timeIntervalSinceReferenceDate)
                }
            } else {
                // Reduce Motion, or off-screen: one composed still. Frozen at
                // a moment with signals part-way down several paths, so it
                // reads as the same picture stopped rather than as an empty
                // diagram.
                trace(at: TraceGraph.stillMoment)
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    private func trace(at t: Double) -> some View {
        Canvas { ctx, size in
            let g = TraceGraph.shared
            func at(_ i: Int) -> CGPoint {
                CGPoint(x: g.nodes[i].x * size.width, y: g.nodes[i].y * size.height)
            }

            // Every edge, once, as one path. The lattice is the quiet part;
            // it should read as wiring, not as content.
            var lattice = Path()
            for e in g.edges {
                lattice.move(to: at(e.a))
                lattice.addLine(to: at(e.b))
            }
            ctx.stroke(lattice, with: .color(tint.opacity(0.22)), lineWidth: 1.0)

            // A signal on each edge, and the glow it leaves on the node it is
            // arriving at. Accumulated rather than assigned, so a node fed by
            // three paths at once lights brighter than one fed by a single.
            var glow = [Double](repeating: 0, count: g.nodes.count)
            for e in g.edges {
                let u = (t * e.speed + e.phase).truncatingRemainder(dividingBy: 1)
                let a = at(e.a), b = at(e.b)
                let head = CGPoint(x: a.x + (b.x - a.x) * u, y: a.y + (b.y - a.y) * u)
                let v = max(0, u - 0.22)
                let tail = CGPoint(x: a.x + (b.x - a.x) * v, y: a.y + (b.y - a.y) * v)

                var streak = Path()
                streak.move(to: tail)
                streak.addLine(to: head)
                ctx.stroke(streak,
                           with: .linearGradient(
                            Gradient(colors: [tint.opacity(0), tint.opacity(0.85)]),
                            startPoint: tail, endPoint: head),
                           style: StrokeStyle(lineWidth: 2.2, lineCap: .round))

                ctx.fill(Path(ellipseIn: CGRect(x: head.x - 1.8, y: head.y - 1.8,
                                                width: 3.6, height: 3.6)),
                         with: .color(.white.opacity(0.85)))

                // The arriving node brightens over the last fifth of the run
                // and the departing one over the first, which is what makes
                // the lattice look like it is passing something along rather
                // than like dots sliding on wires.
                glow[e.b] += max(0, (u - 0.80) / 0.20)
                glow[e.a] += max(0, (0.14 - u) / 0.14)
            }

            for (i, n) in g.nodes.enumerated() {
                let lit = min(1.0, glow[i])
                let p = CGPoint(x: n.x * size.width, y: n.y * size.height)
                let r = 2.4 + lit * 3.4
                if lit > 0.05 {
                    ctx.fill(Path(ellipseIn: CGRect(x: p.x - r * 3, y: p.y - r * 3,
                                                    width: r * 6, height: r * 6)),
                             with: .radialGradient(
                                Gradient(colors: [tint.opacity(0.32 * lit), .clear]),
                                center: p, startRadius: 0, endRadius: r * 3))
                }
                ctx.fill(Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r,
                                                width: r * 2, height: r * 2)),
                         with: .color(tint.opacity(0.42 + 0.55 * lit)))
            }
        }
    }
}

/// The lattice itself: fixed, deterministic, and in unit coordinates so it is
/// built once for the life of the process and merely scaled to whatever room
/// the view is given. Generating it inside the canvas would have rebuilt forty
/// nodes and thirty-eight edges thirty times a second to draw the same graph.
struct TraceGraph {
    struct Edge {
        let a: Int, b: Int
        /// Where on the edge this signal starts, and how many runs a second
        /// it makes. Both fixed per edge, so nothing about the animation is
        /// stateful and any moment `t` can be drawn on its own - which is
        /// what lets the still fall out of the same code as the motion.
        let phase: Double, speed: Double
    }
    let nodes: [CGPoint]
    let edges: [Edge]

    static let shared = TraceGraph()
    /// The instant the Reduce Motion still freezes on. Chosen because at this
    /// point several signals are mid-flight and two nodes are lit, so the
    /// static frame is a composition rather than a bare graph.
    static let stillMoment: Double = 6.35

    private init() {
        var rng = TraceRNG(seed: 0x5EED_F00D)
        let counts = [3, 5, 6, 5, 3]
        var pts: [CGPoint] = []
        var layers: [[Int]] = []
        for (li, n) in counts.enumerated() {
            let x = 0.07 + 0.86 * Double(li) / Double(counts.count - 1)
            var idx: [Int] = []
            for k in 0..<n {
                let y = (Double(k) + 0.5) / Double(n)
                idx.append(pts.count)
                pts.append(CGPoint(x: x + (rng.unit() - 0.5) * 0.05,
                                   y: min(0.93, max(0.07,
                                          y + (rng.unit() - 0.5) * 0.11))))
            }
            layers.append(idx)
        }
        var es: [Edge] = []
        for li in 0..<(layers.count - 1) {
            for a in layers[li] {
                // The two nearest nodes in the next layer rather than two at
                // random: crossing wires everywhere reads as noise, and a
                // lattice that mostly flows forwards reads as a path.
                let ya = pts[a].y
                let near = layers[li + 1]
                    .sorted { abs(pts[$0].y - ya) < abs(pts[$1].y - ya) }
                for b in near.prefix(2) {
                    es.append(Edge(a: a, b: b, phase: rng.unit(),
                                   speed: 0.15 + rng.unit() * 0.22))
                }
            }
        }
        nodes = pts
        edges = es
    }
}

/// Deterministic, so the lattice is the same shape on every launch. A graph
/// that rearranges itself each time the tab opens looks like a bug in a board
/// whose whole claim is that the same input draws the same picture.
private struct TraceRNG {
    private var state: UInt64
    init(seed: UInt64) { state = seed }
    mutating func unit() -> Double {
        state = state &* 6364136223846793005 &+ 1442695040888963407
        return Double(state >> 11) / Double(UInt64(1) << 53)
    }
}
