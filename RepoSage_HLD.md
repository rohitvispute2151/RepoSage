# RepoSage: High-Level Design (HLD)

| Field | Value |
|---|---|
| Document | High-Level Design |
| System | RepoSage: Agentic Codebase Assistant |
| Version | 1.0 (draft for 1-week build) |
| Audience | Engineers, reviewers, interviewers |
| Companion | `RepoSage_LLD.md` (low-level design) |

---

## 1. Purpose and scope

### 1.1 Purpose
RepoSage is a service that helps engineers understand and fix code. It supports two task types:

1. **QA mode**: answer questions about a repository ("where is retry logic handled?") with verifiable citations (file, line range, symbol).
2. **Fix mode**: given a failing-test bug report, investigate, propose a patch, **prove it in a sandbox by running tests**, and apply it only after explicit human approval.

### 1.2 Why this system exists (engineering goals)
- Study agent reliability against **objective outcomes** (tests pass or fail).
- Build code-aware retrieval where plain natural-language chunking breaks down.
- Safely contain a system that executes model-generated code.
- Be fully measurable: every claim about quality, cost, and latency is backed by an eval harness.

### 1.3 Non-goals (v1)
- Languages other than Python.
- Multi-agent swarms, IDE plugins, real Git-host integration (GitHub/GitLab PRs).
- Multi-tenancy, SSO, billing.
- Fine-tuning models.
- Autoscaling sandbox fleets.

### 1.4 Glossary

| Term | Meaning |
|---|---|
| Chunk | A function, method, or class extracted from source, with metadata |
| Symbol | A named code entity (function, class, method) |
| Hybrid search | Vector similarity + lexical (FTS/trigram) retrieval, fused with RRF |
| RRF | Reciprocal Rank Fusion, a rank-merging method |
| Rerank | Re-scoring top-N candidates with a cross-encoder or LLM |
| HITL | Human-in-the-loop approval gate |
| Checkpoint | Persisted agent state after each graph step |
| Trajectory | The sequence of agent steps and tool calls in a run |
| pass@k | Probability that at least one of k attempts resolves a task |

---

## 2. Requirements

### 2.1 Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | Ingest a repository at a pinned commit into searchable, symbol-level chunks |
| FR-2 | Answer natural-language questions with citations that resolve to real file/line ranges |
| FR-3 | Given a bug task (failing tests), propose a patch and verify it by running tests in an isolated sandbox |
| FR-4 | Never apply a patch without explicit human approval; the human may approve, edit, or reject |
| FR-5 | Enforce hard budgets (steps, tokens, cost, wall-clock) per task, ending gracefully with a partial report |
| FR-6 | Resume any task after worker crash from its last checkpoint without repeating completed side effects |
| FR-7 | Provide task status and event streaming to clients |
| FR-8 | Expose repository tools through an MCP server |
| FR-9 | Run an evaluation harness (retrieval, QA, fix, trajectory, consistency) from CLI and CI |

### 2.2 Non-functional requirements (targets to validate, not claims)

| Category | Target | How validated |
|---|---|---|
| QA latency | P95 time-to-first-token under [target, e.g. 3 s]; P95 full answer under [target, e.g. 15 s] | Load script, Prometheus histograms |
| Fix latency | P95 under [target, e.g. 5 min] excluding human approval wait | Eval runs |
| Availability | API tier survives loss of any single worker; tasks resume | Chaos tests |
| Safety | 0 patches applied without approval; 0 test files modified by agent; 0 sandbox escapes in adversarial suite | Eval gate |
| Cost | Per-task budget cap enforced; cost per resolved task reported | Usage ledger |
| Durability | No task state lost on worker/API restart | Crash-resume test |
| Observability | Every task has one trace with node/tool/LLM spans | Trace coverage check |
| Reproducibility | Every run records prompt hashes, model IDs, repo commit, seed/config | Run record |

