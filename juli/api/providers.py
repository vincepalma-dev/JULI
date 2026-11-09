"""Provider routes: presets with prices, and key health checks."""

from fastapi import APIRouter

from juli import config, keystore
from juli import providers as llm
from juli.api.models import ProviderId

router = APIRouter(prefix="/providers")


@router.get("")
def list_providers() -> list[dict]:
    settings = config.load_settings()
    endpoints = settings.get("endpoints") or {}
    ids = list(dict.fromkeys([*llm.PROVIDERS, *endpoints]))
    result = []
    for pid in ids:
        info = llm.provider_info(pid, endpoints) or {}
        needs_key = info.get("key", True)
        result.append(
            {
                "id": pid,
                "label": info.get("label", pid),
                "kind": info.get("kind"),
                "local": llm.is_local_url(info.get("base_url", "")),
                "needs_key": needs_key,
                "key_hint": keystore.key_hint(keystore.get_key(pid)) if needs_key else "",
                "models": [
                    {"ref": ref, "price_in": price["in"], "price_out": price["out"]}
                    for ref, price in llm.MODELS.items()
                    if ref.startswith(pid + ":")
                ],
            }
        )
    return result


@router.post("/{provider}/check")
def check_provider(provider: ProviderId) -> dict:
    """Health-check a provider's key with a cheap call (lists models)."""
    settings = config.load_settings()
    return llm.check(provider, settings.get("endpoints"), privacy=settings["run"]["privacy_mode"])
