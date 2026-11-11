# JULI

**Jolly Universe of Little Intelligences.** *Understand. Learn. Improve.*

JULI is a little universe of AI helpers: a local-first crew of agents that builds software on your own machine. A Planner, Coder, Reviewer, Tester and Documenter work through your task together. They share one plan, feed review and test results back into the next pass, and write real files you can open, diff, zip or commit.

Run it entirely on-device with local models, or bring your own cloud API keys. You choose, per agent.

## What makes JULI different

- **Bring your own LLM.** Use on-device models through [Ollama](https://ollama.com), any OpenAI-compatible local server (LM Studio, llama.cpp, vLLM), or cloud providers with your own key.
- **Hardware-aware model catalogue.** JULI checks your RAM, GPU and free disk space. Models your machine can't run are greyed out with the reason, e.g. "needs 18 GB, you have 16 GB".
- **Speed measured on your machine.** After a download, JULI benchmarks the model on your hardware and shows real tokens per second.
- **Auto-Crew.** One click picks the best model for each agent role that fits your machine.
- **Privacy Mode.** Guarantees nothing leaves your device. It's enforced in the code that calls models, not just hidden in the UI.
- **No token limits.** JULI never caps your usage. Local models get the largest context window your memory allows. Cloud spending caps are optional and off by default.
- **API key guardrails.** Keys are checked when you save them, you get "running low" warnings, and a run pauses (instead of crashing) when a key runs out of credit, so you can switch models and resume.
- **Real files, real terminal.** Generated code lands in a file tree with a diff view. A built-in terminal works like an IDE's, and agent commands ask for your approval.

## Requirements

- **Python 3.10** or later.
- **Node.js 20.19** or later, to build the dashboard (once, on first start).
- **Optional:**
  - [Ollama](https://ollama.com), for on-device models.
  - Docker, for the sandbox that lets safe test commands run without asking.

## Get started

```bash
git clone https://github.com/vincepalma-dev/JULI.git
cd JULI
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS and Linux: source .venv/bin/activate
pip install -e .
juli serve
```

`juli serve` builds the dashboard the first time, then opens it at `http://127.0.0.1:8000` with a fresh session token in the link. On Windows, `start-juli.bat` does the same after the install.

The first run uses a local crew (every agent on `ollama:qwen3:8b`), so it needs no API keys. In the dashboard:

- **Models:** see what your machine can run, download a model, and benchmark it.
- **Crew:** pick a model per agent, or let Auto-Crew choose.
- **Settings:** add cloud API keys.

The keys go to your OS keychain. On machines without one, copy `.env.example` to `.env` and fill it in.

### Command line

Everything the dashboard does is also on the `juli` command, for example:

```bash
juli run "a CLI that converts CSV to JSON"   # run the crew on a task
juli hardware                                # what this machine can run
juli auto-crew --apply                       # pick a local model per agent
juli mode privacy                            # all local; nothing leaves the machine
juli models --help                           # downloads, benchmarks and the catalogue
```

Run `juli --help` for the full list.

### Where your data lives

- Settings, run history and each project's files are kept in `./data`, or in the folder that `JULI_DATA_DIR` names.
- API keys are kept in the OS keychain, never in `./data`.
- Voice is optional: `pip install -e ".[voice]"`. Voice input uses Google's online speech recognition, and JULI tells you before it listens.

## Security

JULI is built for one person on one machine:

- It listens on `127.0.0.1` only.
- Every request needs the session token from the launch link.
- Agent commands ask before they run, unless they're plain test commands inside the Docker sandbox.

See [SECURITY.md](SECURITY.md) for the threat model and how to report a vulnerability.

## Development

```bash
pip install -e ".[dev]"
pre-commit install          # ruff and gitleaks on every commit; needs gitleaks on PATH
cd frontend && npm install
```

`python run.py` starts the API with the Vite dev server on `http://localhost:3000`, which reloads the dashboard as you edit it.

CI runs these checks; run them before you open a pull request:

| Area | Commands |
|---|---|
| Python | `ruff check .`, `ruff format --check .`, `mypy juli`, `pytest --cov` |
| Dashboard (in `frontend/`) | `npm run lint`, `npm run test:coverage`, `npm run build` |
| End to end (in `frontend/`) | `npm run build`, then `npm run e2e` |
| Secrets | `gitleaks git` |

The end-to-end tests drive the built dashboard in Chromium against the real API and a fake model server (`frontend/e2e/`). Install the browser once with `npx playwright install chromium`. The sandbox test runs only when Docker has the `ubuntu:24.04` image.

A nightly workflow downloads a small real model with Ollama, benchmarks it and runs a local crew on it.

## Roadmap

| Phase | Scope |
|---|---|
| 1 | Baseline codebase under the JULI name |
| 2 | Security foundations: local-only binding, session token, OS keychain for API keys, validation, security headers |
| 3 | Lean agent engine and multi-provider streaming, cost meter, budget cap, API key guardrails |
| 4 | On-device LLMs: hardware detection, catalogue with fit checks, Ollama downloads, benchmarks, Auto-Crew, Privacy Mode |
| 5 | Artifact workspace, IDE-style terminal, approvable agent commands |
| 6 | Dashboard UI for all of the above |
| 7 | Tooling: tests, linting, type checks, CI, secret scanning, docs |
| 8 | Agent harness: tools and MCP (next) |

## Credits

- The Juli mascot art is original work made for JULI and released under the MIT License, like the rest of the repository. See [frontend/public/mascot/LICENSE.md](frontend/public/mascot/LICENSE.md).
- Inter and JetBrains Mono fonts are self-hosted through [Fontsource](https://fontsource.org), under the SIL Open Font License.

## History

JULI is a rebuild of [Jarvis.AI](https://github.com/vincepalma-dev/Jarvis.AI).

## License

[MIT](LICENSE)
