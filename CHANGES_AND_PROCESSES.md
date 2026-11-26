# AutoEvolve — Changes & Running Processes

**Generated:** October 31, 2026
**Branch:** `test` · **Last commit:** `3d6005a` (Milestones 07A–08A)
**Working tree:** uncommitted changes present (see §3)

---

## 1. Running processes (captured live)

Both the backend API and the frontend dev server are running. The dashboard is
HTTP-to-FastAPI only, so both must be up for it to work.

| Service | Command | Port | PID(s) | Started |
|---|---|---|---|---|
| Backend API (uvicorn) | `.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000` | 8000 (127.0.0.1) | 37852 (+ child 9740) | 11:32 |
| Frontend (Vite dev) | `npm run dev` | 5173 (::1) | 4668 (+ esbuild child 7636) | 11:32 |

- Open the app at **http://localhost:5173**.
- Kiro-managed background processes: **none** (you are running both servers manually in your own terminals).

### How to start / stop them
```powershell
# Backend (terminal 1)
cd c:\Users\ASUS\Desktop\CBIT\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# Frontend (terminal 2)
cd c:\Users\ASUS\Desktop\CBIT\frontend
npm run dev
```
Stop either with `Ctrl+C` in its terminal.

---

## 2. Changes made in recent sessions

### 2a. Milestone 08B — React dashboard (new `frontend/`)
A Vite + React + TypeScript dashboard that talks only to the FastAPI backend.
- Typed API client (`src/api/client.ts`) that unwraps the response envelope and
  throws a typed `ApiError` (code / status / details); React Query hooks
  (`src/api/hooks.ts`) with polling that stops at terminal status; types in
  `src/api/types.ts`.
- Screens: Home, New Task, Run View, Compare View, Verification, Publishing &
  Agent B placeholder.
- Guarantee: hidden test names/inputs/per-test results never render — only
  counts and hashes (enforced + covered by `hiddenLeak.test.tsx`).
- 29 component/client tests (Vitest + Testing Library).

### 2b. Milestone 08B.1 — UI polish (this session, visual/layout only)
No API call, data shape, route, backend file, or test expectation was changed.
All 29 tests still pass.

**New files**
- `src/styles/tokens.css` — single source of design tokens (colors, spacing,
  radius, shadow, font sizes), with a full `[data-theme="light"]` palette.
- `src/theme.ts` — dark/light theme persistence helpers.
- `src/components/Sidebar.tsx` — fixed left nav (Home, New Task, Run, Compare,
  Verification, Publishing, Agent B); run-context items enable only inside a run.
- `src/components/ThemeToggle.tsx` — light/dark toggle (sun/moon).
- `src/components/CopyButton.tsx` — `CopyButton` + `HashChip` (copy hashes/ids).
- `public/favicon.svg` — SVG favicon.

**Rewritten / updated files**
- `src/styles.css` — full dark-first restyle (sidebar+topbar shell, cards,
  badges with a pulsing "running" dot, skeleton loaders, stat cards, timeline,
  stepper, tabs, compare banner, hash-chip grid, responsive down to tablet,
  focus rings, 150ms transitions). Every value references a token.
- `index.html` — SVG favicon link, page title, `color-scheme`.
- `src/main.tsx` — bundled Inter + JetBrains Mono fonts, token/style imports,
  theme init on load.
- `src/App.tsx` — sidebar + top bar layout shell; per-route page title.
- `src/components/StatusStrip.tsx` — status shown as colored pills
  (green configured / red missing / grey not-available).
- `src/components/Spinner.tsx` — now a skeleton shimmer (keeps the accessible
  loading label).
- `src/components/Empty.tsx` — friendly empty state with an icon.
- `src/screens/Home.tsx` — four stat cards + cleaner table with status badges.
- `src/screens/NewTask.tsx` — two-column form, monospace starter editor, hidden
  card with a lock + "Write-only: never shown again", copy-able example, modal
  confirmation listing the hashes to be recorded.
- `src/screens/RunView.tsx` — vertical timeline tree, stage stepper, public/
  hidden progress bars, failed-term chips, tabbed side panel
  (Code / Public tests / Critic *advisory* / Metadata).
- `src/screens/CompareView.tsx` — big hidden-accuracy banner (green/red),
  public context chip, gate failed-term chips, line-numbered diff with
  diff-only/full toggle, changelog, amber "public up / hidden not" warning.
- `src/screens/Verification.tsx` — hash-chip grid with copy buttons.
- `src/screens/Placeholder.tsx` — two polished "Coming next" cards.
- `package.json` — added `lucide-react`, `@fontsource-variable/inter`,
  `@fontsource-variable/jetbrains-mono`.

### 2c. New Task bug fix (this session)
- **Problem:** when the backend rejected a run, the error card rendered *behind*
  the confirmation modal and the modal stayed open, so it looked like "Start Run
  does nothing."
- **Fix:** the error now renders **inside** the modal (and the form-level copy
  is suppressed while the modal is open, so exactly one error shows). File:
  `src/screens/NewTask.tsx`.

### 2d. Earlier backend work present but NOT yet committed
These show as modified/untracked in git (from the 07B.1 stability, demo, and
08A dashboard work) and are part of the working tree, not yet in a commit:
- `backend/app/config.py`, `backend/app/main.py`,
  `backend/app/evaluation/execution.py`, `backend/pytest.ini`,
  `backend/requirements.txt`, `backend/.env.example`, `backend/README.md`,
  `backend/tests/conftest.py`
- `backend/tests/test_stability.py` (new)

---

## 3. Uncommitted changes (git status)

```
 M backend/.env.example
 M backend/README.md
 M backend/app/config.py
 M backend/app/evaluation/execution.py
 M backend/app/main.py
 M backend/pytest.ini
 M backend/requirements.txt
 M backend/tests/conftest.py
?? backend/tests/test_stability.py
?? frontend/            (entire dashboard: 08B + 08B.1)
?? package-lock.json
```

> Nothing above has been committed or pushed. The last commit on `test` is
> `3d6005a`. Commit/push only when you ask.

---

## 4. Verification status (frontend, last run this session)

| Check | Command | Result |
|---|---|---|
| Lint | `npm run lint` | pass (0 errors) |
| Type-check + build | `npm run build` | pass |
| Component tests | `npm test` | 29 passed / 29 |
