"use client";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { api, type Chain, type Health, type Readiness } from "@/lib/api";
import { KpiCard } from "@/components/kpi-card";

type State = {
  loading: boolean;
  error: string | null;
  health?: Health;
  ready?: Readiness;
  chains: Chain[];
};

export default function Overview() {
  const [s, setS] = useState<State>({ loading: true, error: null, chains: [] });

  useEffect(() => {
    Promise.all([
      api<Health>("/health"),
      api<Readiness>("/health/ready", [503]),
      api<Chain[]>("/chains"),
    ])
      .then(([health, ready, chains]) => setS({ loading: false, error: null, health, ready, chains }))
      .catch((e: Error) => setS({ loading: false, error: e.message, chains: [] }));
  }, []);

  const live = s.chains.filter((c) => c.status === "live").length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="text-sm text-muted">
          Metrics appear once blockchain data is ingested. Nothing on this page is simulated.
        </p>
      </div>

      {s.error && (
        <div className="rounded-lg border border-loss/40 bg-loss/10 p-4 text-sm text-loss">
          Cannot reach the backend API: {s.error}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Tracked wallets" value="0" hint="Wallet management arrives in Phase 2" loading={s.loading} />
        <KpiCard label="Active blockchains" value={`${live} / ${s.chains.length}`} hint="Chains with a live adapter" loading={s.loading} />
        <KpiCard label="Large tx volume (24h)" value="—" hint="No ingested data yet" loading={s.loading} />
        <KpiCard label="Whale alerts" value="—" hint="No ingested data yet" loading={s.loading} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="rounded-lg border border-line bg-panel p-4">
          <h2 className="mb-3 text-sm font-medium">System status</h2>
          {s.loading ? (
            <div className="space-y-2"><div className="skeleton h-4 w-full" /><div className="skeleton h-4 w-2/3" /></div>
          ) : (
            <ul className="space-y-2 text-sm">
              <Row name="API" ok={s.health?.status === "ok"} />
              {Object.entries(s.ready?.checks ?? {}).map(([k, v]) => (
                <Row key={k} name={k} ok={v === "ok"} />
              ))}
            </ul>
          )}
          {s.health && <p className="mt-3 text-xs text-muted">v{s.health.version} · {s.health.environment}</p>}
        </section>

        <section className="rounded-lg border border-line bg-panel p-4 lg:col-span-2">
          <h2 className="mb-3 text-sm font-medium">Network registry</h2>
          {s.loading ? (
            <div className="skeleton h-32 w-full" />
          ) : s.chains.length === 0 ? (
            <p className="text-sm text-muted">No networks available.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-muted">
                  <tr><th className="py-1.5">Network</th><th>Type</th><th>Native</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {s.chains.map((c) => (
                    <tr key={c.id} className="border-t border-line">
                      <td className="py-1.5">{c.name}</td>
                      <td className="uppercase text-muted">{c.family}</td>
                      <td>{c.native_symbol}</td>
                      <td className="text-muted">{c.status === "live" ? "Live" : `Planned · Phase ${c.planned_phase}`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Row({ name, ok }: { name: string; ok: boolean }) {
  return (
    <li className="flex items-center justify-between capitalize">
      {name}
      <span className={clsx("flex items-center gap-1.5 text-xs", ok ? "text-gain" : "text-loss")}>
        <span className={clsx("h-2 w-2 rounded-full", ok ? "bg-gain" : "bg-loss")} />
        {ok ? "healthy" : "unavailable"}
      </span>
    </li>
  );
}
