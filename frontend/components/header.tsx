import { ShieldCheck } from "lucide-react";

export function Header() {
  return (
    <header className="flex h-14 items-center justify-between border-b border-line px-4 pl-14 md:px-6">
      <span className="text-sm text-muted">Read-only analytics · no keys, no seed phrases</span>
      <span className="flex items-center gap-1.5 text-xs text-teal">
        <ShieldCheck size={14} /> Non-custodial
      </span>
    </header>
  );
}
