"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Megaphone,
  Image as ImageIcon,
  Send,
  BarChart3,
  Target,
  TrendingUp,
  Users,
  Zap,
  ChevronRight,
} from "lucide-react";
import { clsx } from "clsx";

const NAV = [
  { href: "/",              label: "Dashboard",    icon: LayoutDashboard },
  { href: "/campaign/new",  label: "New Campaign", icon: Megaphone },
  { href: "/campaign",      label: "Campaigns",    icon: Zap },
  { href: "/poster",        label: "Posters",      icon: ImageIcon },
  { href: "/posting",       label: "Posting",      icon: Send },
  { href: "/analytics",     label: "Analytics",    icon: BarChart3 },
  { href: "/optimization",  label: "Optimize",     icon: Target },
  { href: "/leads",         label: "Lead Scores",  icon: Users },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 flex-shrink-0 flex flex-col border-r border-surface-border bg-surface-card">
      {/* Logo */}
      <div className="p-6 border-b border-surface-border">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-brand-gradient flex items-center justify-center shadow-brand">
            <Zap size={18} className="text-white" />
          </div>
          <div>
            <p className="font-bold text-white text-sm leading-none">NexMarket</p>
            <p className="text-xs text-brand-400 mt-0.5">AI Platform</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-3 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 group",
                active
                  ? "bg-brand-500/20 text-brand-300 border border-brand-500/30"
                  : "text-slate-400 hover:text-slate-200 hover:bg-surface-muted"
              )}
            >
              <Icon
                size={16}
                className={clsx(
                  "flex-shrink-0 transition-colors",
                  active ? "text-brand-400" : "text-slate-500 group-hover:text-slate-300"
                )}
              />
              {label}
              {active && (
                <ChevronRight size={12} className="ml-auto text-brand-400" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-surface-border">
        <div className="glass rounded-lg p-3">
          <p className="text-xs text-slate-400 font-medium">Demo Mode</p>
          <p className="text-xs text-slate-500 mt-0.5">Mock posting active</p>
          <div className="mt-2 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs text-emerald-400">All systems healthy</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
