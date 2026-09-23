import Foundation
import OSLog

#if canImport(Darwin)
import Darwin
#endif

/// What only a headset can answer: how fast the stadium actually runs, and how
/// much memory it actually holds.
///
/// `-stadiumStats` already counts draw parts and triangles, and
/// `[stadium-timing]` says where the seconds before the first frame go. Both
/// are honest in the simulator, because a triangle is a triangle and load
/// order is load order. Frame time is not: the simulator renders on a Mac's
/// GPU at whatever rate the window manager feels like, so a number taken there
/// says nothing about 90 fps on a Vision Pro. That is why this exists and why
/// every line it writes says which machine produced it - a device line and a
/// simulator line must never be mistaken for each other.
///
/// The budget is `docs/ART_BIBLE.md`'s: 90 fps in full immersion, so 11.1 ms a
/// frame. What matters for comfort is not the mean but the tail: one frame in
/// a hundred over budget is a visible hitch in a headset, where the same
/// number on a monitor would pass unnoticed. So the report carries the mean,
/// the 95th percentile, the worst frame and how many frames missed.
/// Not actor-isolated: reading the clock, the frame list and the kernel's
/// memory counter touches nothing shared, and `Window` has to do all three
/// from wherever it is called. Only `Sampler` and `announce` are isolated,
/// because they are the parts the renderer drives from the main actor.
enum StadiumDeviceStats {
    /// True when this build is running in a simulator rather than on a headset.
    /// Compiled in, not sniffed at runtime, so it cannot be wrong.
    static let simulated: Bool = {
        #if targetEnvironment(simulator)
        return true
        #else
        return false
        #endif
    }()

    static var machine: String { simulated ? "simulator" : "device" }

    /// 90 fps in full immersion (docs/ART_BIBLE.md).
    static let budgetHz = 90.0
    static var budgetMs: Double { 1000.0 / budgetHz }

    /// Physical footprint in bytes, which is what the system kills an app for,
    /// not `resident_size`. Returns nil if the kernel will not say.
    static func footprintBytes() -> UInt64? {
        #if canImport(Darwin)
        var info = task_vm_info_data_t()
        var count = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<natural_t>.size)
        let kr = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
            }
        }
        guard kr == KERN_SUCCESS else { return nil }
        return UInt64(info.phys_footprint)
        #else
        return nil
        #endif
    }

    /// A window of frame intervals, reported when it fills.
    struct Window {
        let label: String
        private(set) var frames: [Double] = []
        private var peakFootprint: UInt64 = 0
        private let want: Int

        init(label: String, frames want: Int = 300) {
            self.label = label
            self.want = want
            frames.reserveCapacity(want)
        }

        var isFull: Bool { frames.count >= want }

        /// One frame, measured in milliseconds of wall clock between ticks.
        /// Wall clock rather than the `dt` RealityKit hands us: `dt` is what
        /// the engine intends the frame to be worth, and the question here is
        /// what the frame actually cost.
        mutating func add(_ ms: Double) {
            frames.append(ms)
            if let f = StadiumDeviceStats.footprintBytes() { peakFootprint = max(peakFootprint, f) }
        }

        /// The report line. Sorted copy, so the caller's order is untouched.
        func line() -> String {
            guard !frames.isEmpty else { return "" }
            let sorted = frames.sorted()
            let mean = frames.reduce(0, +) / Double(frames.count)
            let p95 = sorted[min(sorted.count - 1, Int(Double(sorted.count) * 0.95))]
            let worst = sorted[sorted.count - 1]
            let budget = StadiumDeviceStats.budgetMs
            let missed = frames.filter { $0 > budget }.count
            let fps = mean > 0 ? 1000.0 / mean : 0
            let mb = peakFootprint / 1_048_576
            return String(
                format: "[stadium-device] %@ %@: %.1f fps mean (%.2f ms), p95 %.2f ms, worst %.2f ms, "
                    + "%d of %d frames over %.1f ms, peak footprint %llu MB",
                label, StadiumDeviceStats.machine, fps, mean, p95, worst,
                missed, frames.count, budget, mb)
        }
    }

    /// Samples every frame, reports each time a window fills. Cheap enough to
    /// leave on: one clock read and an append per frame.
    @MainActor
    final class Sampler {
        private var window: Window
        private var last: ContinuousClock.Instant?
        private let label: String
        /// Frames to let settle after a build before believing anything. The
        /// first frames after the stadium is built are dominated by the build
        /// itself, and counting them would slander a stadium that then runs
        /// clean.
        private var warmup: Int

        init(label: String, warmup: Int = 60, frames: Int = 300) {
            self.label = label
            self.warmup = warmup
            self.window = Window(label: label, frames: frames)
        }

        /// Call once per tick. Returns a line to log when a window completes.
        func tick() -> String? {
            let now = ContinuousClock.now
            defer { last = now }
            guard let last else { return nil }
            if warmup > 0 { warmup -= 1; return nil }
            let d = now - last
            let ms = Double(d.components.seconds) * 1000
                + Double(d.components.attoseconds) / 1e15
            // A frame longer than a second is not a frame: the app was
            // backgrounded, or the space was closed and reopened. Counting it
            // would put a 3,000 ms "worst frame" in a report about comfort.
            guard ms < 1000 else { return nil }
            window.add(ms)
            guard window.isFull else { return nil }
            let line = window.line()
            window = Window(label: label, frames: window.frames.count)
            return line
        }
    }

    /// One line at launch saying what is measuring what, so a log read later
    /// cannot be misattributed.
    static func announce(_ label: String) {
        let mem = footprintBytes().map { "\($0 / 1_048_576) MB" } ?? "unknown"
        let line = "[stadium-device] \(label) running on \(machine), "
            + "budget \(String(format: "%.1f", budgetHz)) fps "
            + "(\(String(format: "%.2f", budgetMs)) ms), footprint at start \(mem)"
        StadiumLog.log.notice("\(line, privacy: .public)")
        if simulated {
            let warn = "[stadium-device] simulator frame times are the Mac's, not a headset's: "
                + "treat them as nothing. Run on a Vision Pro (docs/DEVICE.md)."
            StadiumLog.log.notice("\(warn, privacy: .public)")
        }
    }
}
