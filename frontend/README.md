# Crisees frontend

Next.js 15 (App Router) + TypeScript + Tailwind CSS v4. Phase 1 contains the application shell, the API
client (`src/lib/api.ts`), a live backend status indicator, a map-ready workspace and a data status page.

```bash
npm install
npm run dev          # http://localhost:3000, expects the API at NEXT_PUBLIC_API_BASE_URL
npm run typecheck
npm run lint
npm run build
```

See the repository [README](../README.md) and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