### 2.3 Constraints and assumptions
- One experienced engineer, about 7 days.
- Python 3.11+, Postgres as the single stateful store, Docker available on worker hosts.
- Two LLM providers reachable (primary + fallback), with tool-calling support.
- Target repos are small to medium open-source Python projects with existing test suites.

---

## 3. System context

```text
                  +-------------------+
   Engineer ----> |   CLI / REST API  |
   (user,         +---------+---------+
    approver)               |
                            v
                  +-------------------+        +------------------+
                  |     RepoSage      | -----> | LLM providers    |
                  |   (this system)   |        | (primary+fallback)|
                  +----+---------+----+        +------------------+
                       |         |
                       v         v
              +-----------+   +----------------+
              | Git repos |   | Langfuse /     |
              | (local    |   | Prometheus     |
              |  mirrors) |   +----------------+
              +-----------+
```

External actors and systems:
- **Engineer**: submits tasks, approves or rejects patches.
- **LLM providers**: chat/tool-calling models and an embedding model.
- **Git repos**: read-only mirrors at pinned commits (no network credentials stored in v1).
- **Observability stack**: traces, metrics, dashboards.

---

## 4. Architecture overview

### 4.1 Logical architecture

```text
+---------------------------------------------------------------------+
|                           API LAYER (FastAPI)                       |
|  /repos  /tasks  /tasks/{id}/events (SSE)  /tasks/{id}/approval     |
|  auth (API key) | rate limit | request-id | validation              |
+----------------------------+----------------------------------------+
                             | enqueue / query
+----------------------------v----------------------------------------+
|                 ORCHESTRATION LAYER (Celery workers)                |
|  Task runner -> LangGraph agent (checkpointed to Postgres)          |
|                                                                     |
|   Plan -> Retrieve -> Explore loop -> Patch -> Verify -> Approval   |
|                          |                          |       -> Report|
|                  Guardrail / Policy layer      (interrupt)          |
|                  Budget manager | Loop detector                     |
+-----+----------------+------------------+---------------------+-----+
      |                |                  |                     |
+-----v-----+  +-------v--------+  +------v-------+     +-------v------+
| LLM       |  | RETRIEVAL      |  | MCP TOOL     |     | SANDBOX      |
| GATEWAY   |  | SERVICE        |  | SERVER       |     | RUNNER       |
| (client   |  | rewrite->hybrid|  | search, read,|     | Docker, no   |
| abstraction|  | ->rerank       |  | grep, symbols|     | network,     |
| retry/    |  |                |  | run_tests,   |     | limits       |
| fallback) |  |                |  | apply_patch  |     |              |
+-----+-----+  +-------+--------+  +------+-------+     +-------+------+
      |                |                  |                     |
+-----v----------------v------------------v---------------------v-----+
|                       DATA LAYER                                    |
|  PostgreSQL: repos, files, chunks(+pgvector, FTS, trigram),         |
|  tasks, runs, events, checkpoints, approvals, usage ledger          |
|  Redis: Celery broker, rate limits, locks, short-lived cache        |
|  Object/volume store: repo mirrors, patch artifacts, test logs      |
+---------------------------------------------------------------------+
|                 OBSERVABILITY + EVALUATION                          |
|  Langfuse traces | Prometheus metrics | Eval harness (CLI + CI)     |
+---------------------------------------------------------------------+
```

### 4.2 Key architectural principles
1. **Graph over free-form loop.** The agent is an explicit state machine, so every transition is inspectable, budgeted, and resumable.
2. **Deterministic guardrails outside the model.** Policy checks (paths, sizes, allowlists, approval) are code, never prompt instructions.
3. **Untrusted by default.** Repository text, tool output, and model output are all untrusted input.
4. **Side effects are gated and idempotent.** Only two side-effecting tools exist (`run_tests`, `apply_patch`), both guarded and idempotency-keyed.
5. **State lives in Postgres, workers are stateless.** Any worker can resume any task.
6. **Measure first.** The eval harness is built before the agent, and every design choice is an ablation.

---

## 5. Component descriptions

