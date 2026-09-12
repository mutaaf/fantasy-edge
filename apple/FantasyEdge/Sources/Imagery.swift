import CoreGraphics
import Foundation

/// Asking ESPN for a picture at the size it is actually going to be drawn.
///
/// Every headshot and club mark on this surface arrives from the read API as a
/// bare path - `/i/headshots/nfl/players/full/<id>.png`, which is one fixed
/// 600x436 file, and `/i/teamlogos/nfl/500/<abbr>.png`, which is one fixed
/// 500x500. One file for every use is wrong in both directions at once:
///
///   * A 28pt avatar in a table of hundreds pulled the whole 241 KB, 600 pixel
///     portrait to fill eighty-four pixels of screen. Two hundred rows was
///     forty megabytes of PNG for a column of thumbnails.
///   * The hologram draws the same man 260pt wide. At the 2.0 display scale
///     this app actually renders at (measured, not assumed) that is 520
///     device pixels off a 600 pixel source, with nothing spare - and a
///     headset resolves far more angular detail than the simulator does, so on
///     the device it is an upscale.
///
/// ESPN's combiner resamples from a larger original, so `&w=` is real detail
/// rather than interpolation - verified against the live endpoint: w=768
/// returns 768x558, w=1024 returns 1024x744, alpha channel intact in both, and
/// the aspect ratio is the same 600:436 the bare path has. `live.py` learned
/// the same trick server-side; this is the client half, because only the
/// client knows how big it is about to draw the thing.
enum Art {

    /// ESPN's cut-out portraits are all this shape. It matters because a
    /// circular avatar uses `scaledToFill`, which covers the circle by its
    /// *height* - so the width actually rasterised is this much wider than the
    /// circle's diameter, and asking for the diameter would under-request by
    /// nearly 40%.
    static let headshotAspect: CGFloat = 600.0 / 436.0

    /// Three device pixels per point.
    ///
    /// The window renders at a display scale of 2.0, so 2x is parity and 3x
    /// leaves half a pixel of headroom in each axis for the resampling the
    /// compositor does when a window is placed in the room at an angle - and
    /// for a real headset, which does not hold the scale at 2.0 the way the
    /// simulator does. Above that the bytes stop buying anything a wearer can
    /// see.
    static let oversample: CGFloat = 3

    /// Requested widths are rounded up to a multiple of this.
    ///
    /// Not a nicety: the URL is the cache key in `URLSession`'s shared cache
    /// and in ESPN's CDN, so a table that asks for 84, 86 and 90 pixels is
    /// three cache misses for one picture. Rounding to a coarse grid means the
    /// whole app converges on about six distinct widths.
    private static let grid: CGFloat = 32
    private static let smallest: CGFloat = 64
    /// Past this the file is bigger than any surface here draws. The largest
    /// is the hologram's head at 260pt, which lands at 800.
    private static let largest: CGFloat = 1024

    /// The width to ask for, given how many points wide the image will be
    /// drawn. Exposed so a caller can report it, and so the tests of this
    /// arithmetic do not have to parse a URL.
    static func width(forPoints points: CGFloat) -> Int {
        let want = max(smallest, points * oversample)
        let stepped = (want / grid).rounded(.up) * grid
        return Int(min(largest, stepped))
    }

    /// Any ESPN image URL, re-asked for at a size.
    ///
    /// Anything that is not an `a.espncdn.com` raster passes through
    /// unchanged. That is deliberate rather than lazy: a good part of ESPN's
    /// fantasy-team badges are SVG, the combiner will not resample one, and
    /// silently rewriting a URL that then 404s would replace a drawable badge
    /// with a blank circle. `Models.swift` already filters those out by the
    /// server's `logoRaster` flag; this is the second net under it.
    static func at(_ url: String?, points: CGFloat) -> URL? {
        guard let raw = url, !raw.isEmpty else { return nil }
        guard let c = URLComponents(string: raw), let host = c.host,
              host.hasSuffix("espncdn.com"), c.path.hasPrefix("/i/"),
              isRaster(c.path)
        else { return URL(string: raw) }
        // Already a combiner request - leave whatever width it carries alone
        // rather than fighting the caller that built it.
        guard !c.path.hasPrefix("/combiner/") else { return URL(string: raw) }
        var out = URLComponents()
        out.scheme = "https"
        out.host = "a.espncdn.com"
        out.path = "/combiner/i"
        out.queryItems = [URLQueryItem(name: "img", value: c.path),
                          URLQueryItem(name: "w", value: String(width(forPoints: points)))]
        return out.url ?? URL(string: raw)
    }

    /// A portrait drawn inside a circle by `scaledToFill`, where the diameter
    /// is not the width being rasterised. See `headshotAspect`.
    static func avatar(_ url: String?, diameter: CGFloat) -> URL? {
        at(url, points: diameter * headshotAspect)
    }

    /// A portrait for a player id, when the caller has an id and no URL.
    ///
    /// Three panels were building this path inline, which meant three places
    /// that would have had to learn about the combiner separately. A negative
    /// id is a team defence and has no portrait - see CLAUDE.md - so it gets
    /// nothing rather than a 404, and the caller's initials fallback stands.
    static func headshot(id: String, points: CGFloat) -> URL? {
        guard !id.isEmpty, !id.hasPrefix("-") else { return nil }
        return at("https://a.espncdn.com/i/headshots/nfl/players/full/\(id).png",
                  points: points)
    }

    /// An NFL club's mark, from the abbreviation the payload carries.
    static func club(_ abbr: String, points: CGFloat) -> URL? {
        let a = abbr.lowercased()
        guard !a.isEmpty, a != "fa" else { return nil }
        return at("https://a.espncdn.com/i/teamlogos/nfl/500/\(a).png", points: points)
    }

    private static func isRaster(_ path: String) -> Bool {
        let p = path.lowercased()
        return p.hasSuffix(".png") || p.hasSuffix(".jpg") || p.hasSuffix(".jpeg")
    }
}
