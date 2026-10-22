# RepoSage Console

Vue 3 + TypeScript (strict) + Vite frontend for RepoSage. It covers every REST endpoint the API has (register repo, snapshot status, create task, task status, SSE events, approval, cancel, health/readiness) through these screens:

| Route | Screen |
|---|---|
| `/tasks/:id` | **Trajectory**: live SSE view with node progress, tool calls (denied ones highlighted and filterable), and budget burn against steps, tokens, USD and seconds |
| `/tasks/:id/review` | **Approval review**: diff, sandbox test evidence, rationale; approve, edit or reject, each sending the pending `patch_sha256`; a 409 opens a stale-patch dialog that forces a refetch |
| `/tasks/:id/answer` | **QA answer**: answer text, citations with path, line range and symbol; a distinct not-found state |
| `/evals/compare` | **Eval compare**: two runs side by side with paired per-case deltas, win/loss/tie, SE of the delta, and run-to-run spread with an improved / within-noise verdict |

| `/` | **Overview**: API liveness/readiness, API key, open a task by id, recent tasks (the API has no list endpoint, so this is per-browser history) |
| `/repos` | **Repositories**: register a repo at a commit, follow indexing (queued, ingesting, ready, failed), repo map |
| `/tasks/new` | **New task**: question or fix mode with client-side validation matching the API limits, budgets |

A Cancel button on the task page covers `POST /tasks/{id}/cancel`. (`/metrics` is Prometheus-only and not surfaced.)

 What the console assumes about the backend, and where the backend disagrees with its own docs, is in [docs/BACKEND_CONTRACT.md](docs/BACKEND_CONTRACT.md). **Read that first**: the current worker does not persist SSE events, so the live views need the backend fixes listed there.

## Requirements

Bun 1.4+, Node 20+ (Vite, Vitest, Playwright run on Node; versions of `@vitejs/plugin-vue`, `jsdom` and `msw` are pinned to ranges that work on Node 20.10).

## Commands

```sh
bun install
bunx playwright install chromium     # once, for e2e and Lighthouse

bun run dev            # Vite on :5173, proxies /v1 to $API_PROXY (default http://127.0.0.1:8000)
bun run mock           # scripted mock API on :8788 (use with API_PROXY=http://127.0.0.1:8788 bun run dev; key: reposage-dev-key)
bun run build          # vue-tsc --noEmit && vite build
bun run preview

bun run typecheck      # vue-tsc --noEmit
bun run lint           # ESLint (bans v-html and innerHTML sinks)
bun run test           # Vitest: unit, component, MSW flows, security invariants, axe (jsdom)
bun run test:bun       # the pure-logic unit tests again under `bun test`
bun run test:e2e       # Playwright against the mock server (starts mock + Vite itself)
bun run test:e2e:stack # Playwright against the docker-compose stack; skips with a reason if it is not up
bun run lhci           # build, then Lighthouse CI (3 runs x 4 pages) with the budgets in lighthouserc.json
bun run verify         # typecheck + lint + test + test:bun + build

bun run export:openapi # re-export openapi.json from the FastAPI app (needs ../.venv)
bun run gen:api        # regenerate src/api/schema.d.ts from openapi.json
```

## How it is built

- **Types.** REST types come from `openapi.json` via `openapi-typescript`, called through `openapi-fetch` (`src/api/client.ts`). OpenAPI cannot describe SSE and types `result`/`budgets` as bare dicts, so those are Zod schemas in `src/api/contracts.ts` and are validated at runtime (SSE events, task results, eval exports). No other backend types are hand-written.
- **State.** TanStack Query for server state (task status polls every 2 s until terminal, and is refetched immediately when the stream implies a status change). Pinia for session (API key, theme) and the live trajectory (events, connection, derived nodes/tools/budget/pending patch).
- **SSE** (`src/lib/sse.ts`). `fetch`-based, because `EventSource` cannot send `X-API-Key`. Reconnects with capped exponential backoff and `Last-Event-ID`, dedupes replayed seqs, stops on `done`, treats 401/403/404 as fatal, and after six failed attempts shows a manual Reconnect button.
- **Styling.** Tailwind v4 over a small design system ("Obsidian & Signal", `src/style.css`): semantic tokens, light/dark/system themes, Geist and Geist Mono bundled via `@fontsource-variable` (no CDN). Axe checks colour contrast on every screen in both themes, so change colours only through the tokens. Icons are inline SVG from `AppIcon.vue` (marked `data-app-svg`; the injected-markup test treats any other `<svg>` as hostile). The entrance animation is transform-only on purpose: a fade would momentarily fail contrast scans. Diff syntax colouring (`src/lib/highlight.ts`) emits plain text segments rendered as text nodes. Headless components from Reka UI (dialogs, tabs, progress) for focus trapping and keyboard behaviour.
- **States.** All eight task statuses have a meaning and message (`src/lib/statusMeta.ts`); an unrecognised status renders as "Unknown status (value)". Also handled: SSE connecting / reconnecting / closed / failed, empty results, 401/403, 404, 5xx (retryable), network errors, malformed or unknown events, unreadable results.

## Safety properties (and the tests that enforce them)

- **No approval without the current hash.** `submitApproval` is the only POST in the app. It takes a branded `PendingPatch` that only an `approval_requested` event can produce and always sends that patch's `sha256`. The Approve/Edit/Reject buttons exist only inside `ApprovalPanel`, which `ReviewView` renders only for a pending patch. Tests: `tests/security/approval-sha.test.ts` (every decision carries the hash; a changed patch changes the hash sent; disabled buttons send nothing; static checks that no other module can POST) and `tests/msw/fix-flow.test.ts`.
- **A 409 forces a refetch.** The decision buttons stay disabled until the stream is replayed and the new patch hash is shown.
- **Untrusted text is only ever text.** No `v-html`, no `innerHTML`, no markdown renderer. Diffs, answers, tool names, denial reasons, citation paths, log tails, rationale and eval labels are all interpolated as text nodes. Citation links come only from `VITE_SOURCE_URL_TEMPLATE`, are percent-encoded, and must be `http(s)`. Tests: `tests/security/untrusted-html.test.ts` scans `src/` for sinks and pushes hostile payloads (`<img onerror>`, `<script>`, `<svg onload>`) through every component and view. ESLint also errors on `v-html`/`innerHTML`.
- I mutation-checked both: adding a `v-html` to the diff viewer fails the static, runtime and ESLint checks; sending a wrong hash fails 8 tests.

## API key

Every request, including the SSE stream, sends `X-API-Key`. Until you set one on the Overview page it uses `VITE_DEFAULT_API_KEY`; in dev (`bun run dev`) that falls back to the backend's default `reposage-dev-key`. Production builds have no baked-in key, so set `VITE_DEFAULT_API_KEY` at build time or enter it in the UI.

## Citation links

Set `VITE_SOURCE_URL_TEMPLATE` (for example `https://github.com/org/repo/blob/<sha>/{path}#L{start}-L{end}`) to make citations real links. Without it the location is shown as `path:start-end` with a Copy button, since the backend exposes no source-viewing endpoint.

## Budgets (Lighthouse CI, `lighthouserc.json`)

Mobile emulation, 3 runs per page, on the production build behind `vite preview`:
performance >= 0.90, accessibility = 1.00, best-practices >= 0.90, FCP <= 1800 ms, LCP <= 2500 ms, TBT <= 200 ms, CLS <= 0.10, JS transfer <= 200 KB, total transfer <= 250 KB.
Pages: `/`, a QA answer, a patch review (terminal task), an eval compare.