### 5.1 API service
- Accepts repo registration, task creation, approval decisions, and event subscriptions.
- Does no LLM work. It validates, persists, and enqueues, so it stays fast and horizontally scalable.
- Streams task events (Server-Sent Events) from an event table plus Redis pub/sub.

### 5.2 Worker and task runner
- Celery worker pulls a task ID, loads or creates its checkpoint thread, and drives the LangGraph agent.
- Holds a per-task distributed lock so two workers never run the same task.
- On crash, the lock expires (lease), the task is requeued, and the graph resumes from the latest checkpoint.

### 5.3 Agent (LangGraph)
Nodes: **Plan, Retrieve, Explore, Patch, Verify, Approval, Report**. Details in section 8.

### 5.4 Retrieval service
Pipeline: query rewrite, hybrid search (vector + FTS + trigram), RRF fusion, rerank, symbol-level result with citations. Details in section 9.

### 5.5 LLM client layer
- Provider-agnostic interface (chat, tool-calling, embeddings, structured output).
- Retry with jittered backoff, per-provider circuit breaker, ordered fallback chain.
- Records tokens, cost, latency, model ID, and prompt hash on every call.

### 5.6 MCP tool server
- Exposes repository tools over MCP so the agent depends on a protocol boundary rather than in-process functions.
- Every tool has a strict JSON schema, a timeout, and an output size cap.
- The **guardrail layer** wraps tool dispatch: it validates arguments and enforces policy before a call reaches the server.

### 5.7 Sandbox runner
- Executes tests (and nothing else) in an ephemeral, network-less container with CPU, memory, PID, and time limits.
- Receives a read-only copy of the repo plus an overlay containing the candidate patch.
- Returns structured results (pass/fail per test, durations, truncated logs).

### 5.8 Data stores

| Store | Role |
|---|---|
| PostgreSQL | System of record: repos, chunks, vectors, tasks, checkpoints, approvals, ledger |
| Redis | Celery broker, rate-limit counters, task leases, pub/sub for events |
| Volume/object store | Repo mirrors at pinned commits, patch files, raw test logs |

### 5.9 Observability and evaluation
- Langfuse: trace per task with spans for nodes, tools, LLM calls, retrieval.
- Prometheus: RED metrics, token/cost counters, budget-breach and escalation counters.
- Eval harness: replays task suites, scores outcomes automatically, enforces CI gates.

---

## 6. Data architecture

### 6.1 Entity overview

```text
repos 1---* repo_snapshots 1---* files 1---* chunks
                  |
                  *
               tasks 1---* task_events
                  |  1---* tool_calls
                  |  1---* llm_calls   (usage ledger)
                  |  1---* approvals
                  |  1---1 checkpoint thread (LangGraph tables)
                  *
               patches
eval_suites 1---* eval_cases ; eval_runs 1---* eval_results
```

### 6.2 Data lifecycle
- **Snapshot** = repo at a specific commit SHA. Chunks belong to a snapshot, so re-ingesting a new commit never mutates existing data.
- **Chunks** are immutable once written. Identity = `(snapshot_id, file_path, symbol_qualname, content_hash)`.
- **Tasks** reference a snapshot, so every answer is reproducible against the exact code it saw.
- **Checkpoints** are retained until task completion plus a retention window, then pruned.
- **Test logs and traces** are truncated and secret-scanned before storage.

### 6.3 Consistency model
- Postgres transactions for task state transitions (state machine with allowed transitions only).
- Idempotency keys on side-effecting tool calls (`task_id + step_id + tool + args_hash`).
- At-least-once task delivery from Celery, with idempotent handling.

---

## 7. Key flows

### 7.1 Repository ingestion

```text
Client -> POST /repos {url|path, commit}
API: validate, create repo_snapshot (status=queued), enqueue ingest
Worker:
  1. Materialize repo at commit (read-only mirror)
  2. Walk files (respect ignore list, size limits)
  3. Parse Python files into symbols (AST/tree-sitter)
  4. Build chunk text = header(path, qualname, signature, docstring) + body
  5. Batch-embed chunks (dedupe by content_hash)
  6. Insert chunks + tsvector + trigram text
  7. Build/refresh indexes; status=ready
  8. Emit repo map (module -> symbols) for the Plan node
```

