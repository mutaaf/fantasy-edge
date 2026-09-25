import Foundation

/// What the viewer has seen land, in one place.
///
/// The stadium's rule is that nothing gets ahead of the ball: the score, the
/// ribbon, the video board and the drive log all describe plays the viewer has
/// watched finish. Broadcast answers "has this play landed?" from its trails;
/// the composer answers it from `StatusGate`, which holds the scene's status
/// behind the same landing. Both ask here, so the rule has one implementation,
/// and it lives in a file that imports nothing but Foundation so the sweeps can
/// compile it - `BroadcastVideoBoard` imports UIKit and cannot be swept.
public enum LaidPlay {
    /// The newest play of this drive the viewer has seen land, or nil while the
    /// first play of a drive is still in the air.
    public static func newest(_ drive: SceneSpec.Drive?, laid: (String) -> Bool) -> SceneSpec.Arc? {
        (drive?.arcs ?? []).last(where: { laid($0.id) })
    }

    /// The drive as it may be listed while `held` is still in the air: that play
    /// and every play after it are dropped, and the drive's result with them -
    /// a header reading "Touchdown" over a ball still in flight is the same
    /// defect as a score that moves early.
    ///
    /// `held` nil means nothing is being held, so the drive is listed whole: a
    /// scrub, a seat change, reduce motion and a drive laid at rest all fly
    /// nothing and hold nothing.
    public static func through(_ drive: SceneSpec.Drive?, held: String?) -> SceneSpec.Drive? {
        guard let drive else { return nil }
        guard let held, let cut = drive.arcs.firstIndex(where: { $0.id == held }) else { return drive }
        return SceneSpec.Drive(id: drive.id, team: drive.team, side: drive.side,
                               result: "", arcs: Array(drive.arcs.prefix(cut)))
    }
}
