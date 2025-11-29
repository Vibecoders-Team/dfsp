import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useMiniAuth } from "../auth";

const links = [
  { to: "/mini", label: "Home" },
  { to: "/mini/files", label: "Files" },
  { to: "/mini/grants", label: "Grants" },
  { to: "/mini/verify", label: "Verify" },
];

export function MiniLayout({ children }: { children: ReactNode }) {
  const { status, error, expSeconds } = useMiniAuth();

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      <header className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
        <div>
          <p className="text-sm uppercase text-slate-400">DFSP · Mini App</p>
          <p className="text-lg font-semibold">Telegram WebApp</p>
        </div>
        <div className="text-right">
          <p className="text-xs text-slate-400">Auth state: {status}</p>
          {expSeconds !== null && <p className="text-xs text-slate-500">JWT TTL: {expSeconds}s</p>}
          {error && <p className="text-xs text-red-400 max-w-xs text-right">{error}</p>}
        </div>
      </header>

      <nav className="flex gap-3 px-4 py-2 border-b border-slate-800 bg-slate-950/50 text-sm">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) =>
              `px-3 py-1 rounded-full transition ${
                isActive ? "bg-sky-500 text-slate-950" : "bg-slate-800 text-slate-100 hover:bg-slate-700"
              }`
            }
          >
            {link.label}
          </NavLink>
        ))}
      </nav>

      <main className="p-4">
        <Outlet />
        {children}
      </main>
    </div>
  );
}
