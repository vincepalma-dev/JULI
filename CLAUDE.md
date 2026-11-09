# JULI — project rules

JULI = **Jolly Universe of Little Intelligences**. The full build plan, current status and verified model data are in [docs/PLAN.md](docs/PLAN.md). Read it before starting work.

## Naming

- Never write anything about where the name JULI comes from.
- Never reference this project's previous name anywhere: code, comments, docs, commit messages, branch names or remotes. Before each commit, a repo-wide case-insensitive search for the old name must return nothing.

## Workflow

- One **stacked PR per phase**: each phase branch is created from the previous phase's branch, and its PR targets that branch. CodeRabbit reviews every PR.
- Before every commit: run the project's checks, stage, run `gitleaks git --staged`, then commit in a separate command. Never use `--no-verify`.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. End each PR body with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Repo: `github.com/vincepalma-dev/JULI` (private).

## Engineering

- Use our own lean agent engine (no AutoGen or other agent frameworks), plus Ollama and any OpenAI-compatible endpoint for local models.
- Don't add a tool-loop/hooks/skills "harness" layer unless the user asks for one.
- Never copy, adapt or read proprietary or leaked source code into this project.
- Keep it simple and flat. Add no dependency without a concrete need.
- Backend: Python ≥3.10, FastAPI, SQLite. Frontend: Vue 3 + Vite + Tailwind 3. SVG icons only, never emojis in the UI.
- Secrets live only in the OS keychain (`keyring`) or `.env`. Never in `settings.json`, never in logs.