### 7.2 QA task

```text
Client -> POST /tasks {mode: qa, repo_snapshot, question}
API -> enqueue
Worker -> graph:
  Plan: classify as QA; set budgets
  Retrieve: rewrite -> hybrid -> rerank -> top-k symbols
  Explore (0..n iterations): read_file(range), grep, list_symbols to resolve gaps
  Report: answer + citations
  Citation verifier (deterministic): every cited file/range exists and contains the cited symbol
  -> events streamed to client (SSE)
```

### 7.3 Fix task with human approval

```text
Client -> POST /tasks {mode: fix, failing_tests[], description}
Worker -> graph:
  Plan -> Retrieve -> Explore (reproduce failure via run_tests baseline)
  -> Patch: model proposes unified diff
  -> Patch validator (size, allowed paths, no test files, applies cleanly)
  -> Verify: sandbox runs target tests + regression subset on patched copy
       fail -> repair loop (bounded) -> Patch
       pass -> Approval
  -> Approval: graph interrupt, task status = awaiting_approval
Human -> POST /tasks/{id}/approval {decision: approve|reject|edit, edited_patch?}
  edit -> re-validate and re-verify the edited patch
  approve -> apply_patch (idempotent) -> Report
  reject -> Report (patch not applied, rationale recorded)
```

### 7.4 Crash and resume

```text
Worker A runs task T, checkpointing after every node.
Worker A dies. Its lease on T expires.
Reaper/requeue marks T runnable.
Worker B acquires lease, loads latest checkpoint for thread T.
Graph resumes at the next un-run node.
Side effects already recorded in tool_calls (by idempotency key) are not repeated;
their stored results are replayed into state.
```

### 7.5 Budget breach

```text
Budget manager checks after every node and tool call.
Breach (steps | tokens | cost | wall-clock) -> route to Report with status=budget_exceeded,
partial findings, and the reason. No silent truncation.
```

---

## 8. Agent design

### 8.1 Graph

```text
START -> Plan -> Retrieve -> Explore <-----+
                    |          |  |        |
                    |          |  +--loop--+   (bounded; budget + loop detector)
                    |          v
                    |     [QA?]--yes--> Report -> END
                    |          |
                    |          no (fix)
                    |          v
                    |        Patch -> Verify --fail(bounded)--> Patch
                    |                    |
                    |                  pass
                    |                    v
                    |                Approval (interrupt)
                    |               /     |      \
                    |         approve   edit    reject
                    |             |       |        |
                    |        apply_patch  Verify   Report
                    |             |
                    +-----------> Report -> END
Any node --budget breach / fatal error--> Report (partial) -> END
```

### 8.2 Agent state (conceptual)
- Task identity, mode, repo snapshot, original request
- Rewritten queries, retrieved candidates, evidence set (with citation anchors)
- Message history (compacted), scratchpad (hypotheses, facts established)
- Patch candidate(s), validation results, test results
- Budget counters, step counter, loop-detector fingerprints
- Approval decision, final report

### 8.3 Context management
- Evidence is stored as structured items (path, range, symbol, snippet), not pasted transcript.
- History is compacted when it exceeds a token threshold: older tool outputs are replaced by short summaries plus pointers to evidence.
- Tool outputs are truncated to a cap with an explicit "truncated" marker.
- A **repo map** (module to symbol outline) is cached per snapshot and included in planning.

### 8.4 Model usage per node (cost control)

| Node | Model tier | Rationale |
|---|---|---|
| Plan, query rewrite | Small/cheap | Classification and short generation |
| Explore | Mid | Tool selection quality matters |
| Patch | Strongest | Highest-value reasoning |
| Report/answer | Mid or strong | Quality of final answer |
| Rerank (if LLM-based) | Small | High volume, narrow task |

