/** Thin fetch layer over the §12 contract. Every call returns the envelope, because the
 *  assumption block that travels with a payload is part of the payload's meaning (§10.14). */
import type { Envelope, Problem } from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  problem: Problem;
  constructor(p: Problem) {
    super(p.detail || p.title);
    this.problem = p;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<Envelope<T>> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!r.ok) {
    let p: Problem;
    try {
      p = await r.json();
    } catch {
      p = { type: "/errors/unknown", title: r.statusText, status: r.status, detail: await r.text(), instance: path };
    }
    // §13.10: a 422 for missing covariance is information, not a crash — the caller renders "—".
    throw new ApiError(p);
  }
  return r.json();
}

export const api = {
  get: <T>(path: string, params?: Record<string, unknown>) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params ?? {})) {
      if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
    }
    const qs = q.toString();
    return request<T>(path + (qs ? `?${qs}` : ""));
  },
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
};
