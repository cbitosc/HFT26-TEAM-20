# AutoEvolve Dashboard

A Vite + React + TypeScript dashboard for the AutoEvolve Protocol.

It talks to the FastAPI backend **over HTTP only**. It never touches the
database, the blockchain or IPFS directly, and it never renders hidden test
contents — hidden tests appear only as counts.

## Prerequisites

- Node.js 20+ (developed on Node 24, npm 11)
- The FastAPI backend running and reachable (see `../backend/README.md`)

## Configuration

The backend base URL is read at runtime from `VITE_API_BASE_URL`. Copy the
example file and adjust if needed:

```bash
cp .env.example .env
```

Default when unset: `http://localhost:8000`. The client appends `/api` itself.
The backend's CORS allowlist defaults to `http://localhost:5173`, which is the
Vite dev server port configured here.

## Commands

```bash
npm install      # install dependencies
npm run dev      # start the dev server on http://localhost:5173
npm test         # run the component and API-client tests once (vitest run)
npm run lint     # eslint (flat config)
npm run build    # type-check (tsc -b) and produce a production build
```

`npm run test:watch` runs Vitest in watch mode.

### Running against a live backend

From the repository root, in a separate terminal:

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Then `npm run dev` here and open http://localhost:5173.

## Screens

- **Home** — recent executions: task title, status, stalled flag, best hidden
  accuracy. A system status strip sits in the header (`GET /api/status`).
- **New Task** — description, language, entry function, optional starter code,
  and public + hidden tests. Each test holds exactly **one** check in this UI
  (the backend supports up to 20 per test; richer suites must be created via
  the API directly). Start Run is disabled until a title, description,
  language, entry function and at least one public and one hidden test exist.
  A confirmation states that the suite hash and configuration are recorded
  before any code is generated. On confirm it creates the task, creates an
  execution and starts the run; afterwards only counts and hashes are shown.
- **Run View** — the version tree (`GET /api/executions/{id}/tree`), polling
  while the run is non-terminal. Selecting a version shows its code, public
  test results and the Critic note (labelled *advisory*). Hidden results are
  counts only. A Cancel button appears for running executions.
- **Compare View** — hidden accuracy headline (previous → candidate), public
  accuracy for context, the gate result with exact failed terms, a coloured
  unified diff (`GET /api/versions/{id}/diff`) with a diff-only / full-file
  toggle, and the changelog. It warns when public accuracy improves but hidden
  accuracy does not.
- **Verification** — read-only: committed suite/config hashes, scoring rule,
  delta, evidence records, invalid comparisons and the advisory proposal count
  (`GET /api/executions/{id}/evidence`).
- **Publishing & Agent B** — a "Not available yet" placeholder. No data is
  shown because the backend workflow does not exist yet.

## Privacy guarantee

The backend strips hidden test ids, names, inputs, expected values and per-test
results from every response (they are returned as counts only). The dashboard
adds a second line of defence: a test (`src/screens/__tests__/hiddenLeak.test.tsx`)
feeds a deliberately malformed response containing those fields and asserts the
UI renders none of them.

## Layout

```
src/
  api/        typed client (unwraps the envelope, throws typed ApiError),
              React Query hooks (polling stops at terminal status), types
  components/ StatusStrip, Spinner, ErrorBox, Empty, Badge
  screens/    Home, NewTask, RunView, CompareView, Verification, Placeholder
  test/       setup, render helpers, fixtures
```

Any sample/preview data must carry a `SAMPLE DATA` badge (`components/Badge.tsx`).
None is used today; every value on screen comes from the backend.
