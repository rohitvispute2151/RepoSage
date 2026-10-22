# What the console builds against

Derived from the code in `src/reposage/` (authoritative for behaviour) and `RepoSage_HLD.md` / `RepoSage_LLD.md` (the intended contract).
The REST types in `src/api/schema.d.ts` are generated from `openapi.json`, which is exported from the FastAPI app (`bun run export:openapi`).

## REST API (all under `/v1`, header `X-API-Key`; 401 missing, 403 wrong)

| Method | Path | Notes |
|---|---|---|
| POST | `/repos` | 202. Registers repo and commit, starts ingestion in-process. Used by `/repos`. |
| GET | `/repos` | `?limit` (1-200, default 50), `?offset`, `?status=queued\|ingesting\|ready\|failed`. `{items, total, limit, offset}`, newest first; each item has `id, repo_id, name, source_uri, commit_sha, status, error, chunk_count, created_at` (no `mirror_path`). Used by `/repos` and the snapshot picker on `/tasks/new`. |
| GET | `/repos/{snapshot_id}` | Snapshot status, polled until `ready`/`failed`. Used by `/repos` and `/tasks/new`. |
| POST | `/tasks` | 202 `TaskResponse`. `mode` is `qa` or `fix`. Used by `/tasks/new`. |
| GET | `/tasks/{id}` | `TaskResponse`: `status`, `outcome`, `budgets`, `result` (the last two are untyped `dict` in OpenAPI). |
| GET | `/tasks/{id}/events` | SSE, resumable with `Last-Event-ID` (integer seq). |
| POST | `/tasks/{id}/approval` | Body `{decision: approve\|reject\|edit, patch_sha256, edited_diff?, comment?}`. 200 `{status:"accepted"}`; **409** if the task is not `awaiting_approval` or the sha is not the latest patch's; 422 if `edit` has no diff. |
| POST | `/tasks/{id}/cancel` | Cancel button on the task page (confirmation dialog). | |
| GET | `/healthz`, `/readyz`, `/metrics` | `/healthz` and `/readyz` feed the status strip on the home page. `/metrics` is for Prometheus, not the console. |

## Task state machine

Eight statuses: `queued`, `running`, `awaiting_approval`, `completed`, `failed`, `budget_exceeded`, `cancelled`, `approval_timeout`.

```text
queued -> running | cancelled
running -> awaiting_approval | completed | failed | budget_exceeded | cancelled
awaiting_approval -> running | approval_timeout | cancelled
```

Terminal: `completed`, `failed`, `budget_exceeded`, `cancelled`, `approval_timeout`. `outcome` carries the detail
(`answered`, `patch_applied`, `patch_rejected`, `loop_detected`, `not_reproducible`, `apply_failed`, `edited_patch_invalid`, ...).
Loop detection and non-reproducible bugs finish as `completed` with those outcomes, not as separate statuses.

## SSE events

Wire format: `id: <seq>\nevent: <type>\ndata: <json>\n\n`. After the task reaches a terminal status the server sends `event: done` (no `id`) and closes.

| Event | Payload | Emitted by current backend |
|---|---|---|
| `node_started` / `node_finished` | `{node}` (+ `passed` from verify, `validation` from patch) | yes (but not for `approval`, and the sink is a no-op, see below) |
| `approval_requested` | `{patch_id, diff, sha256, test_evidence, rationale}` | yes (same caveat) |
| `patch_applied` | `{applied, error}` | yes |
| `patch_rejected` | `{comment}` | yes |
| `completed` | `{status, outcome}` | yes |
| `done` | `{status}` | yes, from the API route |
| `tool_call` | `{tool, status: allowed\|denied\|ok\|error\|timeout, denial_reason, duration_ms, node}` | **no**: documented in LLD §3 only |
| `llm_call` | `{model, tokens_in, tokens_out, cost_usd, latency_ms}` | **no** |
| `budget` | `{steps, tokens, usd, seconds, limits}` | **no** |

Every event is validated with Zod. A malformed event is shown in the log as malformed, an unrecognised type is counted, and neither crashes the stream.

## Approval flow

