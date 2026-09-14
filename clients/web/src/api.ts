// The API, as this client uses it. Every route is the one the headset uses.

import type { ReplayControl } from "./spec.ts";

export interface CatalogGame {
  event: string;
  date?: string;
  home?: { abbr: string; score?: number };
  away?: { abbr: string; score?: number };
  final?: string;
  length?: number;
}

export type ReplayState = ReplayControl & { games?: CatalogGame[]; matchup?: { home?: { abbr: string }; away?: { abbr: string } } };

export class ApiError extends Error {
  status: number;
  fix?: string;
  constructor(status: number, message: string, fix?: string) {
    super(message);
    this.status = status;
    this.fix = fix;
  }
}

export class Api {
  base: string;
  constructor(base = "") { this.base = base.replace(/\/$/, ""); }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    let res: Response;
    try {
      res = await fetch(this.base + path, { cache: "no-store", ...init });
    } catch {
      throw new ApiError(0, "Cannot reach the API.", "python3 -m fantasyedge api --port 8793");
    }
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(res.status, body.error ?? `HTTP ${res.status}`, body.fix);
    return body as T;
  }

  replay(): Promise<ReplayState> { return this.request("/api/replay"); }
  replayScene(): Promise<unknown> { return this.request("/api/replay/scene"); }
  scene(event: string): Promise<unknown> { return this.request(`/api/scene/${encodeURIComponent(event)}`); }

  control(body: Record<string, unknown>): Promise<ReplayState> {
    return this.request("/api/replay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }
}
