// How the ball travels each new play, in order. A port of PlayMotion in
// SceneMath.swift: plays that arrive together queue, each flies for the
// duration the scene gave it, a backlog halves what is left, and reduce
// motion lands the ball instead of flying it. The first drive a client sees
// is history and does not animate.

import type { Arc, Drive } from "./spec.ts";

export class PlayMotion {
  queue: Arc[] = [];
  seen = new Set<string>();

  arrive(drive: Drive | null, initial: boolean): Arc[] {
    if (!drive) return [];
    const fresh = drive.arcs.filter((a) => !this.seen.has(a.id));
    for (const a of drive.arcs) this.seen.add(a.id);
    if (initial) return [];
    this.queue.push(...fresh);
    return fresh;
  }

  reset(): void {
    this.queue = [];
    this.seen.clear();
  }

  next(reduceMotion: boolean, floor: number): { arc: Arc; seconds: number } | null {
    const arc = this.queue.shift();
    if (!arc) return null;
    if (reduceMotion) return { arc, seconds: 0 };
    const squeeze = this.queue.length > 3 ? 0.5 : 1;
    return { arc, seconds: Math.max(floor, arc.duration * squeeze) };
  }
}
