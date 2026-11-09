"""
The default crew: built-in roles, their agents, prompts and models.

Every agent has a role. The engine fills the planner, coder, reviewer, tester
and docs steps with the first agent of that role; every other agent runs as a
custom role after the code is approved.
"""

ROLES = ("planner", "coder", "reviewer", "tester", "docs", "custom")

SYSTEM_PROMPTS = {
    "PlannerResearcher": (
        "You are the Planner & Researcher. "
        "Plan system architecture, break tasks into steps, research tools/libraries/APIs, "
        "and define tech stack decisions. Output structured markdown task plans. "
        "Specify which agent handles each task."
    ),
    "Coder": (
        "You are the Coder. Write clean, production-ready code in any language or framework "
        "the task requires (Python, JavaScript, TypeScript, Go, Rust, Java, C#, etc.). "
        "Support any stack: Django, FastAPI, Flask, Express, Next.js, Vue, React, Angular, "
        "mobile (React Native, Flutter), and more. Follow the plan exactly. "
        "Use proper typing, docs, error handling. Output complete, runnable code — never placeholders."
    ),
    "ReviewerSecurity": (
        "You are the Reviewer & Security agent. "
        "Review code for bugs, anti-patterns, and performance issues. "
        "Check for SQL injection, XSS, CSRF, auth flaws, and OWASP Top 10. "
        "Rate issues as Critical/High/Medium/Low. Provide fixes with code examples."
    ),
    "DevOps": (
        "You are the DevOps agent. Create Dockerfiles, docker-compose, "
        "GitHub Actions CI/CD pipelines, deployment configs. "
        "Handle git workflows, environment variables, and infrastructure setup. "
        "Output complete, copy-paste-ready config files."
    ),
    "TestMonitor": (
        "You are the Test & Monitoring agent. "
        "Write pytest unit/integration tests and e2e test suites. "
        "Set up monitoring, health checks, log aggregation, and alerting rules. "
        "Use AAA pattern. Include fixtures and mocks."
    ),
    "DocsDiagram": (
        "You are the Documentation & Diagram agent. "
        "Generate API docs, README files, developer guides, and changelogs. "
        "Create Mermaid.js architecture diagrams, flowcharts, ERDs, and sequence diagrams. "
        "Output valid Mermaid syntax with clear labels."
    ),
}

AGENT_COLORS = {
    "PlannerResearcher": "#6366f1",
    "Coder": "#06b6d4",
    "ReviewerSecurity": "#ef4444",
    "DevOps": "#10b981",
    "TestMonitor": "#f59e0b",
    "DocsDiagram": "#8b5cf6",
    "System": "#374151",
}

DEFAULT_ROLES = {
    "PlannerResearcher": "planner",
    "Coder": "coder",
    "ReviewerSecurity": "reviewer",
    "DevOps": "custom",
    "TestMonitor": "tester",
    "DocsDiagram": "docs",
}

# Local by default, so a fresh install needs no API keys. One shared model
# until Auto-Crew picks one per role; users can set any provider:model.
DEFAULT_MODEL = "ollama:qwen3:8b"
DEFAULT_AGENT_MODEL_MAP = {name: DEFAULT_MODEL for name in DEFAULT_ROLES}

DEFAULT_AGENT_ICONS = {
    "PlannerResearcher": "planner",
    "Coder": "coder",
    "ReviewerSecurity": "reviewer",
    "DevOps": "devops",
    "TestMonitor": "test",
    "DocsDiagram": "docs",
}

# What a turn is doing, by role or by protocol, for turn_start events.
ACTIVITIES = {
    "planner": "planning",
    "coder": "coding",
    "reviewer": "reviewing",
    "tester": "testing",
    "docs": "writing docs",
    "custom": "working",
    "discuss": "discussing the plan",
    "revise": "revising the plan",
}

# Appended to an agent's prompt so the pipeline works whatever the user edits.
PROTOCOL = {
    "coder": (
        "Put each file in its own fenced code block whose info string names the language and "
        "the file path, for example ```python path=src/app.py. Always give complete files."
    ),
    "reviewer": (
        "End your reply with exactly one final line: `VERDICT: APPROVED` if the code is ready, "
        "or `VERDICT: CHANGES REQUESTED` if it needs another pass."
    ),
    # Crew discussion of the plan, before any code is written.
    "discuss": (
        "You are discussing the plan with the crew before any code is written. Point out problems, "
        "gaps or open questions briefly; don't write code. End with exactly one final line: "
        "`PLAN: AGREED` if the plan is ready, or `PLAN: CHANGES NEEDED`."
    ),
    "revise": "Revise your plan to address the feedback. Reply with the complete revised plan.",
    "follow_up": (
        "You are answering follow-up questions about a finished run. Answer from the run's output, "
        "and say so when it doesn't cover the question."
    ),
}


def role_of(name: str, agent: dict) -> str:
    """An agent's role: its own setting, the default for its name, or custom."""
    role = agent.get("role") or DEFAULT_ROLES.get(name, "custom")
    return role if role in ROLES else "custom"
