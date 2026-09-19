import SwiftUI

// How the stadium's panels behave, as opposed to how they look: folding,
// resting translucent until looked at, getting out of the way of a moment,
// the controls folding to a pill, the Crown hint and the seat picker. The
// panels' own visuals (scorebug, drive log) belong to Broadcast.

/// Rests at `rest` opacity and comes up to `hover` when looked at, and fades
/// out of the way while a celebrated moment is up. Gaze never reaches the app:
/// the system applies the hover state, so this is the only way to brighten a
/// panel under the wearer's eyes without knowing where they look.
struct StadiumPanelPresence: ViewModifier {
    let rest: Double
    let hover: Double
    let yielding: Bool
    let yieldOpacity: Double
    let fadeSeconds: Double
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        content
            .contentShape(.hoverEffect, RoundedRectangle(cornerRadius: 30))
            .hoverEffect { effect, isActive, _ in
                effect.opacity(isActive ? hover : rest)
            }
            .opacity(yielding ? yieldOpacity : 1)
            .allowsHitTesting(!yielding)
            .animation(reduceMotion ? nil : .easeInOut(duration: fadeSeconds), value: yielding)
    }
}

extension View {
    func stadiumPanel(_ layout: SceneSpec.Look.Layout?, _ panels: SceneSpec.Look.Panels?, yielding: Bool) -> some View {
        modifier(StadiumPanelPresence(rest: layout?.restOpacity ?? 1, hover: layout?.hoverOpacity ?? 1,
                                      yielding: yielding, yieldOpacity: panels?.momentOpacity ?? 0,
                                      fadeSeconds: panels?.momentFadeSeconds ?? 0.3))
    }
}

/// A side panel that folds to a 60-point tab. Reduce motion folds it for a
/// moment rather than fading it, so nothing animates.
struct FoldablePanel<Content: View>: View {
    let title: String
    let symbol: String
    @Binding var folded: Bool
    let yielding: Bool
    @ViewBuilder let content: () -> Content
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        if folded || (yielding && reduceMotion) {
            Button { folded = false } label: {
                Label(title, systemImage: symbol)
                    .font(.system(size: 17, weight: .semibold))
                    .padding(.horizontal, 20)
                    .frame(minHeight: 60)
            }
            .buttonStyle(.plain)
            .glassBackgroundEffect()
            .accessibilityHint("Unfolds the \(title) panel")
        } else {
            content()
                .overlay(alignment: .topTrailing) {
                    Button { folded = true } label: {
                        Image(systemName: "chevron.down")
                            .font(.system(size: 18, weight: .semibold))
                            .frame(width: 60, height: 60)
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("Fold \(title)")
                }
        }
    }
}

/// The controls, folded: one pill, one tap to bring them back.
struct ControlsPill: View {
    let reveal: () -> Void

    var body: some View {
        Button(action: reveal) {
            Label("Controls", systemImage: "slider.horizontal.3")
                .font(.system(size: 17, weight: .semibold))
                .padding(.horizontal, 22)
                .frame(minHeight: 60)
        }
        .buttonStyle(.plain)
        .glassBackgroundEffect()
        .accessibilityLabel("Show controls")
        .accessibilityHint("Brings the panels to where you are looking, and opens play, seat, sound, immersion and leave")
    }
}

/// Said once, the first time the wearer is looking well away from the dock:
/// the panels are where they left them, and this is how to call them over.
struct RecentreHint: View {
    var body: some View {
        Label("Pinch anywhere, or tap Controls, to bring the panels to you",
              systemImage: "hand.pinch")
            .font(.system(size: 19, weight: .semibold))
            .padding(.horizontal, 24).padding(.vertical, 16)
            .glassBackgroundEffect()
            .accessibilityAddTraits(.isStaticText)
    }
}

/// Said once, the first time the stadium opens on the dial.
struct CrownHint: View {
    var body: some View {
        Label("Turn the Digital Crown to fill the room with the stadium", systemImage: "dial.medium")
            .font(.system(size: 19, weight: .semibold))
            .padding(.horizontal, 24).padding(.vertical, 16)
            .glassBackgroundEffect()
            .accessibilityAddTraits(.isStaticText)
    }
}

/// A map of the bowl from above with every seat on it. The shape, the tiers
/// and the seats are the scene's; the map only scales them to fit.
struct SeatPickerView: View {
    let spec: SceneSpec
    let current: String
    let sit: (String) -> Void
    let close: () -> Void

    private var picker: SceneSpec.Look.SeatPicker? { ExperienceTokens.picker(spec) }