Tier-to-model mapping lives in config so it can be ablated.

### 8.5 Reliability mechanisms
- **Budgets**: max steps, tokens, dollars, wall-clock per task and per node.
- **Loop detection**: fingerprint `(tool, normalized_args)`; repeated fingerprints beyond a threshold force a replan or terminate.
- **Bounded repair**: patch repair attempts capped (for example 3).
- **Forced finalization**: near budget exhaustion, the agent is routed to Report with what it has.

---

## 9. Retrieval architecture

### 9.1 Pipeline

```text
Question
  -> Query rewriter (small model): produces
       - natural-language variants
       - likely identifiers / file names / error strings
  -> Parallel retrieval per variant:
       a) Vector: pgvector cosine on chunk embeddings
       b) Lexical: Postgres FTS on identifier-expanded text
       c) Fuzzy: pg_trgm similarity on qualnames and paths
  -> RRF fusion -> top 20-30 candidates
  -> Reranker (cross-encoder or LLM) -> top 5-8
  -> Expand: attach parent class signature, file path, line range
```

### 9.2 Design decisions
- **Chunk unit = function/method/class**, with a header (path, qualname, signature, docstring). Large classes are split into method chunks plus a class-summary chunk.
- **Identifier expansion**: `parse_retry_header` is also indexed as `parse retry header`, since default FTS tokenization handles snake_case and camelCase poorly.
- **Hybrid is essential for code**: meaning queries ("where do we handle rate limits") need vectors; identifier queries need lexical/trigram.
- **Metadata filters**: snapshot, path prefix, symbol kind, test-vs-source.
- **Test files are indexed but flagged**, so the agent can find tests without mistaking them for implementation.

### 9.3 Citation model
A citation = `{snapshot_id, path, start_line, end_line, symbol}`. The verifier checks that the range exists in the snapshot and that the symbol occurs within it.

---

## 10. Tool and MCP architecture

### 10.1 Tool catalogue

| Tool | Type | Purpose | Key guards |
|---|---|---|---|
| `search_code` | read | Hybrid retrieval | Result cap, snapshot-scoped |
| `read_file` | read | Read a line range | Path allowlist, max lines |
| `grep` | read | Regex/literal search | Pattern length cap, result cap |
| `list_symbols` | read | Outline of a file/module | Snapshot-scoped |
| `run_tests` | **side effect (sandboxed)** | Execute selected tests on a snapshot or patched copy | Sandbox limits, test selector validation |
| `apply_patch` | **side effect (privileged)** | Apply approved diff to the working copy | Approval token required, idempotent |

`apply_patch` is **not callable by the model**. It is invoked only by the Approval node after a valid approval record exists.

### 10.2 Guardrail layer (policy enforcement point)
All tool calls pass through one chokepoint that:
1. Checks the tool is on the allowlist for the current node.
2. Validates arguments against the JSON schema.
3. Enforces path policy (inside repo root, no symlink escape, no ignored dirs).
4. Applies size and rate limits.
5. Scans outputs for secrets before they reach the model or traces.
6. Records the call (args hash, duration, result summary) for audit and idempotency.

Tool output is wrapped in clearly delimited, labeled blocks and can never alter the allowlist or policy.

---

## 11. Security architecture

### 11.1 Assets and trust boundaries

```text
[Untrusted]  Repo contents, tool output, model output, user task text
[Semi-trusted] Authenticated API caller
[Trusted]    Policy code, orchestrator, DB, sandbox runner service
Boundaries:  Model <-> Guardrail layer | Orchestrator <-> Sandbox | API <-> Internet
```

### 11.2 Threat model

