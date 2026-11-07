# Spill the Market UI

React / TypeScript / Vite. This is an Operate interface for the local Python service. All simulation results come from the real `/api/v1` API; the browser contains no fake metrics or provider secrets.

```powershell
npm ci
npm run dev
npm run test
npm run build
```

Development proxies `/api` to `http://127.0.0.1:8765`. Production builds directly into `../src/spill_market/web`, which Python serves and packages. Node is needed only to work on the frontend, not to run the installed application.

The local session token is obtained from bootstrap and held in memory for write requests. Only the language preference is persisted in browser storage. Research, experiment, plan and run state belong to the local service. Online research is an explicit action with a separately saved real API cost cap. Documents and fictional demos work offline.

Design decisions: [DESIGN.md](DESIGN.md). Product scope: [PRODUCT.md](PRODUCT.md). Backend contracts: [../docs/INTERFACES.md](../docs/INTERFACES.md).
