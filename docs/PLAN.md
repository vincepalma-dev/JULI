# JULI build plan

**JULI = Jolly Universe of Little Intelligences.** Motto: *Understand. Learn. Improve.*

JULI is a local-first crew of AI agents (Planner, Coder, Reviewer, Tester, Documenter) that builds software on the user's own machine. It works with on-device models (Ollama, or any OpenAI-compatible local server) and cloud models (the user's own API keys), chosen per agent.

What sets it apart from other local AI workspaces:

- **Auto-Crew:** picks a model per agent role that fits the machine.
- **Privacy Mode:** enforced in the code that calls models, not just in the UI.
- **Benchmarks on the user's hardware:** model speed is measured, not guessed.
- **Real files:** generated code lands in a file tree.
- **IDE-style terminal:** with approvable agent commands.

---

## Status (as of 2026-11-09)

| Item | State |
|---|---|
| Repo | `github.com/vincepalma-dev/JULI` (private), default branch `main` |
| `main` | `2f3cc63`: README and `.gitignore` only |
| Phase 1 | **PR #1 open** (`phase-1-baseline` → `main`): the baseline code renamed to JULI, MIT LICENSE, `.gitattributes`. Behaviour unchanged on purpose. |
| Phase 2 | **Done** on `phase-2-security` (stacked on `phase-1-baseline`): package restructure, token auth, keychain, validation, headers, rate limits, thread-safe bus, run history, TTS fix, self-hosted fonts, 68 tests. |
| Phases 3–7 | Not started |

**Workflow:**

- **One stacked PR per phase.** Each phase branch is based on the previous phase's branch, and its PR targets that branch, so every diff shows only that phase. CodeRabbit reviews each PR.
- **Before each commit:** run the project's checks, stage, run `gitleaks git --staged`, then commit in a separate command.
- **Commit trailer:** `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **PR body ends with:** `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

**Environment on the dev machine:**

- Python 3.10.11. Node 24.14, npm 11.9.
- `.venv` exists with fastapi, uvicorn, httpx, openai, anthropic, typer, rich, psutil, keyring, python-dotenv, pywinpty, pytest, mypy and ruff installed.
- `frontend/node_modules` is installed. ruff 0.16 and gitleaks 8.30 are on PATH.
- Ollama is installed but not running. There's no NVIDIA GPU (`nvidia-smi` is missing). Docker 29.9 is present.

---

## Known issues in the baseline (each fixed in the listed phase)

**Critical**

1. **No authentication; the whole LAN can reach it.** The backend binds `0.0.0.0` with no auth, CORS is `*` with credentials, and LLM-written code runs on the host (`use_docker: False`). Anyone on the LAN can run code. **Phase 2**
2. **Plain-text API keys** in `settings.json`, and the server mutates `os.environ` when keys are saved. **Phase 2**
3. **Windows TTS injection.** It builds a PowerShell string from LLM output (`agents/utils.py`). **Phase 2**
4. **`--push` runs `git add .`** in the current folder (`cli/main.py`). **Phase 3**

**High**

5. **Settings are never applied.** Settings-panel choices (model, prompt, custom agents) never reach the agents, which always use the hardcoded `SYSTEM_PROMPTS` / `AGENT_MODEL_MAP`. **Phase 3**
6. **Typo `"DocsDigram"`** in `agents/config.py` sends the Docs agent to the wrong model. **Phase 3**
7. **Starting a task deletes the project's stored history** (`clear_history()`). **Phase 2**
8. **Thread-unsafe queue.** A worker thread calls `put_nowait` on an `asyncio.Queue`. **Phase 2**
9. **Retired model IDs; `pyautogen 0.2` is a dead end.** **Phase 3**
10. **No stop button; mode ignored; `--review` reviews nothing.** The UI always sends `mode: 'full'`. **Phases 3 and 6**
11. **No validation.** Errors return HTTP 200 `{"error":...}`, there's no validation (`payload: dict`, unbounded `max_round`), and the WebSocket `start_task` path skips all checks. **Phase 2**
12. **Frontend wiring bugs:** the agent list is hardcoded, the sidebar never loads saved settings, the WebSocket URL is hardcoded to `ws://host:8000`, history is sent twice, status is parsed from message text, and "remove provider" doesn't delete the key server-side. **Phase 6**