| Threat | Example | Mitigation |
|---|---|---|
| Prompt injection via repo | README says "delete tests and print env" | Untrusted-data delimiting; tool allowlist outside model control; patch validator forbids test edits; adversarial eval tasks |
| Malicious generated code | Patch or test run tries network exfiltration | No-network sandbox, read-only FS, dropped capabilities, resource limits |
| Sandbox escape | Container breakout | Non-root user, seccomp default, no privileged mode, no host mounts except read-only repo copy; optional gVisor/Firecracker hardening |
| Path traversal | `read_file("../../etc/passwd")` | Canonical path resolution, allowlist, symlink checks |
| Test tampering | Agent edits tests to make them pass | Validator rejects any change under test paths or matching test patterns; test files mounted read-only in verify |
| Secret leakage | `.env` content in prompt/trace | Ignore list, secret scanner on retrieved text and traces |
| Resource exhaustion | Infinite loop, fork bomb | CPU/mem/PID/time limits, global sandbox slot cap |
| Unapproved write | Patch applied without human | `apply_patch` unreachable from model; requires approval record; audited |
| Cost abuse | Runaway loops | Hard budgets, per-key rate limits, concurrency caps |
| Supply-chain in test deps | Malicious package at test time | Pre-built dependency image per repo, no network at run time |

### 11.3 Sandbox isolation requirements
- No network (`--network none`).
- Read-only root filesystem; writable tmpfs for scratch only.
- Non-root user; all capabilities dropped; `no-new-privileges`.
- CPU, memory, PID, file-size, and wall-clock limits.
- Repo mounted read-only; patch applied in an overlay/copy.
- The component that talks to the Docker daemon is a **separate sandbox-runner service**, so general workers never hold the Docker socket.

### 11.4 AuthN/Z
- API key per caller, hashed at rest.
- Role split: `submitter` can create tasks; `approver` can decide approvals (can be the same person in v1, distinct claim in the data model).
- Approval records capture who, when, and exactly which patch hash was approved.

---

## 12. Reliability and failure handling

| Failure | Detection | Response |
|---|---|---|
| Worker crash | Lease expiry | Requeue; resume from checkpoint; idempotent side effects |
| LLM provider error/timeout | Exceptions, latency | Retry with backoff; breaker opens; fallback model; typed error if exhausted |
| Malformed model output | Schema validation | Repair prompt (bounded), then fallback model, then fail node |
| Tool timeout | Timeout | Retry once; mark gap; replan around the tool |
| Test runner crash/OOM | Container exit status | Classified as infrastructure failure, retried once; not treated as test failure |
| Patch fails to apply | Apply error | Feed error to repair loop (bounded) |
| Agent loop | Repeated fingerprints | Replan, else terminate with partial report |
| Budget exhausted | Budget manager | Graceful partial report |
| DB unavailable | Connection errors | API returns 503; workers retry with backoff; no state corruption (transactional writes) |
| Human never approves | Approval TTL | Task expires to `approval_timeout`; patch discarded |

### 12.1 Task state machine

```text
queued -> running -> awaiting_approval -> running -> completed
   |         |              |                          
   |         +--> failed    +--> rejected (completed with outcome=rejected)
   |         +--> budget_exceeded
   |         +--> cancelled
   +--> cancelled
awaiting_approval --TTL--> approval_timeout
```
Only transitions in this table are permitted; illegal transitions raise and are logged.

---

## 13. Observability architecture

### 13.1 Tracing
One trace per task. Span hierarchy: `task` > `node` > (`llm_call` | `tool_call` | `retrieval` | `sandbox_run`). Attributes: model, prompt hash, tokens in/out, cost, latency, retry count, fallback used, policy decision.

### 13.2 Metrics (Prometheus)
- `tasks_total{mode,status}`, `task_duration_seconds{mode}`
- `llm_calls_total{provider,model,outcome}`, `llm_tokens_total{direction}`, `llm_cost_usd_total`
- `retrieval_latency_seconds{stage}`, `rerank_latency_seconds`
- `tool_calls_total{tool,outcome}`, `policy_denials_total{reason}`
- `sandbox_runs_total{outcome}`, `sandbox_queue_wait_seconds`
- `budget_breaches_total{type}`, `loop_detections_total`
- `approvals_total{decision}`, `resume_total{reason}`

