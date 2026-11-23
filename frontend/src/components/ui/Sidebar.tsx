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
  Users,
  Zap,
  Plus,
  Settings,
  Type,
  ChevronRight,
  Moon,
  Sun,
} from "lucide-react";
import { clsx } from "clsx";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

type ProfileDetails = { name: string; role: string };

const NAV_GROUPS = [
  {
    title: "MAIN",
    items: [
      { href: "/",             label: "Dashboard",       icon: LayoutDashboard },
      { href: "/campaign",     label: "Campaigns",       icon: Megaphone },
      { href: "/campaign/new", label: "Create Campaign", icon: Plus },
    ]
  },
  {
    title: "AI",
    items: [
      { href: "/poster",       label: "Poster Gallery",  icon: ImageIcon },
      { href: "/adcopy",       label: "Ad Copy",         icon: Type },
      { href: "/leads",        label: "Leads & Sentiment", icon: Users },
    ]
  },
  {
    title: "ANALYTICS",
    items: [
      { href: "/analytics",    label: "Analytics",       icon: BarChart3 },
      { href: "/optimization", label: "Optimization",    icon: Target },
    ]
  },
  {
    title: "OPERATIONS",
    items: [
      { href: "/posting",      label: "Social Media",    icon: Send },
    ]
  },
  {
    title: "SETTINGS",
    items: [
      { href: "/settings",     label: "Settings",        icon: Settings },
    ]
  }
];

export function Sidebar() {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [profile, setProfile] = useState<ProfileDetails>({ name: "Revanth", role: "Student" });

  useEffect(() => {
    setMounted(true);
    const loadProfile = () => {
      try {
        const saved = window.localStorage.getItem("nexmarket-profile");
        if (saved) setProfile(JSON.parse(saved) as ProfileDetails);
      } catch {
        window.localStorage.removeItem("nexmarket-profile");
      }
    };
    loadProfile();
    window.addEventListener("nexmarket-profile-updated", loadProfile);
    return () => window.removeEventListener("nexmarket-profile-updated", loadProfile);
  }, []);

  return (
    <aside className="w-60 flex-shrink-0 flex flex-col bg-slate-900 border-r border-slate-800">
      {/* Logo & Theme Toggle */}
      <div className="px-5 py-5 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-brand-gradient flex items-center justify-center shadow-brand">
            <Zap size={15} className="text-white" />
          </div>
          <div>
            <p className="font-bold text-white text-sm leading-none tracking-tight">NexMarket</p>
            <p className="text-[11px] text-blue-400 mt-0.5 font-medium">AI Platform</p>
          </div>
        </div>
        {mounted && (
          <button
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-white transition-colors border border-slate-700"
            title="Toggle theme"
          >
            {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
          </button>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-6 overflow-y-auto">
        {NAV_GROUPS.map((group) => (
          <div key={group.title}>
            <p className="px-3 mb-2 text-xs font-semibold text-slate-500 tracking-wider">
              {group.title}
            </p>
            <div className="space-y-0.5">
              {group.items.map(({ href, label, icon: Icon }) => {
                const active = href !== "#" && (href === "/" ? pathname === "/" : pathname.startsWith(href));
                return (
                  <Link
                    key={label}
                    href={href}
                    prefetch={true}
                    className={clsx(
                      "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150 nav-item",
                      active
                        ? "bg-blue-600 text-white font-semibold border-l-[3px] border-white pl-[9px]"
                        : "text-slate-400 font-medium hover:bg-slate-800 hover:text-slate-200"
                    )}
                  >
                    <Icon
                      size={16}
                      className={clsx(
                        "flex-shrink-0",
                        active ? "text-white" : "text-slate-400"
                      )}
                    />
                    {label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer — User Profile */}
      <div className="px-3 py-4 border-t border-slate-800">
        <Link href="/profile" className="flex items-center justify-between p-2 hover:bg-slate-800 rounded-lg transition-colors group">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center overflow-hidden flex-shrink-0">
              <Users size={16} className="text-slate-400" />
            </div>
            <div>
              <p className="text-sm font-semibold text-white leading-none mb-1">{profile.name}</p>
              <p className="text-[10px] text-slate-400 leading-none">{profile.role}</p>
            </div>
          </div>
          <ChevronRight size={16} className="text-slate-500 group-hover:text-slate-300 transition-colors" />
        </Link>
      </div>
    </aside>
  );
}
