//  Leverage.swift
//  The same model as fantasyedge/leverage.py and the JavaScript in mosaic.html.
//
//  Ported rather than fetched, which is the whole point of keeping it to
//  arithmetic over plain numbers: no surface waits on a server to be told how
//  big to draw a cell. If this file and leverage.py ever disagree, one of them
//  is wrong - LeverageTests carries the same properties the Python suite does.

import Foundation

/// Full-game standard deviation of fantasy points, by position. Kickers are
/// nearly deterministic; skill positions are not.
enum Sigma {
    static let full: [String: Double] = [
        "QB": 7.0, "RB": 6.5, "WR": 7.0, "TE": 5.0, "K": 3.0, "DEF": 6.0,
    ]
    static let fallback = 6.0

    /// Variance accumulates like independent increments over game time, so a
    /// player with fraction `f` of his game left carries `sigmaFull * sqrt(f)`.
    static func remaining(pos: String, remaining f: Double) -> Double {
        let base = full[pos.uppercased()] ?? fallback
        return base * (max(0, min(1, f))).squareRoot()
    }
}

enum Band: String, CaseIterable {
    case xl, lg, md, sm
    var order: Int { Band.allCases.firstIndex(of: self)! }
}

struct Cell: Identifiable, Equatable, Hashable {
    let id: String
    var name: String
    var pos: String
    var team: String
    var side: String           // "you" | "opp"
    var scored: Double
    var projected: Double
    var remaining: Double      // fraction of his game still to play, 0...1
    var state: String
    /// Carried so a card can draw the man rather than a coloured rectangle.
    var img: String = ""

    // filled in by evaluate
    var sigma: Double = 0
    var leverage: Double = 0
    var share: Double = 0
    var band: Band = .sm
}

struct Mosaic {
    var winProb: Double
    var margin: Double
    var sigma: Double
    var intensity: Double
    var phase: String          // "pre" | "live" | "final"
    var yourScore: Double
    var oppScore: Double
    var yourProjected: Double
    var oppProjected: Double
    var cells: [Cell]
}

enum Leverage {
    private static func normalPDF(_ z: Double) -> Double {
        exp(-0.5 * z * z) / (2 * Double.pi).squareRoot()
    }

    private static func normalCDF(_ z: Double) -> Double {
        0.5 * erfc(-z / 2.0.squareRoot())
    }

    /// Cuts are multiples of an even split rather than absolute numbers,
    /// because the metric behind `share` changes with the phase of the week.
    /// Absolute cuts made every pre-game cell identical.
    static func band(share: Double, previous: Band?, even: Double,
                     hysteresis: Double = 0.15) -> Band {
        let cuts: [(Band, Double)] = [
            (.xl, even * 3.0), (.lg, even * 1.9), (.md, even * 1.05), (.sm, 0),
        ]
        var target = cuts.first { share >= $0.1 }?.0 ?? .sm
        if let prev = previous, prev != target {
            let table = Dictionary(uniqueKeysWithValues: cuts)
            if target.order < prev.order {                 // growing
                if share < (table[target] ?? 0) * (1 + hysteresis) { target = prev }
            } else {                                       // shrinking
                if share > (table[prev] ?? 0) * (1 - hysteresis) { target = prev }
            }
        }
        return target
    }

    /// leverage_i = phi(m/s) * sigma_i / s
    static func evaluate(_ input: [Cell], previous: [String: Band] = [:]) -> Mosaic {
        var cells = input
        var ys = 0.0, yr = 0.0, yv = 0.0, os = 0.0, orr = 0.0, ov = 0.0

        for i in cells.indices {
            cells[i].sigma = Sigma.remaining(pos: cells[i].pos,
                                             remaining: cells[i].remaining)
            let rest = max(0, cells[i].projected - cells[i].scored) * cells[i].remaining
            if cells[i].side == "you" {
                ys += cells[i].scored; yr += rest; yv += cells[i].sigma * cells[i].sigma
            } else {
                os += cells[i].scored; orr += rest; ov += cells[i].sigma * cells[i].sigma
            }
        }

        let margin = (ys + yr) - (os + orr)
        let s = (yv + ov).squareRoot()
        var winProb = 0.5, sensitivity = 0.0
        if s <= 1e-9 {
            winProb = margin > 0 ? 1 : (margin < 0 ? 0 : 0.5)
        } else {
            let z = margin / s
            winProb = normalCDF(z)
            sensitivity = normalPDF(z) / s
        }
        for i in cells.indices { cells[i].leverage = sensitivity * cells[i].sigma }

        // Which question the board can answer. Read the clock, not the
        // scoreboard: banked points do not make a week live, and an early
        // kickoff does not make it over.
        let phase: String
        if cells.allSatisfy({ $0.remaining >= 1 }) { phase = "pre" }
        else if cells.allSatisfy({ $0.remaining <= 0 }) { phase = "final" }
        else { phase = "live" }

        func basis(_ c: Cell) -> Double {
            switch phase {
            case "pre": return max(0, c.projected)
            case "final": return max(0, c.scored)
            default: return c.leverage
            }
        }
        let total = cells.reduce(0) { $0 + basis($1) }
        let even = 1.0 / Double(max(1, cells.count))
        for i in cells.indices {
            cells[i].share = total > 1e-12 ? basis(cells[i]) / total : 0
            cells[i].band = band(share: cells[i].share,
                                 previous: previous[cells[i].id], even: even)
        }
        cells.sort { ($0.share, $0.leverage, $1.id) > ($1.share, $1.leverage, $0.id) }

        return Mosaic(winProb: winProb, margin: margin, sigma: s,
                      intensity: 2 * min(winProb, 1 - winProb), phase: phase,
                      yourScore: ys, oppScore: os,
                      yourProjected: ys + yr, oppProjected: os + orr,
                      cells: cells)
    }
}
