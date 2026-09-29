import Link from "next/link";
import { FileQuestion, Home } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6 animate-fade-in">
      <div className="w-14 h-14 rounded-2xl bg-blue-50 border border-blue-200 flex items-center justify-center text-blue-600 mb-4 shadow-sm">
        <FileQuestion size={28} />
      </div>
      <h1 className="text-2xl font-bold text-slate-900 tracking-tight">404 — Page Not Found</h1>
      <p className="text-slate-500 text-sm max-w-md mt-2 leading-relaxed">
        The page you are looking for does not exist or may have been moved.
      </p>
      <Link
        href="/"
        className="btn-brand mt-6 px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2"
      >
        <Home size={15} />
        Return to Dashboard
      </Link>
    </div>
  );
}
