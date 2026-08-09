# NexMarket AI Frontend — Performance Baseline

> Measured **before** any optimization changes.
> Next.js 14.2.5, Webpack (default), Node 20, Windows.

## Build Metrics (Baseline)

| Metric | Before |
|---|---|
| `npm run build` time | **68.5 s** |
| Build outcome | ❌ FAILED (TypeScript error) |
| TypeScript error | `onForecast: () => void` not assignable to `() => Promise<unknown>` |
| Shared JS chunk (first load) | Not measured (build failed) |

## Code Issues Found

| Issue | File | Severity |
|---|---|---|
| Entire dashboard is `"use client"` unnecessarily | `app/page.tsx` | 🔴 High |
| `Toaster` (client) imported in Server Component layout | `app/layout.tsx` | 🔴 High |
| 549-line monolith with 2 Recharts charts, all client | `app/campaign/[id]/page.tsx` | 🔴 High |
| `DEMO_CHART` uses `Math.random()` — unstable on every HMR | `app/page.tsx` | 🟡 Medium |
| `axios` installed but never used (native `fetch` used instead) | `package.json` | 🟡 Medium |
| `lucide-react` has no `optimizePackageImports` — full icon bundle | `next.config.js` | 🟡 Medium |
| `recharts` has no `optimizePackageImports` | `next.config.js` | 🟡 Medium |
| `tsconfig.json` includes `**/*.ts` — scans `.next` artifacts | `tsconfig.json` | 🟡 Medium |
| Google Fonts loaded via CSS `@import` (render-blocking) | `globals.css` | 🟡 Medium |
| Turbopack not enabled for dev | `package.json` | 🟡 Medium |
| No dynamic imports for Recharts (loaded on first bundle) | All chart pages | 🟡 Medium |
| `components/charts/`, `components/campaign/`, `components/posting/` all empty | `src/components/` | 🟢 Low |

## Client Component Count (Baseline)

| `"use client"` files | Count |
|---|---|
| `app/page.tsx` | ✗ unnecessary |
| `app/campaign/page.tsx` | ✓ needed |
| `app/campaign/new/page.tsx` | ✓ needed |
| `app/campaign/[id]/page.tsx` | ✓ needed (but monolith) |
| `components/ui/Sidebar.tsx` | ✓ needed |
| **Total** | **5** |
