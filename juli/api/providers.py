"""Provider routes: presets with prices, key health checks, custom OpenAI-compatible endpoints."""

from fastapi import APIRouter, HTTPException, Response

from juli import config, keystore
from juli import providers as llm
from juli.api.models import EndpointCreate, ProviderId
from juli.api.settings import KEYCHAIN_HELP
from juli.local import catalogue

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


@router.post("/endpoints", status_code=201)
def add_endpoint(body: EndpointCreate) -> dict:
    """Save an OpenAI-compatible endpoint, test it and list its models."""
    try:
        endpoint = catalogue.save_endpoint(body.id, body.label, body.base_url, body.key.strip() if body.key else None)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    except keystore.KeystoreUnavailable:
        raise HTTPException(503, KEYCHAIN_HELP) from None
    settings = config.load_settings()
    health = llm.check(body.id, settings.get("endpoints"), privacy=settings["run"]["privacy_mode"])
    return {"id": body.id, **endpoint, "local": llm.is_local_url(endpoint["base_url"]), "health": health}


@router.delete("/endpoints/{endpoint_id}", status_code=204)
def remove_endpoint(endpoint_id: ProviderId) -> Response:
    try:
        catalogue.remove_endpoint(endpoint_id)
    except KeyError:
        raise HTTPException(404, "Endpoint not found") from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    except keystore.KeystoreUnavailable:
        raise HTTPException(503, KEYCHAIN_HELP) from None
    return Response(status_code=204)