1. Verify passes, the approval node sets `awaiting_approval` and emits `approval_requested` with the diff, its `sha256`, test evidence and rationale, then pauses (LangGraph `interrupt`).
2. The reviewer decides. The console POSTs the decision with **that event's** `sha256`.
3. The API locks the task row, requires `awaiting_approval` (else 409), compares the sha to the latest patch (else 409), stores an `approvals` row and enqueues `run_task(task_id, approval_id)`.
4. The worker resumes the graph: `approve` applies the diff with `git apply` and emits `patch_applied`; `reject` emits `patch_rejected`; `edit` re-validates, goes back through verify and asks again with a new sha.
5. Report writes the final `result` and status.

## Code vs docs vs reality: discrepancies

Ordered by how much they affect the UI. Items 1 to 4 mean **the live views cannot work against the current worker**, whatever the frontend does.

1. **No events are ever persisted.** `workers/tasks.py` passes `event_sink = lambda ...: pass`, so `task_events` stays empty. The SSE route then only ever sends `done`. (LLD §3, §7.5 and HLD §5.1 describe an event table plus pub/sub.)
2. **No checkpointer.** `build_graph(deps)` is called without one. LangGraph `interrupt()` and `Command(resume=...)` need a checkpointer, so approval pause/resume and crash-resume (HLD FR-6, LLD §11.1 with `AsyncPostgresSaver`) cannot work as written.
3. **The pending patch has no read endpoint.** It is only delivered by the `approval_requested` SSE event (see 1). `GET /tasks/{id}` does not include it, and there is no `GET /tasks/{id}/patch`. The console therefore rebuilds the pending patch by replaying the stream, and a 409 "refetch" means restarting the stream from `seq 0`.
4. **No eval API.** LLD §14 describes eval runs, results and a `compare` command with paired deltas and spread. There are no eval routes, and `reposage-eval compare` prints hard-coded numbers (`evals/cli.py`). The console reads exports in the shape of the `eval_runs` / `eval_results` tables from `GET /v1/evals/runs/{id}` (proposed) or a JSON file.
5. `tool_call`, `llm_call` and `budget` events are documented (LLD §3, HLD §13) but never emitted. Live budget burn is only exact once a `budget` event exists; until then the console counts steps from node events, runs the wall clock locally and shows tokens and USD as "not reported". Final usage comes from `result.budget_report`.
6. `TaskResponse.result` and `.budgets` are `dict[str, Any]`; `TaskResult` and `Citation` exist in `api/schemas.py` but are not referenced by any route, so they are missing from OpenAPI. The console re-declares them in Zod (`src/api/contracts.ts`) and validates at runtime.
7. **`found` is dropped.** `answer.v1.md` asks for `found: bool`; the report node keeps only `answer` and `citations`. The console infers not-found from a missing/placeholder answer ("Unable to locate answer."), honours `found:false` if it ever appears, and flags an answer with zero verified citations as unverified.
8. **Verify evidence is thinner than LLD §9/§10.8.** Verify forwards only `{all_target_pass, regressions (always 0), policy_ok, failure_digest}`. No per-test list, no log tail, and no regression subset is run. The evidence panel renders per-test rows and logs when present and says plainly when they are not.
9. **`failed` is never set by the worker.** Exceptions in `_run_task_async` propagate; nothing transitions the task to `failed`. A crashed task stays `running` until the reaper requeues it. The status exists in the schema and the console handles it.
10. **Report can overwrite `cancelled`.** The report node writes its terminal status unconditionally, so a cancel that races a running graph can be overwritten.
11. **Approval node is not idempotent on resume** (LLD §10.9 requires it). It re-runs from the top, so once events work it would re-emit `approval_requested` after a decision. The console treats `patch_applied`, `patch_rejected`, `completed` and `done` arriving after a request as resolving it.
12. **Approval resume can silently not happen.** `apply_async(..., retry=False)` errors are swallowed, so with the broker down the API still answers `accepted`. The UI says "waiting for the worker to resume", not "applied".
13. `TaskCreate.idempotency_key` is accepted and ignored. Auth is a single shared key (no `submitter`/`approver` roles, approver is the literal `"api_user"`). CORS is `*` with `allow_credentials=True`, which browsers reject for credentialed requests; the console uses a header key and no cookies, so it is unaffected. `/readyz` returns 200 with `status: unhealthy`.
14. `docker-compose.yml` uses `build: .` for api, worker, beat, mcp-tools and sandbox-runner, but the repository has no Dockerfile, so `docker compose build` cannot succeed as committed. (`mcp-tools` also gets no database environment.)
