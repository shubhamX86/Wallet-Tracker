"use client";
import { useState } from "react";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { Menu, X, Waves } from "lucide-react";
import { NAV } from "./nav";

export function Sidebar() {
  const [open, setOpen] = useState(false);
  const path = usePathname();
  return (
    <>
      <button
        aria-label="Toggle navigation"
        className="fixed left-3 top-3 z-40 rounded-md border border-line bg-panel p-2 md:hidden"
        onClick={() => setOpen(!open)}
      >
        {open ? <X size={18} /> : <Menu size={18} />}
      </button>
      <aside
        className={clsx(
          "fixed inset-y-0 left-0 z-30 w-60 shrink-0 border-r border-line bg-panel transition-transform md:static md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-14 items-center gap-2 border-b border-line px-5 pl-14 md:pl-5">
          <Waves className="text-teal" size={20} />
          <span className="font-semibold tracking-wide">Whale Tracker</span>
        </div>
        <nav className="space-y-0.5 p-3">
          {NAV.map(({ label, href, icon: Icon }) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <a
                key={href}
                href={href}
                onClick={() => setOpen(false)}
                className={clsx(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  active ? "bg-teal/15 text-teal" : "text-muted hover:bg-panel2 hover:text-white"
                )}
              >
                <Icon size={16} />
                {label}
              </a>
            );
          })}
        </nav>
      </aside>
    </>
  );
}