**Medium**

13. **No tooling:** no tests, linter, type checker, CI, `pyproject.toml` or SECURITY.md. **Phase 7**
14. **Reliability:** non-atomic settings writes, timestamps without time zones, synchronous SQLite inside async routes, and the message bus importing `backend` (inverted layers). **Phases 2 and 3**
15. **Privacy:** Google Fonts loads from a CDN (IP leak), and cloud speech-to-text has no disclosure. **Phase 2**

---

## Target architecture

`agents/`, `backend/` and `cli/` merge into one flat `juli/` package. The frontend stays on Vue 3 + Vite + Tailwind 3.

```
juli/
  __init__.py    __version__
  config.py      paths (DATA_DIR = $JULI_DATA_DIR or ./data), settings.json in data/ (no secrets), atomic save, defaults
  keystore.py    OS keychain via `keyring` (service "juli"), env-var fallback, key_hint() -> "••••abcd"
  store.py       SQLite (WAL): projects, runs, messages, benchmarks
  bus.py         thread-safe event bus (loop.call_soon_threadsafe); optional persister callback
  providers.py   streaming: OpenAI-compatible | Anthropic | Ollama-native; usage+cost; privacy guard; KeyProblem
  providers.json presets, base URLs, $/MTok prices
  roles.py       default crew roles + prompts
  engine.py      pipeline: Plan -> Code<->Review loop -> Test -> Docs
  local/hardware.py, local/catalogue.py, local/catalogue.json, local/ollama.py
  workspace.py   artifact extraction, file tree, diff, zip, git commit to branch
  terminal.py    PTY sessions (pywinpty on Windows, ptyprocess on POSIX)
  voice.py       TTS/STT (injection fixed, STT disclosed)
  api/           app.py, security.py, models.py, routers (tasks, projects, settings, providers, local, workspace, terminal)
  cli.py         Typer CLI, entry point `juli`
```

**Database** (kept flat):

- `projects`(id, name, created_at, updated_at)
- `runs`(id, project_id, prompt, mode, status, crew_json, tokens_in, tokens_out, cost_usd, started_at, ended_at)
- `messages`(id, project_id, run_id, agent, content, type, model, tokens_in, tokens_out, created_at)
- `benchmarks`(model_ref, tok_per_sec, prefill_tok_per_sec, hw_fingerprint, measured_at)

Each task creates a new run row, so history is never deleted. Deleting a project cascades.

---

## Phase 2: Security and foundations (done)

Implementation notes: the `messages` table keeps its existing column names (`agent_name`, `timestamp`, `message_type`) and gains `run_id`, `model`, `tokens_in`, `tokens_out` in place, so existing databases migrate without rewriting rows. The server is started with `uvicorn --factory juli.api.app:create_app`.

To keep the diff readable, the package restructure happens here: `backend/` moves to `juli/api/`, `agents/message_bus.py` to `juli/bus.py`, `backend/projects_db.py` to `juli/store.py`. `agents/` and `cli/` stay until Phase 3, with their imports updated.

1. **Bind to localhost.** `run.py` / launcher bind `127.0.0.1`. A `--host` override prints a warning.
2. **Session token.**
   - The launcher generates `secrets.token_urlsafe(32)`, passes it to uvicorn via the `JULI_TOKEN` env var, and opens `http://localhost:3000/#token=<token>` in the browser.
   - The token is never printed or logged. The launcher prints the link only when asked (`--show-link`). The server refuses to start if `JULI_TOKEN` is unset, rather than generating and printing one. The `#token=` fragment never reaches server logs.
   - All `/api/*` routes except `GET /api/health` require `Authorization: Bearer <token>`, compared with `secrets.compare_digest`. Header-only auth means CSRF doesn't apply, so no CSRF tokens.
