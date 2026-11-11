# Security

## Reporting a vulnerability

Please report security issues privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. Don't open a public issue or pull request for a vulnerability.

Include what you found, how to reproduce it, and what an attacker could do with it. Fixes land on `main`; there are no maintained release branches yet.

## What JULI is, and who it protects against

JULI is a **single-user app that runs on your own machine**. The server and the dashboard run on the same computer, for the person who started them. It isn't built to be hosted for other people or exposed to a network.

What it protects:

- **Your API keys**, which can spend your money.
- **Your machine**, since agents propose commands and write code that test runners execute.
- **Your code and prompts**, which leave the machine only when you choose a cloud model.

The threats it's designed for:

- other devices on your network;
- websites open in your browser, which can send requests to `localhost`;
- model output, which is untrusted: a model can be wrong, or steered by text it reads (prompt injection).

## How it's protected

### Local only

- The server binds `127.0.0.1`. Starting it with another `--host` prints a warning, because anyone who can reach the port and get the token can run agents on your machine.
- In production, FastAPI serves the dashboard and the API from one origin. In development, the Vite dev server proxies to the API. Neither enables CORS.

### Session token

- Each launch generates a fresh random token (`secrets.token_urlsafe(32)`). The launcher passes it to the server in the `JULI_TOKEN` environment variable, and the server refuses to start without one.
- The token is never printed or logged unless you ask for the link (`--show-link`). The browser gets it in the URL fragment (`/#token=…`), which never reaches the server or its logs. The dashboard moves it into `sessionStorage` and removes it from the address bar.
- Every `/api` route except `GET /api/health` needs `Authorization: Bearer <token>`, compared in constant time.
- The WebSocket's first message must carry the token within 5 seconds, or the socket is closed (4401). Its `Origin` must be on the allowlist (`JULI_ALLOWED_ORIGINS`; default: localhost and 127.0.0.1 on ports 3000 and 8000), or the socket is closed (4403).
- Auth is header-only and there are no cookies, so cross-site request forgery doesn't apply.

### Requests

- **Validation:** every request body has a strict schema with length and range limits.
- **Rate limits:** a per-client sliding window, tightest on key saves and task starts.
- **Headers:** every response sends `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and `X-Frame-Options: DENY`.
- **Content Security Policy:** API responses send `default-src 'none'; frame-ancestors 'none'`. The dashboard's policy allows only its own scripts, styles, fonts, images and WebSockets.
- **HTTPS:** HSTS is sent only over https.
- **API docs:** off unless `JULI_DEBUG=1`.

### API keys

- Keys live in the OS keychain (service `juli`), or in a `.env` file on machines without one. They're never written to `settings.json`, and never logged. The dashboard only ever shows the last four characters.
- The server never puts keys into its own environment. The terminal and agent commands run with the session token and every `*_API_KEY` variable removed.

### Agent commands and the Docker sandbox

Agents propose commands in ` ```bash run ` blocks. A command on the test and lint allowlist (`pytest`, `npm test`, `ruff` …) isn't trusted for that reason alone, because test runners execute code the agents wrote: `conftest.py`, a `package.json` test script, build scripts. A command runs without asking only when **all** of these hold:

1. it starts with an allowlisted prefix;
2. it contains no shell metacharacters: `;`, `&`, `|`, a backtick, `$`, `<`, `>` or a line break;
3. the Docker sandbox is enabled and Docker is running.

Every other command asks you to approve or deny it and shows the exact text. With the sandbox off, that's every command.

The sandbox runs each command in a throwaway container with:

- the project's workspace as the only mount, and its `.git` read-only;
- no network;
- no host environment variables;
- all capabilities dropped and `no-new-privileges`;
- a read-only root filesystem;
- limits on memory and processes, plus a timeout.

A container isn't as strong a boundary as a virtual machine; treat the sandbox as a strong guard rail, not a guarantee.

### Agent tools and MCP servers

Agents with tool calling get tools by role. The Planner and follow-up answers only read; the Reviewer can also run commands, but not write files. Every tool works inside the project's workspace through the same path guard as file blocks, and `run_command` goes through the command rules above. The role check runs again when a tool is called, whatever name the model asks for.

Tool results (file contents, command output, MCP answers) are untrusted input. They go back to the model as tool results and can't change approvals, the sandbox, Privacy Mode or keys.

MCP servers are programs or URLs you add in Settings:

- a program server runs with the same stripped environment as agent commands (no JULI variables, no API keys), or in the Docker sandbox when you turn that on for it;
- a server's token lives in the keychain, never in `settings.json`; a program server gets it as the environment variable you name, and a sandboxed one gets it without the token appearing in the `docker` command line;
- every MCP tool call shows the server, the tool and the exact arguments and asks Approve/Deny, unless you trust that tool **and** its server is sandboxed or reached over HTTP; a server running on this machine outside the sandbox always asks;
- in Privacy Mode, only sandboxed program servers and HTTP servers on this machine or the LAN start; any other server is left out of the run with a notice.

A server you add runs code you chose to run; JULI can't make an untrustworthy server safe.

Loop guards: each agent turn has a limit on tool rounds (25 by default), a reply runs at most 8 tool calls, an identical call is refused the third time unless something changed in between, and handoffs are limited per run and between any two agents. The token and budget caps count every model call of a tool loop, and Stop is checked between tool calls.

### Files the agents write

Generated files are written only inside the project's workspace (`data/workspace/<project>/`). Every path is resolved and refused if it would land outside. Pushing a commit to a remote always asks first.

### Privacy Mode

Privacy Mode is enforced in the code that calls models, not in the dashboard. With it on, any call to a provider whose host isn't local (localhost, loopback or a private LAN address) is refused. In Hybrid and Cloud modes, your prompts and code go to the providers you picked.

Voice input uses Google's online speech recognition, and JULI says so before it listens.

## Out of scope

- Anyone or anything already running as your OS user. Malware, or another program in your account, can read your keychain, your `.env` and the server's environment, which holds the session token.
- Exposing JULI to a network with `--host`, or hosting it for other people.
- The built-in terminal. It's your own shell on your machine, with the same rights as you.
- Commands and tool calls you approve, and MCP servers you add or trust. Read them first.

## Dependencies

CI scans the whole git history for secrets (gitleaks) and fails on any high-severity advisory in the packages the dashboard ships (`npm audit --omit=dev`).

Known advisories in **development tools only**, which aren't part of what ships:

- **minimatch and glob** (used by ESLint and `@vue/test-utils`): denial of service from attacker-written glob patterns. The only patterns are our own config.
