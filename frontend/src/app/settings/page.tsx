"use client";

import { useEffect, useState } from "react";
import { Moon, Settings as SettingsIcon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

export default function SettingsPage() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-3">
          <span className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center">
            <SettingsIcon size={18} className="text-blue-600" />
          </span>
          Settings
        </h1>
        <p className="text-slate-500 mt-1.5 text-sm">Manage your workspace preferences.</p>
      </div>

      <section className="bg-white border border-slate-200 rounded-2xl p-6 space-y-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">Appearance</h2>
          <p className="text-xs text-slate-500 mt-1">Choose how NexMarket looks on this device.</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => setTheme("light")}
            disabled={!mounted}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border text-sm font-medium transition-colors ${
              mounted && resolvedTheme === "light"
                ? "border-blue-500 bg-blue-50 text-blue-700"
                : "border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}
          >
            <Sun size={15} /> Light
          </button>
          <button
            type="button"
            onClick={() => setTheme("dark")}
            disabled={!mounted}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border text-sm font-medium transition-colors ${
              mounted && resolvedTheme === "dark"
                ? "border-blue-500 bg-blue-50 text-blue-700"
                : "border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}
          >
            <Moon size={15} /> Dark
          </button>
        </div>
      </section>
    </div>
  );
}
