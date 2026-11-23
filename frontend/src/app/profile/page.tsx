"use client";

import { useEffect, useState } from "react";
import { UserRound } from "lucide-react";

type ProfileDetails = { name: string; role: string };

const DEFAULT_PROFILE: ProfileDetails = { name: "Revanth", role: "Student" };

export default function ProfilePage() {
  const [profile, setProfile] = useState(DEFAULT_PROFILE);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem("nexmarket-profile");
      if (stored) setProfile({ ...DEFAULT_PROFILE, ...JSON.parse(stored) });
    } catch {
      window.localStorage.removeItem("nexmarket-profile");
    }
  }, []);

  function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextProfile = {
      name: profile.name.trim(),
      role: profile.role.trim(),
    };
    window.localStorage.setItem("nexmarket-profile", JSON.stringify(nextProfile));
    setProfile(nextProfile);
    setSaved(true);
    window.dispatchEvent(new Event("nexmarket-profile-updated"));
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-3">
          <span className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center">
            <UserRound size={18} className="text-blue-600" />
          </span>
          Profile
        </h1>
        <p className="text-slate-500 mt-1.5 text-sm">Manage your account details.</p>
      </div>

      <form onSubmit={saveProfile} className="bg-white border border-slate-200 rounded-xl p-6 space-y-5">
        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-slate-700">Name</span>
          <input
            required
            value={profile.name}
            onChange={(event) => { setProfile({ ...profile, name: event.target.value }); setSaved(false); }}
            className="w-full max-w-md rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
        </label>
        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-slate-700">Role</span>
          <input
            value={profile.role}
            onChange={(event) => { setProfile({ ...profile, role: event.target.value }); setSaved(false); }}
            className="w-full max-w-md rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
        </label>
        <div className="flex items-center gap-3">
          <button type="submit" className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">
            Save profile
          </button>
          {saved && <span role="status" className="text-sm text-emerald-700">Profile saved</span>}
        </div>
      </form>
    </div>
  );
}