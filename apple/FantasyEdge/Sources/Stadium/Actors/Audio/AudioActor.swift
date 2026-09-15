import Foundation
import RealityKit
import simd

/// The sound of the stadium, placed where it comes from.
///
///   beds      the crowd from `bedEmitters` points round the lower bowl (the
///             one nearest the wearer `nearBoost` dB louder), rhythmic
///             clapping from the home stands, the PA and concourse murmur
///             from the press box, wind over the rim as ambience
///   moments   on the scene's timeline (`visual.moments.timeline`), the same
///             schedule Moments plays its light to: the referee's whistle
///             from the field, the scoring side's roar or cheer from that
///             side's seats, fireworks from the rim, the PA chime. A turnover
///             is a sting from the side that took it and a groan from the
///             side that lost it
///   cues      the horn, the two-minute chime, the rumble into the red zone,
///             the third-down swell, the final cheer or the exodus
///   plays     a soft whistle as each drawn play lands
///
/// Every level is `visual.audio.gains` + `masterGain`; every file was
/// normalised when it was made (tools/audio/build.py), so nothing here can be
/// louder than it was designed. The tabletop plays a miniature mix: fewer
/// beds, `tabletop.gain` quieter, falling off fast so it stays on the table.
/// Reduce motion keeps the sound but swells rather than bursts. Mute stops
/// everything. No sound is invented: every one follows something in the scene.
@MainActor
final class AudioActor: StadiumActor {
    let name = "audio"
    let root = Entity()
    private var beds: [(entity: Entity, controller: AudioPlaybackController, key: String, base: Double)] = []
    private var active = 0
    private var muted = false
    private var steps: [(at: Double, run: @MainActor () -> Void)] = []
    private var lastCue: String?
    /// When the composer's own red-zone event fired: the server's red-zone cue
    /// for the same crossing arrives a poll later and must not play twice.
    private var redZoneAt = -Double.infinity
    private var lastArc: String?
    private var landed = 0
    private var nearBed: Int?

    /// The whole stadium's level on top of the mix, in dB: how the space
    /// arrives, ducks through a seat change and fades on the way out
    /// (`visual.audio.experience`). A linear ramp in dB, applied per frame.
    private struct Ramp {
        var from: Double, to: Double, start: Double, seconds: Double
        func value(at t: Double) -> Double {
            guard seconds > 0 else { return to }
            let u = max(0, min(1, (t - start) / seconds))
            return from + (to - from) * u
        }
        func done(at t: Double) -> Bool { t >= start + seconds }
    }
    private var envelope = Ramp(from: 0, to: 0, start: 0, seconds: 0)
    private var applied = Double.nan
    private var pausedByLeave = false
    private var events: [ExperienceEvent] = []
    private var observer: NSObjectProtocol?

    init() {
        root.name = "actor.audio"
        // Experience posts its beats; Audio scores them on the next frame,
        // where the context and the frame clock are at hand.
        observer = NotificationCenter.default.addObserver(forName: ExperienceEvents.name, object: nil,
                                                          queue: .main) { [weak self] note in
            guard let event = note.userInfo?["event"] as? ExperienceEvent else { return }
            MainActor.assumeIsolated { self?.events.append(event) }
        }
    }

    // MARK: build

    func build(_ c: StadiumContext) {
        beds.forEach { $0.controller.stop() }
        beds.removeAll()
        steps.removeAll()
        clear()
        active = 0
        nearBed = nil
        muted = c.shared.muted
        pausedByLeave = false
        applied = .nan
        let A = c.look.audio
        // The stadium never snaps on: its beds rise from arrivalStartDb, so a
        // launch straight into a seat is as gentle as walking through the gate.
        let X = A.experience
        envelope = c.tabletop ? Ramp(from: 0, to: 0, start: 0, seconds: 0)
            : Ramp(from: X.arrivalStartDb, to: 0, start: c.shared.time,
                   seconds: c.reduceMotion ? X.reducedSeconds : X.arriveSeconds)
        root.components.set(ReverbComponent(reverb: .preset(Self.reverbPreset(A.reverb))))

        let count = c.tabletop ? A.tabletop.bedEmitters : A.bedEmitters
        if let tier = c.tiers.first, count > 0 {
            let m = (tier.inner + tier.outer) / 2
            for k in 0..<count {
                let t = Double(k) / Double(count) * 2 * .pi + 0.4
                let p = SceneMath.bowlPoint(c.spec.bowl.shape, offset: m, angle: t)
                let at = SIMD3(Float(p.x), Float(SceneMath.tierHeight(tier, offset: m)), Float(p.z))
                bed("crowdBed", at: at, c)
            }
        }
        if !c.tabletop {
            bed("clapBed", at: section("home", c), c)
            bed("murmurBed", at: c.shared.pressBox, c)
            if let wind = c.assets.audio["audio.windBed"] {
                let e = Entity()
                e.components.set(AmbientAudioComponent(gain: Audio.Decibel(level("windBed", c))))
                root.addChild(e)
                let controller = e.playAudio(wind)
                if muted { controller.pause() }
                beds.append((e, controller, "windBed", level("windBed", c)))
            }
        }
    }