    var body: some View {
        let dims = picker
        let width = CGFloat(dims?.widthPoints ?? 340), height = CGFloat(dims?.heightPoints ?? 260)
        let dot = CGFloat(dims?.dotPoints ?? 60), inset = CGFloat(dims?.insetPoints ?? 18)
        let seats = spec.presentation.stadium.seats ?? []
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Pick a seat").font(.system(size: 22, weight: .semibold))
                Spacer()
                Button(action: close) {
                    Image(systemName: "xmark").font(.system(size: 18, weight: .semibold)).frame(width: 60, height: 60)
                }
                .buttonStyle(.borderless)
                .accessibilityLabel("Close the seat picker")
            }
            HStack(alignment: .top, spacing: 18) {
                ZStack {
                    Canvas { ctx, size in drawBowl(ctx, size, inset: inset) }
                    ForEach(seats) { seat in
                        let p = mapPoint(seat.x, seat.z, CGSize(width: width, height: height), inset: inset)
                        Button { sit(seat.id) } label: {
                            ZStack {
                                Circle().strokeBorder(.white.opacity(seat.id == current ? 0.95 : 0), lineWidth: 3)
                                Circle().fill(seat.id == current ? Color.white : Color.white.opacity(0.7))
                                    .frame(width: 14, height: 14)
                            }
                            .frame(width: dot, height: dot)
                            .contentShape(Circle())
                        }
                        .buttonStyle(.plain)
                        .hoverEffect(.highlight)
                        .position(p)
                        .accessibilityLabel(seat.label)
                        .accessibilityAddTraits(seat.id == current ? .isSelected : [])
                    }
                }
                .frame(width: width, height: height)
                // The same seats as a list: several sit close together along
                // one sideline on a map this small, and a row is easier to hit.
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(seats) { seat in
                        Button { sit(seat.id) } label: {
                            HStack(spacing: 10) {
                                Image(systemName: seat.id == current ? "checkmark.circle.fill" : "circle")
                                    .font(.system(size: 18))
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(seat.label).font(.system(size: 16, weight: .semibold)).lineLimit(1)
                                    Text(String(format: "%.0f m up", seat.y * spec.presentation.stadium.metersPerYard))
                                        .font(.system(size: 13)).foregroundStyle(.secondary)
                                }
                                Spacer(minLength: 0)
                            }
                            .padding(.horizontal, 12)
                            .frame(width: CGFloat(dims?.listWidthPoints ?? 320), height: dot, alignment: .leading)
                            .contentShape(RoundedRectangle(cornerRadius: 14))
                        }
                        .buttonStyle(.plain)
                        .hoverEffect(.highlight)
                        .accessibilityLabel(seat.label)
                        .accessibilityAddTraits(seat.id == current ? .isSelected : [])
                    }
                }
            }
        }
        .fixedSize()
        .padding(22)
        .glassBackgroundEffect()
    }

    /// Field x (-10...110) and z (±width/2) onto the map, the home sideline at the bottom.
    private func mapPoint(_ x: Double, _ z: Double, _ size: CGSize, inset: CGFloat) -> CGPoint {
        let shape = spec.bowl.shape
        let outer = spec.bowl.tiers.map(\.outer).max() ?? 70
        let halfX = shape.halfLength + outer, halfZ = shape.halfWidth + outer
        let scale = min((size.width - 2 * inset) / (2 * halfX), (size.height - 2 * inset) / (2 * halfZ))
        return CGPoint(x: size.width / 2 + (x - 50) * scale, y: size.height / 2 + z * scale)
    }

    private func drawBowl(_ ctx: GraphicsContext, _ size: CGSize, inset: CGFloat) {
        let shape = spec.bowl.shape
        for tier in spec.bowl.tiers {
            for offset in [tier.inner, tier.outer] {
                var path = Path()
                for k in 0...96 {
                    let pt = SceneMath.bowlPoint(shape, offset: offset, angle: Double(k) / 96 * 2 * .pi)
                    let m = mapPoint(pt.x + 50, pt.z, size, inset: inset)
                    k == 0 ? path.move(to: m) : path.addLine(to: m)
                }
                ctx.stroke(path, with: .color(.white.opacity(0.35)), lineWidth: 1.5)
            }
        }
        let f = spec.field
        let a = mapPoint(-f.endZone, -f.width / 2, size, inset: inset)
        let b = mapPoint(f.length + f.endZone, f.width / 2, size, inset: inset)
        let field = Path(CGRect(x: a.x, y: a.y, width: b.x - a.x, height: b.y - a.y))
        let turf = SceneMath.rgba(spec.palette["turf.a"] ?? "#1E6A34")
        ctx.fill(field, with: .color(Color(red: Double(turf.x), green: Double(turf.y), blue: Double(turf.z))))
        ctx.stroke(field, with: .color(.white.opacity(0.6)), lineWidth: 1)
    }
}
