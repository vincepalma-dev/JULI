"""
JULI — 6 Consolidated AI Agents.
Optimized for token efficiency with concise system prompts.
"""

from typing import TYPE_CHECKING, Dict

from agents.config import get_config_for_model, AGENT_MODEL_MAP

if TYPE_CHECKING:
    import autogen


# ─────────────────────────────────────────────────────────────
# Concise System Prompts (Token-Optimized)
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
# Agent Factory
# ─────────────────────────────────────────────────────────────

def create_agent(name: str, system_prompt: str, model_pref: str) -> "autogen.AssistantAgent":
    """Create a single AutoGen AssistantAgent."""
    import autogen  # lazy, so the API can read prompts without pyautogen

    config_list = get_config_for_model(model_pref)
    return autogen.AssistantAgent(
        name=name,
        system_message=system_prompt,
        llm_config={
            "config_list": config_list,
            "temperature": 0.3,
            "timeout": 120,
            "cache_seed": None,
        },
    )


def create_user_proxy(work_dir: str = "./workspace") -> "autogen.UserProxyAgent":
    """Create UserProxyAgent for code execution and commands."""
    import autogen

    return autogen.UserProxyAgent(
        name="UserProxy",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=10,
        is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("TERMINATE"),
        code_execution_config={"work_dir": work_dir, "use_docker": False},
        system_message="Execute code and commands. Reply TERMINATE when task is fully complete.",
    )


def create_all_agents(work_dir: str = "./workspace") -> Dict[str, "autogen.Agent"]:
    """Create all 6 agents + UserProxy."""
    agents = {}
    for name, prompt in SYSTEM_PROMPTS.items():
        model_pref = AGENT_MODEL_MAP.get(name, "gpt4")
        agents[name] = create_agent(name, prompt, model_pref)
    agents["UserProxy"] = create_user_proxy(work_dir)
    return agents


def create_agent_subset(agent_names: list, work_dir: str = "./workspace") -> Dict[str, "autogen.Agent"]:
    """Create a subset of agents for specific modes."""
    agents = {}
    for name in agent_names:
        if name in SYSTEM_PROMPTS:
            model_pref = AGENT_MODEL_MAP.get(name, "gpt4")
            agents[name] = create_agent(name, SYSTEM_PROMPTS[name], model_pref)
    agents["UserProxy"] = create_user_proxy(work_dir)
    return agents


# ─────────────────────────────────────────────────────────────
# Agent Metadata (Dashboard + CLI)
# ─────────────────────────────────────────────────────────────

AGENT_COLORS = {
    "PlannerResearcher": "#6366f1",
    "Coder": "#06b6d4",
    "ReviewerSecurity": "#ef4444",
    "DevOps": "#10b981",
    "TestMonitor": "#f59e0b",
    "DocsDiagram": "#8b5cf6",
    "UserProxy": "#6b7280",
    "System": "#374151",
}

AGENT_ICONS = {
    "PlannerResearcher": "🏗️",
    "Coder": "💻",
    "ReviewerSecurity": "🛡️",
    "DevOps": "🚀",
    "TestMonitor": "🧪",
    "DocsDiagram": "📐",
    "UserProxy": "👤",
    "System": "⚙️",
}

AGENT_INFO = [
    {"name": "PlannerResearcher", "icon": "🏗️", "color": "#6366f1", "model": "GPT-4"},
    {"name": "Coder",             "icon": "💻", "color": "#06b6d4", "model": "Claude Opus"},
    {"name": "ReviewerSecurity",  "icon": "🛡️", "color": "#ef4444", "model": "GPT-4"},
    {"name": "DevOps",            "icon": "🚀", "color": "#10b981", "model": "Gemini"},
    {"name": "TestMonitor",       "icon": "🧪", "color": "#f59e0b", "model": "Gemini"},
    {"name": "DocsDiagram",       "icon": "📐", "color": "#8b5cf6", "model": "Gemini Flash"},
]