    private func bed(_ key: String, at position: SIMD3<Float>, _ c: StadiumContext) {
        guard let sound = c.assets.audio["audio.\(key)"] else { return }
        let e = Entity()
        e.position = position
        e.components.set(spatial(level(key, c), c))
        root.addChild(e)
        let controller = e.playAudio(sound)
        if muted { controller.pause() }
        beds.append((e, controller, key, level(key, c)))
    }

    // MARK: frame

    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        if c.shared.muted != muted {
            muted = c.shared.muted
            if !pausedByLeave { beds.forEach { muted ? $0.controller.pause() : $0.controller.play() } }
        }
        if !steps.isEmpty {
            let due = steps.filter { $0.at <= frame.time }
            steps.removeAll { $0.at <= frame.time }
            for step in due { step.run() }
        }
        if !events.isEmpty {
            let now = events
            events.removeAll()
            for e in now { experience(e, c) }
        }
        boostNearest(c)
        applyEnvelope(frame.time, c)
    }

    // MARK: the way in and out (ExperienceEvents)

    private func experience(_ event: ExperienceEvent, _ c: StadiumContext) {
        let X = c.look.audio.experience
        let now = c.shared.time
        let reduced = c.reduceMotion
        let current = envelope.value(at: now)
        switch event {
        case .gateOpening(let seconds, let swellLead):
            // Over the table: the miniature swells toward the stadium as the
            // gate rises. With reduce motion the space opens at once (0 s),
            // so the level steps instead of sweeping.
            guard c.tabletop else { return }
            let lead = max(0, seconds - swellLead)
            let over = reduced || seconds <= 0 ? X.reducedSeconds : max(X.gateSwellSeconds, swellLead)
            schedule(now + (reduced ? 0 : lead)) { [weak self, c] in
                guard let self else { return }
                self.envelope = Ramp(from: self.envelope.value(at: c.shared.time), to: X.gateSwellDb,
                                     start: c.shared.time, seconds: over)
            }
        case .arrived:
            guard !c.tabletop else { return }
            pausedByLeave = false
            nearBed = nil                       // re-pick the wearer's section
            envelope = Ramp(from: current, to: 0, start: now, seconds: reduced ? X.reducedSeconds : X.arriveSeconds)
        case .seatChanging(_, let fadeSeconds):
            guard !c.tabletop else { return }
            // Down to near-silence by the time the world is dark, hold, and
            // come back up; the new seat's section boost is re-picked from
            // shared.seat as Experience moves it.
            let down = reduced ? min(X.reducedSeconds, fadeSeconds) : max(0.05, fadeSeconds)
            envelope = Ramp(from: current, to: X.seatDuckDb, start: now, seconds: down)
            let back = reduced ? X.reducedSeconds : X.seatReturnSeconds
            schedule(now + down + X.seatHoldSeconds) { [weak self, c] in
                guard let self else { return }
                self.nearBed = nil
                self.envelope = Ramp(from: X.seatDuckDb, to: 0, start: c.shared.time, seconds: back)
            }
        case .panelsYielded(let yielded):
            guard !c.tabletop, X.yieldDb != 0 else { return }
            envelope = Ramp(from: current, to: yielded ? X.yieldDb : 0, start: now,
                            seconds: reduced ? X.reducedSeconds : X.yieldSeconds)
        case .leaving:
            guard !c.tabletop else { return }
            let over = reduced ? X.reducedSeconds : X.leaveFadeSeconds
            envelope = Ramp(from: current, to: X.silenceDb, start: now, seconds: over)
            schedule(now + over) { [weak self] in
                guard let self else { return }
                self.beds.forEach { $0.controller.pause() }
                self.pausedByLeave = true
            }
        }
    }

    /// Set every bed's gain to its mix level plus the envelope, only when the
    /// envelope moved by a tenth of a dB: a settled stadium costs nothing.
    private func applyEnvelope(_ time: Double, _ c: StadiumContext) {
        let db = envelope.value(at: time)
        if !applied.isNaN, abs(db - applied) < 0.1, !(envelope.done(at: time) && db != applied) { return }
        applied = db
        for (i, b) in beds.enumerated() {
            let gain = b.base + (i == nearBed ? c.look.audio.nearBoost : 0) + db
            if b.key == "windBed" {
                b.entity.components.set(AmbientAudioComponent(gain: Audio.Decibel(gain)))
            } else {
                b.entity.components.set(spatial(gain, c))
            }
        }
    }

    /// The bed emitter nearest the wearer carries `nearBoost`: the section you
    /// sit in is the loudest thing in the stadium.
    private func boostNearest(_ c: StadiumContext) {
        guard !c.tabletop, let seat = c.shared.seat else { return }
        let A = c.look.audio
        var best: (Int, Float)?
        for (i, b) in beds.enumerated() where b.key == "crowdBed" {
            let d = simd_distance(b.entity.position, seat)
            if best == nil || d < best!.1 { best = (i, d) }
        }
        let pick = best.flatMap { $0.1 <= Float(A.nearYards) ? $0.0 : nil }
        guard pick != nearBed else { return }
        nearBed = pick
        applied = .nan                            // re-apply every bed with the new boost
    }

    // MARK: the game

    func apply(_ c: StadiumContext, previous: SceneSpec?) {
        // A soft whistle as each newly drawn play lands, after its flight.
        let A = c.look.audio
        guard A.playWhistle.every > 0, let i = c.spec.currentDrive, i < c.spec.drives.count,
              let arc = c.spec.drives[i].arcs.last, arc.id != lastArc else { return }
        let first = lastArc == nil
        lastArc = arc.id
        guard !first else { return }
        landed += 1
        guard landed % A.playWhistle.every == 0 else { return }
        let at = SceneMath.local(x: arc.toX, y: 1, z: arc.lane)
        schedule(c.shared.time + arc.duration + A.playWhistle.afterFlight) { [weak self, c] in
            self?.play("whistle", at: at, extra: A.playWhistle.gain - (A.gains["whistle"] ?? 0), c)
        }
    }

    func moment(_ event: StadiumEvent, _ c: StadiumContext) {
        switch event {
        case .redZoneEntered:
            redZoneAt = c.shared.time
            cue(treatment: "redZone", side: c.spec.status.possession, id: nil, c)
        case .moment(let m):
            choreograph(m, c)
        case .cue(let q):
            cue(treatment: q.treatment, side: q.side, id: q.id, c)
        }
    }

    private func choreograph(_ m: SceneSpec.Moment, _ c: StadiumContext) {
        guard let T = c.look.moments.timeline[m.kind] else { return }
        let now = c.shared.time
        let swell = c.reduceMotion ? c.look.moments.reduceMotion.swellDb : 0
        let field = SceneMath.local(x: m.anchorX, y: 2, z: 0)
        let scorers = section(m.side, c)
        let other = section(m.side == "home" ? "away" : "home", c)

        if T.whistle >= 0 {
            schedule(now + T.whistle) { [weak self, c] in self?.play("whistle", at: field, c) }
        }
        if T.surge >= 0 {
            schedule(now + T.surge) { [weak self, c] in
                guard let self else { return }
                switch m.kind {
                case "touchdown": self.play("roar", at: scorers, extra: swell, c)
                case "turnover":
                    self.play("sting", at: scorers, extra: swell, c)
                    self.play("groan", at: other, c)
                default: self.play("cheer", at: scorers, extra: swell, c)
                }
            }
        }
        if T.particles >= 0, let burst = c.look.moments.burstFor[m.kind], burst != "none" {
            let rim = SceneMath.local(x: m.anchorX, y: 30, z: 0)
            schedule(now + T.particles) { [weak self, c] in
                self?.play("fireworks", at: rim, extra: c.reduceMotion ? -40 : 0, c)
            }
        }
        if T.chime >= 0 {
            schedule(now + T.chime) { [weak self, c] in self?.play("chime", at: c.shared.pressBox, c) }
        }
    }

    /// A cue's sound, from where it belongs: the PA's from the press box, a
    /// crowd's from the side it concerns. `id` dedupes a held cue.
    func cue(treatment: String, side: String?, id: String?, _ c: StadiumContext) {
        if let id {
            guard id != lastCue else { return }
            lastCue = id
        }
        if treatment == "redZone", id != nil, c.shared.time - redZoneAt < 8 { return }
        guard let T = c.look.moments.cues[treatment], T.audio != "none" else { return }
        let pa = ["chime", "horn"].contains(T.audio)
        let at = pa ? c.shared.pressBox : section(side ?? "home", c)
        play(T.audio, at: at, c)
    }

    // MARK: playing

    private func play(_ key: String, at position: SIMD3<Float>, extra: Double = 0, _ c: StadiumContext) {
        let A = c.look.audio
        guard !c.shared.muted, !pausedByLeave, !(c.tabletop && !A.tabletop.effects),
              let sound = c.assets.audio["audio.\(key)"] else { return }
        // One-shots share the source budget with the beds; a whistle or a
        // chime is the first thing dropped when the stadium is already loud.
        guard beds.count + active < A.maxSources else { return }
        let e = Entity()
        e.position = position
        e.components.set(spatial(level(key, c) + extra + envelope.value(at: c.shared.time), c))
        root.addChild(e)
        active += 1
        let controller = e.playAudio(sound)
        controller.completionHandler = { [weak self, weak e] in
            e?.removeFromParent()
            self?.active -= 1
        }
    }

    private func level(_ key: String, _ c: StadiumContext) -> Double {
        let A = c.look.audio
        return (A.gains[key] ?? -12) + A.masterGain + (c.tabletop ? A.tabletop.gain : 0)
    }

    private func spatial(_ gain: Double, _ c: StadiumContext) -> SpatialAudioComponent {
        let A = c.look.audio
        return SpatialAudioComponent(gain: Audio.Decibel(gain), reverbLevel: Audio.Decibel(A.reverbLevel),
                                     directivity: .beam(focus: 0),
                                     distanceAttenuation: .rolloff(factor: c.tabletop ? A.tabletop.rolloff : A.rolloff))
    }

    /// Where a side's fans sit: the visitors in their section (the scene's
    /// `awaySection`), the home crowd across the far stands from the 50.
    private func section(_ side: String?, _ c: StadiumContext) -> SIMD3<Float> {
        guard let tier = c.tiers.first else { return .zero }
        let m = (tier.inner + tier.outer) / 2
        let away = c.spec.bowl.crowd.awaySection
        // Local x is field x - 50; "far" is the stands across from the home
        // sideline, z < 0. The visitors sit where the scene says; the home
        // crowd's voice comes from across the field at midfield.
        let wantX = side == "away" ? (away?.fromX ?? 90) + 5 - 50 : 0
        let wantFar = side == "away" ? (away?.side ?? "far") == "far" : true
        var best = (x: 0.0, z: 0.0)
        var bestErr = Double.infinity
        for k in 0..<360 {
            let p = SceneMath.bowlPoint(c.spec.bowl.shape, offset: m, angle: Double(k) / 360 * 2 * .pi)
            guard (p.z < 0) == wantFar else { continue }
            let err = abs(p.x - wantX)
            if err < bestErr { bestErr = err; best = p }
        }
        return SIMD3(Float(best.x), Float(SceneMath.tierHeight(tier, offset: m)), Float(best.z))
    }

    private func schedule(_ at: Double, _ run: @escaping @MainActor () -> Void) {
        steps.append((at, run))
    }

    private static func reverbPreset(_ name: String) -> Reverb.Preset {
        switch name {
        case "concertHall": return .concertHall
        case "veryLargeRoom": return .veryLargeRoom
        case "largeRoom": return .largeRoom
        case "mediumRoomDry": return .mediumRoomDry
        case "smallRoom": return .smallRoom
        default: return .outside
        }
    }
}