3. **WebSocket auth.**
   - The first client message must be `{"type":"auth","token":...}` within 5 s, otherwise close with code 4401.
   - Check `Origin` against `JULI_ALLOWED_ORIGINS` (default: localhost and 127.0.0.1 on ports 3000 and 8000).
   - Remove the WebSocket `start_task` path; tasks start only via REST.
4. **CORS.** Remove `CORSMiddleware`. The browser reaches the API through the Vite proxy in dev and the same origin in production.
5. **Security headers** on every response:
   - `X-Content-Type-Options: nosniff`
   - `Referrer-Policy: no-referrer`
   - `X-Frame-Options: DENY`
   - `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` on API responses
   - HSTS only when the scheme is https
   - Disable `/docs` unless `JULI_DEBUG=1`.
6. **Rate limiting.** An in-memory sliding window keyed by client and route group. Mutating routes 60/min, `POST` task 10/min, key saves 10/min. Returns 429 with `Retry-After`.
7. **Validation.** Pydantic models and `HTTPException` (404/409/422) everywhere:
   - `TaskRequest`: prompt 1–20000 chars, `mode: Literal['full','plan','code','review']`, `max_round` 1–50, `project_id` required.
   - Project name: 1–100 chars.
   - Agent name: `^[A-Za-z][A-Za-z0-9_]{0,39}$`. Color: `^#[0-9a-fA-F]{6}$`. Prompt ≤ 8000. Job title ≤ 80.
   - Provider id: `^[a-z][a-z0-9_]{0,31}$`. Key ≤ 500.
8. **Keystore.**
   - Keys move to the OS keychain; settings only record which providers exist.
   - On first start, move any non-empty keys from a legacy `settings.json` into the keychain and blank them.
   - `agents/config.py` reads keys via `keystore.get_key()` (env fallback) instead of `os.environ`. The server never writes `os.environ`.
   - Add `DELETE /api/settings/keys/{provider}`.
   - If the keychain is unavailable, return 503 with guidance to use `.env`.
   - Commit a `.env.example`.
9. **History.** Starting a task creates a `runs` row. `clear_history` only clears the in-memory view and never deletes from the DB.
10. **Thread-safe bus.** `subscribe_async()` captures the running loop. `publish()` uses `loop.call_soon_threadsafe` and drops the event if the queue is full. Persistence happens through a persister callback registered by the API at startup, so the bus no longer imports the store.
11. **Atomic settings.** `data/settings.json`, written to a temp file then `os.replace`, encoded UTF-8.
12. **Synchronous routes.** Routes that touch SQLite become plain `def`, so FastAPI runs them in its threadpool.
13. **TTS fix.** Pass text through the `JULI_TTS_TEXT` env var into a constant PowerShell script: `$s.Speak($env:JULI_TTS_TEXT)`. No string interpolation.
14. **STT disclosure.** Before listening, print a clear notice that audio goes to Google's speech service.
15. **Fonts.** Self-host via `@fontsource/inter` and `@fontsource/jetbrains-mono`, and remove the Google Fonts links from `index.html`.
16. **Frontend plumbing:**
    - `src/api.js`: read the `#token=` hash into `sessionStorage['juli-token']` and strip the hash. `apiFetch()` adds the Bearer header and throws on `!ok` with the server's `detail`.
    - Replace every raw `fetch('/api…')`.
    - `useWebSocket` uses `${ws|wss}://${location.host}/ws` (Vite proxy) and sends the auth message on open.
    - Show a "no session" notice when the token is missing.
    - Send `project_id` when starting a task.
