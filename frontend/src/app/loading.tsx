export default function Loading() {
  return (
    <div className="space-y-6 animate-pulse" role="status" aria-label="Loading page">
      <div className="h-8 w-56 rounded bg-slate-200" />
      <div className="h-4 w-80 max-w-full rounded bg-slate-200" />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="h-64 rounded-xl border border-slate-200 bg-white" />
        <div className="h-64 rounded-xl border border-slate-200 bg-white" />
      </div>
    </div>
  );
}