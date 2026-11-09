"""
LLM Configuration for JULI Multi-Agent System.
Supports OpenAI (GPT-4), Anthropic (Claude), and Google (Gemini) models.
"""

from typing import Dict, List, Any

from juli.keystore import get_key


def get_openai_config() -> List[Dict[str, Any]]:
    api_key = get_key("openai")
    if not api_key:
        return []
    return [{"model": "gpt-4", "api_key": api_key, "api_type": "openai"}]


def get_anthropic_config() -> List[Dict[str, Any]]:
    api_key = get_key("anthropic")
    if not api_key:
        return []
    return [{"model": "claude-opus-4-20250514", "api_key": api_key, "api_type": "anthropic", "base_url": "https://api.anthropic.com/v1"}]


def get_gemini_config() -> List[Dict[str, Any]]:
    api_key = get_key("google")
    if not api_key:
        return []
    return [{"model": "gemini-pro", "api_key": api_key, "api_type": "google"}]


def get_gemini_flash_config() -> List[Dict[str, Any]]:
    api_key = get_key("google")
    if not api_key:
        return []
    return [{"model": "gemini-1.5-flash", "api_key": api_key, "api_type": "google"}]


def get_config_for_model(model_pref: str) -> List[Dict[str, Any]]:
    """Get config list with fallback chain."""
    configs = {
        "gpt4": get_openai_config,
        "claude": get_anthropic_config,
        "gemini": get_gemini_config,
        "gemini_flash": get_gemini_flash_config,
    }
    preferred = configs.get(model_pref, get_openai_config)()
    if preferred:
        return preferred
    for fn in [get_openai_config, get_anthropic_config, get_gemini_config]:
        fallback = fn()
        if fallback:
            return fallback
    raise EnvironmentError("No API keys found. Add one in Settings, or set OPENAI_API_KEY, ANTHROPIC_API_KEY or GOOGLE_API_KEY in .env")


# Agent → Model mapping (6 consolidated agents)
AGENT_MODEL_MAP = {
    "PlannerResearcher": "gpt4",
    "Coder": "claude",
    "ReviewerSecurity": "gpt4",
    "DevOps": "gemini",
    "TestMonitor": "gemini",
    "DocsDigram": "gemini_flash",
}