### 13.3 Logging
Structured JSON logs with `task_id`, `step_id`, `request_id`. Secret-scanned. No raw repo contents beyond truncated snippets.

### 13.4 Alerts (examples)
- Sandbox failure rate above threshold.
- Policy-denial spike (possible injection campaign).
- Cost per task above budget percentile.
- Resume rate rising (unstable workers).

---

## 14. Evaluation architecture

Evaluation is a first-class subsystem, built on Day 1.

### 14.1 Suites

| Suite | Content | Ground truth |
|---|---|---|
| Retrieval | ~40 questions per repo | Gold symbol(s) |
| QA | ~40 questions | Gold location + rubric |
| Fix | 15-20 injected-bug tasks | Target tests pass, no regressions |
| Adversarial | ~4 tasks with malicious repo text | Policy invariants hold |
| Failure injection | Tool timeout, runner crash, bad patch, empty search | Recovery behavior |

### 14.2 Metrics
- **Retrieval**: Recall@k, MRR at symbol level, with ablations (vector, +lexical, +rewrite, +rerank).
- **QA**: deterministic citation validity; judge-scored correctness (judge calibrated against about 30 hand labels, agreement reported).
- **Fix**: resolve rate (pass@1), pass@k, regression rate, tests-modified rate (must be 0).
- **Trajectory**: tool calls per task, wasted calls, steps to resolution, loop rate, budget-hit rate.
- **Consistency**: outcome agreement across 5 repeated runs.
- **Cost/latency**: cost per resolved task, P50/P95 duration.

### 14.3 Bug injection
A script mutates source (flip comparison, off-by-one, wrong default, swapped args, removed guard) at known locations, verifies that at least one existing test fails, and records the ground-truth location and fixing diff.

### 14.4 Gates
- **PR gate**: small sample suite; fails on invariant violations or metric drops beyond a stated threshold.
- **Nightly**: full suites, 5-run consistency, trend dashboard.
- Improvement = beats run-to-run noise (report spread across repeated runs), not a single-run difference.

---

## 15. Deployment architecture

### 15.1 Topology (v1: single host or small VM set)

```text
+---------------- Host A (app) ----------------+   +------ Host B (sandbox) ------+
| api (FastAPI)       x2                       |   | sandbox-runner service       |
| worker (Celery)     xN                       |   | Docker daemon (isolated)     |
| mcp-tool-server                              |   | dependency images per repo   |
| postgres (+pgvector)  | redis                |   +------------------------------+
| langfuse | prometheus | grafana              |
+----------------------------------------------+
```
Docker Compose for local and demo; the same images deploy to a single cloud VM or ECS. Sandbox host is separate when possible so untrusted code never shares a kernel boundary with the database.

### 15.2 Environments
- **local**: Compose, small repos, fake/stub LLM for unit tests.
- **ci**: ephemeral Postgres/Redis, recorded-response LLM fixtures for deterministic tests, plus a small live-model eval sample.
- **demo/prod-like**: cloud VM(s), real providers, secrets from environment/secret manager.

### 15.3 CI/CD pipeline

```text
lint + type check -> unit tests -> integration tests (ephemeral DB, stub LLM)
  -> build images -> eval gate (sample suite) -> publish -> deploy (manual approve)
nightly: full eval + consistency runs -> report artifact + dashboard
```

---

## 16. Scalability and capacity

| Dimension | Approach in v1 | Scale-out path |
|---|---|---|
| API | Stateless, N replicas | Behind load balancer |
| Workers | Stateless, lease-based; add workers for throughput | Queue-depth autoscaling |
| Sandbox | Slot semaphore (e.g. 4 concurrent runs) | Sandbox worker pool, per-run microVMs |
| Retrieval | HNSW + GIN indexes in one Postgres | Read replicas; separate vector store if corpus grows large |
| Ingestion | Batch embeddings, dedupe by content hash | Parallel ingest workers |
| LLM throughput | Provider rate limits respected via client-side limiter | Multi-key/multi-provider pools |

