export type Health = { status: string; app: string; version: string; environment: string };
export type Readiness = { status: string; checks: Record<string, string> };
export type Chain = {
  id: string;
  name: string;
  family: string;
  native_symbol: string;
  evm_chain_id: number | null;
  status: string;
  planned_phase: number;
};

/** Same-origin calls; Next rewrites (dev) or nginx (docker) proxy /api to the backend. */
export async function api<T>(path: string, allowStatuses: number[] = []): Promise<T> {
  const res = await fetch(`/api/v1${path}`, { cache: "no-store" });
  if (!res.ok && !allowStatuses.includes(res.status)) {
    throw new Error(`${path} failed: HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}