17. **Tests** (pytest + FastAPI TestClient):
    - 401 without the token; health stays open.
    - WebSocket rejected without auth or with a bad Origin.
    - Security headers present.
    - 429 from the rate limiter.
    - 422 on invalid input.
    - History survives a second task.
    - The bus delivers events published from another thread.
    - The keystore works with a fake keyring backend.
    - The `agents.orchestrator` import is lazy inside the task route, so tests don't need `pyautogen`.

## Phase 3: Lean engine, providers, API key guardrails

**`providers.py`**, with `stream(model_ref, messages, *, privacy) -> iterator of deltas` plus final usage:

- **OpenAI-compatible** via the `openai` SDK (`max_retries=0`, `with_raw_response` for headers, `stream_options={"include_usage": True}`). Covers OpenAI, Gemini, OpenRouter, Groq, DeepSeek, Mistral, xAI and custom endpoints.
- **Anthropic** via the `anthropic` SDK's `messages.stream`.
- **Ollama native** `POST /api/chat` via httpx (NDJSON), with `options.num_ctx`.
- **Model refs** look like `provider:model`, e.g. `ollama:qwen3:8b`, `openai:gpt-6.1-sol`, `anthropic:claude-sonnet-5-5`.
- **Privacy guard:** a non-local provider raises `PrivacyViolation` when privacy is on. A provider is local if its host is localhost, 127.x, ::1 or a private LAN range.

**API key guardrails** live in a pure, unit-tested `classify_error(kind, status, body, headers) -> KeyProblem | None`:

| Provider | Response | Meaning |
|---|---|---|
| OpenAI | 401 | invalid |
| OpenAI | 429 with `insufficient_quota` | out of credit |
| OpenAI | other 429 | rate limit |
| Anthropic | 401/403 | invalid |
| Anthropic | "credit balance is too low" | out of credit |
| Anthropic | 429 | rate limit |
| Anthropic | 529 | overloaded |
| Gemini | 429 `RESOURCE_EXHAUSTED` with "exceeded your current quota" | out of credit |
| Gemini | other 429 `RESOURCE_EXHAUSTED` | rate limit |

- **Check on save:** a cheap call (`models.list`; Ollama `/api/version`) gives each key a health badge.
- **Low warning:** read `x-ratelimit-remaining-*` / `anthropic-ratelimit-*-remaining` and warn when less than 10% remains.
- **Optional monthly allowance** per key, tracked locally: warn at 80%, block new runs at 100% (overridable).
- **OpenRouter:** the real balance comes from `GET https://openrouter.ai/api/v1/key`.
- **Rate limits:** automatic backoff honouring `Retry-After`, waiting at most about 60 s.
- **Out of credit or invalid:** the run **pauses** with a decision event (switch model and resume, or stop). An optional auto-fallback switches to the Auto-Crew local model, and never goes to the cloud in Privacy Mode.
- **Logging:** keys are never logged; only the provider name and last 4 characters are shown.

**`engine.py`** replaces AutoGen:

