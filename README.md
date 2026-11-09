# JULI

**Jolly Universe of Little Intelligences.** *Understand. Learn. Improve.*

JULI is a little universe of AI helpers: a local-first crew of agents that builds software on your own machine. A Planner, Coder, Reviewer, Tester and Documenter work through your task together. They share one plan, feed review and test results back into the next pass, and write real files you can open, diff, zip or commit.

Run it entirely on-device with local models, or bring your own cloud API keys. You choose, per agent.

> **Status:** under active development. Features land phase by phase, one pull request each. See [Roadmap](#roadmap).

## What makes JULI different

- **Bring your own LLM.** Use on-device models through [Ollama](https://ollama.com), any OpenAI-compatible local server (LM Studio, llama.cpp, vLLM), or cloud providers with your own key.
- **Hardware-aware model catalogue.** JULI checks your RAM, GPU and free disk space. Models your machine can't run are greyed out with the reason, e.g. "needs 18 GB, you have 16 GB".
- **Speed measured on your machine.** After a download, JULI benchmarks the model on your hardware and shows real tokens per second.
- **Auto-Crew.** One click picks the best model for each agent role that fits your machine.
- **Privacy Mode.** Guarantees nothing leaves your device. It's enforced in the code that calls models, not just hidden in the UI.
- **No token limits.** JULI never caps your usage. Local models get the largest context window your memory allows. Cloud spending caps are optional and off by default.
- **API key guardrails.** Keys are checked when you save them, you get "running low" warnings, and a run pauses (instead of crashing) when a key runs out of credit, so you can switch models and resume.
- **Real files, real terminal.** Generated code lands in a file tree with a diff view. A built-in terminal works like an IDE's, and agent commands ask for your approval.

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

## History

JULI is a rebuild of [Jarvis.AI](https://github.com/vincepalma-dev/Jarvis.AI).

## License

[MIT](LICENSE)
