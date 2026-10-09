# RepoSage: Agentic Codebase Assistant

RepoSage is a service designed to help software engineers navigate, understand, and reliably repair codebases. It operates in two primary modes:

1. **QA Mode**: Answers technical questions about a repository (e.g., *"Where is retry backoff logic configured?"*) with deterministic, verifiable citations anchoring to exact file paths, line spans, and symbol qualnames.
2. **Fix Mode**: Investigates bug reports and failing tests, formulates minimal unified diff patches, **proves the patch by running tests in an isolated sandbox**, and applies changes only upon explicit Human-In-The-Loop (HITL) approval.

---

## 🏛️ Architecture Overview

The system is implemented as a checkpointed **LangGraph state machine** backed by PostgreSQL and Celery:

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

### Key Subsystems

- **API Layer (`src/reposage/api/`)**: FastAPI endpoints for repository registration (`/v1/repos`), task submissions (`/v1/tasks`), SSE event streaming (`/v1/tasks/{id}/events`), and HITL decisions (`/v1/tasks/{id}/approval`).
- **Ingestion & Hybrid Retrieval (`src/reposage/ingest/`, `src/reposage/retrieval/`)**: Symbol-level AST chunking, identifier expansion (camelCase and snake_case tokenization), vector similarity + FTS + trigram fusion via Reciprocal Rank Fusion (RRF), and cross-encoder reranking.
- **LLM Gateway (`src/reposage/llm/`)**: Resilient provider fallback chain (Anthropic, OpenAI, Bedrock, Stubs), circuit breaker, full-jitter exponential backoff, token-bucket rate limiter, and ledger cost accounting.
- **MCP Tool Server & Guardrails (`src/reposage/tools/`)**: Model Context Protocol (MCP) tool server protected by a single policy chokepoint that enforces path containment, safe selectors, and automatic secret redaction.
- **Isolated Sandbox (`src/reposage/sandbox/`)**: Ephemeral containerized test execution with `--network none`, read-only repo root, dropped capabilities, memory and CPU quotas, and read-only test trees to prevent test tampering.
- **Evaluation Harness (`src/reposage/evals/`)**: Synthetic bug injector, QA judge, trajectory metrics, and CLI runner (`reposage-eval`).

---

## 📁 Repository Layout

```text
reposage/
├── pyproject.toml                     # Package dependencies and project config
├── docker-compose.yml                 # PostgreSQL (+pgvector), Redis, API, Worker, Sandbox
├── Makefile                           # Development automation commands
├── gate.yaml                          # CI quality gate threshold rules
├── prompts/                           # Versioned and hashed prompt definitions
│   ├── plan.v1.md
│   ├── rewrite.v1.md
│   ├── explore.v1.md
│   ├── patch.v1.md
│   ├── answer.v1.md
│   └── judge_qa.v1.md
├── src/reposage/
│   ├── config.py                      # Pydantic Settings and budget ceilings
│   ├── api/                           # FastAPI REST routes and dependencies
│   ├── db/                            # SQLAlchemy ORM models and session manager
│   ├── ingest/                        # AST chunker, identifier expander, pipeline
│   ├── retrieval/                     # Hybrid search, RRF fusion, reranker, query rewriter
│   ├── llm/                           # Multi-provider gateway, circuit breaker, ledger
│   ├── tools/                         # MCP tool server, implementations, policy engine
│   ├── sandbox/                       # Runner service and isolated client
│   ├── agent/                         # LangGraph state machine, nodes, budget, patching
│   ├── workers/                       # Celery tasks and distributed lease manager
│   ├── observability/                 # Tracing, Prometheus metrics, JSON logging, secrets
│   └── evals/                         # Benchmark runner, synthetic bug injector, CLI
└── tests/
    ├── unit/                          # Chunker, policy, patch validator, budget, metrics
    ├── integration/                   # REST API, hybrid retrieval, agent workflows
    ├── adversarial/                   # Prompt injection, path traversal, test tampering
    └── chaos/                         # Worker crash-resume, lease recovery
```

---

## 🚀 Quick Start

### 1. Installation

Install dependencies using `uv`:

```bash
uv sync
```

### 2. Run Test Suite

Run unit, integration, adversarial, and chaos test suites:

```bash
uv run pytest -v tests/
```

### 3. Run Evaluation Benchmark CLI

Run evaluation suites, compare two experimental runs, or assert CI gates:

```bash
# Run retrieval benchmark
uv run python -m reposage.evals.cli run --suite retrieval_v1 --label baseline

# Compare two runs
uv run python -m reposage.evals.cli compare --a run12345678 --b run87654321

# Assert quality gate
uv run python -m reposage.evals.cli gate --suite fix_smoke --thresholds gate.yaml
```

### 4. Start Local Development Services

Start the FastAPI application:

```bash
uv run uvicorn reposage.api.main:app --reload --host 0.0.0.0 --port 8000
```

Start the Sandbox Runner service:

```bash
uv run uvicorn reposage.sandbox.runner_service:app --host 0.0.0.0 --port 9000
```

Or run the complete stack via Docker Compose:

```bash
docker-compose up -d
```

---

## 🔒 Security & Guardrails

- **Zero Unapproved Writes**: The `apply_patch` tool is never exposed to the agent model; patches are applied only after human approval.
- **Test Immutability**: The `PatchValidator` and sandbox overlays strictly reject and forbid modifications to test files or test runner configs (`conftest.py`, `pytest.ini`).
- **No-Network Sandbox**: Sandbox test containers run with `--network none`, non-root user (`10001:10001`), and dropped Linux capabilities.
- **Path Traversal Protection**: All filesystem inspection tools resolve canonical paths and deny any reference escaping the repository snapshot root.
- **Secret Redaction**: Prompts, traces, and tool outputs are scanned for high-entropy tokens and private key headers and redacted before persistence.