- **Pipeline:** Plan (optional approval checkpoint) → Code⇄Review (the reviewer ends with `VERDICT: APPROVED` or `VERDICT: CHANGES REQUESTED`; max cycles default 3, a loop guard, not a token limit) → custom roles → Test → Docs.
- **Crew** comes from settings (fixes #5). Modes select the steps. `review` reviews the latest run's artifacts.
- **Cancel event** checked between chunks.
- **Budget cap:** optional, off by default, cloud cost only.
- **Events:** chunks plus a final message per agent turn. One run row per task.
- **Cleanup:** removes `pyautogen`, `agents/`, `main_autogen.py`. The CLI moves to `juli/cli.py` (`juli` entry point). The `--push` behaviour of `git add .` in the current folder is removed (fixes #4).

**Verified model presets** (official pricing pages, 2026-11-09; $ per MTok input/output, short context):

| Provider | Model | In / Out |
|---|---|---|
| OpenAI | `gpt-6-astra` | 10 / 50 |
| OpenAI | `gpt-6.1-sol` | 2 / 10 |
| OpenAI | `gpt-6.1-terra` | 1 / 5 |
| OpenAI | `gpt-6-luna` | 0.10 / 0.50 |
| Anthropic | `claude-opus-5-5` | 4 / 20 |
| Anthropic | `claude-sonnet-5-5` | 2 / 10 |
| Anthropic | `claude-haiku-5-5` | 0.10 / 0.50 (prompts ≤100k; 0.50 / 2.50 above) |
| Gemini | `gemini-4-argon` | 4 / 20 (standard from Dec 1; $2 / $10 intro until Nov 30) |
| Gemini | `gemini-3.8-flash` | 1.50 / 7.50 (standard from Jan 1; $0.75 / $3.75 intro) |
| Gemini | `gemini-3.5-flash-lite` | 0.30 / 2.50 |

The Gemini rows use the **standard** rates on purpose: overestimating cost is the safe side for budget caps.

**Base URLs:**

- Gemini: `https://generativelanguage.googleapis.com/v1beta/openai/`
- OpenRouter: `https://openrouter.ai/api/v1`
- Groq: `https://api.groq.com/openai/v1`
- DeepSeek: `https://api.deepseek.com/v1`
- Mistral: `https://api.mistral.ai/v1`
- xAI: `https://api.x.ai/v1`
- Ollama: `http://localhost:11434`

Users can type any model ID. A model with no known price shows tokens only.

## Phase 4: On-device LLMs

**`local/hardware.py`** detects:

- RAM via psutil, CPU, and disk free on the Ollama models drive.
- **GPU:**
  - NVIDIA: `nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits`.
  - Apple Silicon: unified memory × 0.7.
  - AMD on Linux: `rocm-smi`.
  - Windows: `winreg` reads `HardwareInformation.qwMemorySize` under `HKLM\SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\000N`. WMI `AdapterRAM` is not used because it caps at 4 GB.
  - Intel and other integrated GPUs fall back to CPU.
- A hardware fingerprint.

**Fit check** (a pure function):

- `need(ctx) = size_gb + kv_gb(ctx) + 0.6`.
- `kv_gb` uses the entry's `kv_mb_per_token` if present, otherwise ≈ `0.125 * (params_b/8)**0.7` MB/token.
- **Budgets:**
  - Discrete GPU: GPU = VRAM total × 0.95; Total = VRAM + RAM total × 0.75.
  - Apple Silicon (unified memory, one pool): GPU = RAM × 0.7; Total = RAM × 0.75. VRAM is not added on top.
  - CPU only: GPU = 0; Total = RAM total × 0.75.
- **Tiers:**
  - `great` if `need(4096)` ≤ GPU budget.
  - `slow` if it fits the total budget.
  - Otherwise `cannot`, with a reason like "needs X GB, this machine has Y GB".
- A missing disk space blocks with its own reason.
- `num_ctx` = the largest of 4K…256K (capped at `context_max`) that fits the tier's budget.

**Catalogue** (sizes verified on ollama.com/library, 2026-11-09):

| Tag | Size | Context | License | Roles |
|---|---|---|---|---|
| `llama3.2:1b` | 1.3 GB | 128K | Llama 3.2 Community (accept) | docs |
| `llama3.2:3b` | 2.0 GB | 128K | Llama 3.2 Community (accept) | docs, general |
| `qwen3:1.7b` | 1.4 GB | 40K | Apache-2.0 | general |
| `qwen3:4b` | 2.5 GB | 256K | Apache-2.0 | general |
| `qwen3:8b` | 5.2 GB | 40K | Apache-2.0 | general, coder |
| `qwen3:14b` | 9.3 GB | 40K | Apache-2.0 | general, coder, reviewer |
| `qwen3:30b` (MoE a3b) | 19 GB | 256K | Apache-2.0 | general, planner |
| `qwen3:32b` | 20 GB | 40K | Apache-2.0 | general, reviewer |
| `qwen3-coder:30b` | 19 GB | 256K | Apache-2.0 | coder, reviewer, tester |
| `gemma3:1b` | 0.8 GB | 32K | Gemma terms (accept) | docs |
| `gemma3:4b` | 3.4 GB | 128K | Gemma terms (accept) | general, docs |
| `gemma3:12b` | 8.2 GB | 128K | Gemma terms (accept) | general |
| `gemma3:27b` | 17 GB | 128K | Gemma terms (accept) | general, planner |
| `gemma4:12b` | 8.0 GB | 256K | Gemma terms (accept; verify) | general |
| `gemma4:31b` | 20 GB | 256K | Gemma terms (accept; verify) | general, planner |
| `deepseek-r1:8b` | 5.2 GB | 128K | MIT | planner, reviewer |
| `deepseek-r1:14b` | 9.0 GB | 128K | MIT | planner, reviewer |
| `deepseek-r1:32b` | 20 GB | 128K | MIT | planner, reviewer |
| `gpt-oss:20b` | 14 GB | 128K | Apache-2.0 | planner, reviewer, coder |
| `gpt-oss:120b` | 65 GB | 128K | Apache-2.0 | planner, reviewer, coder |
| `devstral:24b` | 14 GB | 128K | Apache-2.0 | coder, tester |

The `gemma4` sizes are shown as ranges on Ollama; the upper bound is used.

**`local/ollama.py`:**

- `GET /api/version`, `/api/tags`, `/api/ps`.
- `POST /api/pull {model, stream:true}`: NDJSON progress `{status, total, completed}`, throttled to about 4 events/s. Resumable and cancellable.
- `DELETE /api/delete`.
- **Benchmark:** `POST /api/generate` (non-streaming, `num_predict` 128), computing tok/s = `eval_count / (eval_duration/1e9)` plus prefill speed, stored in `benchmarks`.

**Bring your own LLM:**

- **Hugging Face GGUF:** `GET https://huggingface.co/api/models/{repo}/tree/main` lists `.gguf` files with sizes. Shards are summed and the quant parsed from the filename; each gets a fit check, then is pulled as `hf.co/{repo}:{quant}`.
- **OpenAI-compatible endpoint:** test the connection and list `/v1/models`.
- **Cloud providers:** by key.

Restrictive or gated licenses require acceptance before download.

**Auto-Crew:** agents run one at a time, so each role's model only needs to fit on its own. For each role, pick the strongest model whose roles match, in the `great` tier (else `slow`). Ties go to installed models. If the downloads don't fit on disk, fall back to one shared model for all roles.

**Modes:** Privacy (all local, enforced in `providers.py`), Hybrid (Plan and Review in the cloud, the rest local), Cloud.

## Phase 5: Artifact workspace, IDE terminal, agent commands

**Workspace:**

- `data/workspace/<project_id>/` is the project's working tree, a git repo.
- The Coder emits ` ```lang path=src/app.py ` blocks. They're written with a path-traversal guard (resolve the path and require it to stay inside the root).
- Each run stores the before-images of the files it touches, for diffs.
- Endpoints: tree, file, unified diff, zip of the tree (excluding `.git`), and commit to branch `juli/run-<id>`. Pushing asks first.

**Terminal:**

- WebSocket `/ws/terminal`; the first message is `{token, project_id, cols, rows}`.
- PTY via pywinpty / ptyprocess, with the reader on a thread forwarded with `call_soon_threadsafe`.
- Shown in a bottom dock using `@xterm/xterm` + `@xterm/addon-fit`, with tabs: Terminal (the user's) and Agent (live agent commands).

**Agent commands:**

- Proposed in ` ```bash run ` blocks.
- An allowlisted prefix (`pytest`, `python -m pytest`, `npm test`, `npm run test`, `ruff`, `go test`, `cargo test`) is **not** enough to trust a command: test runners execute code the agents wrote (`conftest.py`, the `test` script in a generated `package.json`, build scripts).
- So a command runs automatically only when **all** of these hold:
  - it starts with an allowlisted prefix;
  - it contains no shell metacharacters (`; & | \` $ < >` or a newline);
  - the Docker sandbox is enabled: only the workspace mounted, no network, no host environment variables or secrets.
- Anything else, including every command when Docker is off, asks Approve/Deny and shows the exact command.
- Commands run in the workspace with a timeout. Failures go back to the Coder for one fix pass.

## Phase 6: Dashboard UI

- Load agents from settings; structured status; mode selector, Stop button, plan-approval and command-approval modals.
- `ModelsPanel` (Installed / Catalogue / Bring your own; hardware card; fit badges and greyed-out cards with reasons; download progress; benchmarks).
- `CrewBuilder` (Auto-Crew; Privacy / Hybrid / Cloud switch also in the TopBar).
- `WorkspacePanel`; `TerminalDock`; cost and token meter in `StatsBar` (local shows tok/s and $0).
- Key health badges, allowance settings, "running low" toasts, and an out-of-credit banner (switch / resume / stop).
- Production: FastAPI serves `frontend/dist` on one origin, port 8000. `juli serve` builds it if missing and opens `http://127.0.0.1:8000/#token=…`; `start-juli.bat` calls `.venv\Scripts\python -m juli serve`.
- SVG icons only, with `aria-label` on icon-only buttons.

## Phase 7: Tooling, CI, docs

- `pyproject.toml` (Python ≥3.10, `juli` script; `requirements.txt` removed).
- Python: ruff (lint and format), mypy, pytest.
- Frontend: ESLint (`eslint-plugin-vue`), Vitest + `@vue/test-utils`, an `npm audit` pass.
- `.pre-commit-config.yaml` (ruff + gitleaks); GitHub Actions CI (py lint/type/test, web lint/test/build, gitleaks).
- `SECURITY.md` (threat model: local-only, token, sandbox), `.env.example`, final README.

---

## Verification (end to end)

1. **All checks pass:** `ruff check`, `ruff format --check`, `mypy juli`, `pytest`, `npm run lint`, `npm run test`, `npm run build`, `gitleaks detect`.
2. **Launch and models:**
   - Launch and confirm the dashboard opens with the token.
   - The hardware card shows real RAM and GPU.
   - Oversized models are greyed out with reasons.
   - Pull the smallest model and see progress, then the benchmark tok/s.
3. **Local run:**
   - Run Auto-Crew, then a Privacy Mode run that executes fully on-device.
   - Files appear in the Workspace; diff and zip work.
   - Stop works mid-run.
4. **Terminal:** it runs commands, and agent commands show Approve/Deny.
5. **Cloud keys:**
   - The cost meter updates and a tiny budget cap stops the run.
   - A bad key shows "Invalid"; the allowance warns at 80% and blocks at 100%.
   - An out-of-credit key pauses the run and offers to switch to a local model.
6. **Network:** a request from another LAN machine is refused.
7. **Naming:** a repo-wide search for the project's previous name returns nothing.

## Legal and privacy flags (not legal advice)

- **Model licenses:** Llama and Gemma terms must be accepted before download; some models are gated.
- **Third-party transfers:** in Hybrid and Cloud modes, prompts and code go to third-party providers. Show this in the UI; Privacy Mode is the opt-out.
- **Hosting for others:** if JULI is ever hosted for other people, the Philippine Data Privacy Act (RA 10173) applies: privacy notice, a DPO, 72-hour breach notification, and possibly NPC registration. Have a Philippine lawyer review before any hosted launch.
- **Retention:** a setting (default "keep until deleted") plus a "delete all data" action.

## Roadmap (after this build)

- **Crew A/B:** run the same task with two crews and compare the results.
- **Run branching.**
- **Shareable crew presets.**
- **MCP tools.**
- **Bring-your-codebase retrieval.**
- **Local Whisper voice.**
- **Tagalog/Taglish UI.**
- **Tauri desktop installer.**
- **Docker images.**
- **Scheduled runs.**
