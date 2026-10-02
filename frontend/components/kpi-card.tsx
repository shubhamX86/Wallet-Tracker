export function KpiCard({
  label, value, hint, loading,
}: { label: string; value: string; hint?: string; loading?: boolean }) {
  return (
    <div className="rounded-lg border border-line bg-panel p-4">
      <div className="text-xs uppercase tracking-wider text-muted">{label}</div>
      {loading ? (
        <div className="skeleton mt-3 h-7 w-24" />
      ) : (
        <div className="mt-2 text-2xl font-semibold text-white">{value}</div>
      )}
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}
