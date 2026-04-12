// Thin fetch wrapper. Centralises the /api/v1 prefix and normalises
// error handling — a non-2xx response throws, so React Query can put
// the query into `error` state instead of silently returning an error
// body as if it were data. Kept dependency-free on purpose; swapping
// the transport (e.g. to SSE/WebSocket later) only touches this file
// plus the hooks in queries.ts.

const BASE = '/api/v1';

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    super(`API ${status}`);
    this.status = status;
    this.body = body;
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new ApiError(res.status, await safeJson(res));
  return res.json() as Promise<T>;
}

export async function apiSend<T>(
  method: 'POST' | 'PUT' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, await safeJson(res));
  return res.json() as Promise<T>;
}

async function safeJson(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}