Primary bottlenecks to expect: LLM latency (sequential agent steps), sandbox slots, and embedding throughput on first ingest.

---

## 17. Cost model

Cost per task = sum over LLM calls (tokens x price per model tier) + rerank cost + sandbox compute.

Controls:
- Per-task dollar budget enforced in the graph.
- Small model for planning/rewrite; strongest model only for patching.
- Rerank only top-N; cache embeddings by content hash; cache repo map per snapshot.
- Cache identical tool results within a task.
- Report **cost per resolved task** (total cost over successful fixes), not just cost per attempt.

---

## 18. Architecture decision records (ADRs)

| ID | Decision | Alternatives considered | Rationale |
|---|---|---|---|
| ADR-1 | LangGraph state machine for the agent | Free-form ReAct loop; custom orchestrator | Explicit transitions, durable checkpoints, native interrupts for HITL |
| ADR-2 | Postgres for relational + vector + lexical | Dedicated vector DB | One store to operate; hybrid queries and filters in SQL; adequate scale for the corpus |
| ADR-3 | Function-level chunking via AST/tree-sitter | Fixed-size text chunks | Code semantics align to symbols; enables symbol-level metrics and citations |
| ADR-4 | MCP server for tools | In-process tool functions | Protocol boundary forces clean schemas, permits reuse by other clients |
| ADR-5 | Policy enforcement as code at a single chokepoint | Prompt-based instructions | Guarantees hold even if the model is manipulated |
| ADR-6 | Docker sandbox with separate runner service | Run tests in worker process | Isolates untrusted code; avoids exposing Docker socket to general workers |
| ADR-7 | Human approval before any write | Auto-apply when tests pass | Passing tests do not prove a patch is safe or correct |
| ADR-8 | Injected-bug tasks for fix evaluation | Real issue tracker tasks | Objective, cheap, reproducible ground truth; real issues are a stretch goal |
| ADR-9 | Celery + Redis for execution | Temporal, in-process async | Already familiar; sufficient with lease and checkpoint design (Temporal is the upgrade path) |
| ADR-10 | Cross-encoder reranker | Skip rerank; LLM rerank only | Measure benefit/cost directly; LLM rerank kept as ablation |

---

## 19. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Scope too large for 1 week | High | High | Cut features not evaluation; keep nice-to-haves out |
| Sandbox setup consumes time | Medium | High | Prebuild dependency images; start with 2 small repos |
| Injected bugs too easy/hard | Medium | Medium | Calibrate difficulty; log per-bug resolve rates |
| Agent variance hides improvements | High | Medium | Repeated runs, report spread, paired comparisons |
| Judge unreliable | Medium | Medium | Hand-label 30, measure agreement, prefer deterministic checks |
| Provider rate limits during eval | Medium | Medium | Client limiter, caching in eval, run concurrency caps |
| Test flakiness | Medium | Medium | Run baseline multiple times; exclude flaky tests from ground truth |

---

## 20. Open questions
1. Reranker choice: local cross-encoder on CPU vs hosted API (decide by measured latency/benefit).
2. Embedding model choice and dimension (decide by retrieval ablation).
3. Approval UX in v1: API-only vs minimal CLI prompt.
4. Whether to include caller/callee expansion in v1 (default: no).
5. Retention window for checkpoints and logs.

---

## 21. Mapping to the 7-day plan

| Day | HLD components delivered |
|---|---|
| 1 | Corpus, task sets, bug injector, eval runner, schema skeleton |
| 2 | Ingestion, hybrid retrieval, rerank, rewrite, retrieval ablation |
| 3 | MCP tool server, sandbox runner, baseline graph and baseline score |
| 4 | Checkpointing, approval gate, resume, budgets, loop detection |
| 5 | Guardrails, patch validator, adversarial and failure-injection suites |
| 6 | Trajectory metrics, consistency runs, judge calibration, cost tuning |
| 7 | Deployment, nightly eval, README with ablations and failure taxonomy |
