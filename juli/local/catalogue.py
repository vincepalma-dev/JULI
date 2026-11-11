"""
The model catalogue, model licenses, and bring-your-own models: Hugging Face
GGUF files and OpenAI-compatible endpoints.

Catalogue sizes were checked on ollama.com/library (2026-11-09). A model whose
license must be accepted (Llama, Gemma, a gated repo, or terms JULI doesn't
know) can't be pulled until the acceptance is recorded in
settings["licenses"].
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from juli import config, keystore, providers
from juli.local import hardware

_DATA = json.loads(Path(__file__).with_name("catalogue.json").read_text(encoding="utf-8"))
LICENSES: dict[str, dict] = _DATA["licenses"]
MODELS: list[dict] = _DATA["models"]

HF_API = "https://huggingface.co/api/models/"
HF_TIMEOUT = 20.0


def entry(tag: str) -> dict | None:
    return next((m for m in MODELS if m["tag"] == tag), None)


def listing(hw: dict, installed: set[str], settings: dict) -> list[dict]:
    """Every catalogue model with its fit on this machine and its license."""
    result = []
    for model in MODELS:
        lic = license_info(model["license"])
        is_installed = model["tag"] in installed
        result.append(
            {
                **model,
                "license": {**lic, "accepted": accepted(lic, settings)},
                "installed": is_installed,
                "fit": hardware.fit(model, hw, is_installed),
            }
        )
    return result


# ─── Licenses ────────────────────────────────────────────────


def license_info(license_id: str) -> dict:
    return {"id": license_id, **LICENSES[license_id]}


def accepted(lic: dict, settings: dict) -> bool:
    return not lic.get("accept") or lic["id"] in (settings.get("licenses") or {})


def _unknown_license(model: str) -> dict:
    name = model.partition(":")[0]
    page = f"https://ollama.com/{name}" if "/" in name else f"https://ollama.com/library/{name}"
    return {"id": f"model:{name}", "name": f"the license of {name}", "url": page, "accept": True}


def license_for(model: str) -> dict:
    """The license a model is pulled under. Hugging Face models are looked up."""
    if model.lower().startswith("hf.co/"):
        repo = model[len("hf.co/") :].partition(":")[0]
        info = _hf_get(repo)
        return hf_license(repo, info if isinstance(info, dict) else {})
    known = entry(model)
    if known:
        return license_info(known["license"])
    # Another tag of a catalogue model (e.g. qwen3:8b-q8_0) shares its license.
    family = {m["license"] for m in MODELS if m["tag"].partition(":")[0] == model.partition(":")[0]}
    if len(family) == 1:
        return license_info(family.pop())
    return _unknown_license(model)


def license_needed(model: str, settings: dict) -> dict | None:
    """The license that must be accepted before pulling a model, or None."""
    lic = license_for(model)
    return None if accepted(lic, settings) else lic


LICENSE_ID = re.compile(r"^(?:hf:[A-Za-z0-9][\w.-]*/[\w.-]+|model:[a-z0-9][\w.-]*(?:/[\w.-]+)?)$")


def accept_license(license_id: str) -> None:
    """Record that the user accepted a license."""
    if license_id not in LICENSES and not LICENSE_ID.match(license_id):
        raise ValueError(f"Unknown license '{license_id}'")
    with config.settings_lock:
        settings = config.load_settings()
        licenses = settings.setdefault("licenses", {})
        licenses.setdefault(license_id, {"accepted_at": datetime.now(UTC).isoformat()})
        config.save_settings(settings)


# ─── Hugging Face GGUF ───────────────────────────────────────

QUANT = re.compile(r"(?<![A-Za-z0-9])((?:UD-)?I?Q[1-8](?:_[A-Z0-9]+)*|BF16|F16|F32)(?![A-Za-z0-9])", re.IGNORECASE)
SHARD = re.compile(r"-\d{5}-of-\d{5}(?=\.gguf$)", re.IGNORECASE)


def quant_of(path: str) -> str | None:
    """The quantisation in a GGUF file name, e.g. Q4_K_M, or None."""
    name = SHARD.sub("", path.rsplit("/", 1)[-1])
    found = QUANT.findall(name[: -len(".gguf")] if name.lower().endswith(".gguf") else name)
    return found[-1].upper() if found else None


def parse_ggufs(tree: list[dict]) -> list[dict]:
    """One entry per quantisation, shards summed, smallest first."""
    groups: dict[str, dict] = {}
    for item in tree:
        path = str(item.get("path", ""))
        name = path.rsplit("/", 1)[-1].lower()
        if item.get("type") != "file" or not name.endswith(".gguf") or name.startswith("mmproj"):
            continue  # mmproj files are vision projectors, not models
        quant = quant_of(path)
        if not quant:
            continue
        size = (item.get("lfs") or {}).get("size") or item.get("size") or 0
        group = groups.setdefault(quant, {"quant": quant, "files": [], "size_bytes": 0})
        group["files"].append(path)
        group["size_bytes"] += int(size)
    return sorted(groups.values(), key=lambda g: g["size_bytes"])


def _bits(quant: str) -> float:
    if quant in ("F16", "BF16"):
        return 16.0
    if quant == "F32":
        return 32.0
    return int(re.search(r"Q(\d)", quant)[1]) + 0.5  # type: ignore[index]


def hf_license(repo: str, info: dict) -> dict:
    """A repo's license. Gated repos and terms JULI doesn't know need acceptance."""
    card = info.get("cardData") or {}
    lic = card.get("license")
    if isinstance(lic, list):
        lic = lic[0] if lic else None
    gated = bool(info.get("gated"))
    known = LICENSES.get(lic) if isinstance(lic, str) else None
    if known and not gated:
        return license_info(str(lic))
    name = known["name"] if known else str(card.get("license_name") or lic or "unknown terms")
    link = card.get("license_link")
    url = link if isinstance(link, str) and link.startswith("https://") else f"https://huggingface.co/{repo}"
    return {"id": f"hf:{repo}", "name": name + (" (gated repo)" if gated else ""), "url": url, "accept": True, "gated": gated}


def _hf_get(path: str, params: dict | None = None) -> dict | list:
    try:
        with providers.http_client() as http:
            r = http.get(HF_API + path, params=params, timeout=HF_TIMEOUT)
    except httpx.HTTPError as e:
        raise providers.ProviderError("huggingface", f"can't reach Hugging Face ({type(e).__name__})") from None
    if r.status_code in (401, 403, 404):
        raise providers.ProviderError("huggingface", "repo not found, or it's private")
    if r.status_code >= 400:
        raise providers.ProviderError("huggingface", f"HTTP {r.status_code}")
    try:
        return r.json()
    except ValueError:
        raise providers.ProviderError("huggingface", "unexpected response") from None


def hf_models(repo: str, hw: dict, installed: set[str], settings: dict) -> dict:
    """The GGUF quantisations in a Hugging Face repo, each with a fit check.

    Each is pulled through Ollama as hf.co/{repo}:{quant}.
    """
    info = _hf_get(repo)
    tree = _hf_get(f"{repo}/tree/main", {"recursive": "true"})
    if not isinstance(info, dict) or not isinstance(tree, list):
        raise providers.ProviderError("huggingface", "unexpected response")
    gguf = info.get("gguf") or {}
    params_b = gguf["total"] / 1e9 if isinstance(gguf.get("total"), (int, float)) else None
    context = gguf.get("context_length") if isinstance(gguf.get("context_length"), int) else None
    lowered = {t.lower() for t in installed}
    models = []
    for group in parse_ggufs(tree):
        size_gb = group["size_bytes"] / 1e9
        model = {
            "tag": f"hf.co/{repo}:{group['quant']}",
            "quant": group["quant"],
            "files": group["files"],
            "size_gb": round(size_gb, 2),
            "params_b": round(params_b or size_gb * 8 / _bits(group["quant"]), 2),
            "context_max": context,
        }
        is_installed = model["tag"].lower() in lowered
        models.append({**model, "installed": is_installed, "fit": hardware.fit(model, hw, is_installed)})
    lic = hf_license(repo, info)
    return {"repo": repo, "license": {**lic, "accepted": accepted(lic, settings)}, "models": models}


# ─── OpenAI-compatible endpoints ─────────────────────────────


def save_endpoint(endpoint_id: str, label: str, base_url: str, key: str | None = None) -> dict:
    """Add or update a custom OpenAI-compatible endpoint; its key goes to the keychain.

    Plain http is only allowed for local hosts, so a key never crosses the
    network unencrypted. Raises ValueError, or KeystoreUnavailable.
    """
    if endpoint_id in providers.PROVIDERS:
        raise ValueError(f"'{endpoint_id}' is a built-in provider; pick another id")
    url = urlparse(base_url)
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("The base URL must be a plain http(s) URL, like http://localhost:1234/v1")
    if url.scheme == "http" and not providers.is_local_url(base_url):
        raise ValueError("Use https for an endpoint that isn't on this machine or your local network")
    if key:
        keystore.set_key(endpoint_id, key)
    with config.settings_lock:
        settings = config.load_settings()
        endpoint = {
            "label": label,
            "kind": "openai",
            "base_url": base_url.rstrip("/"),
            "key": bool(key or keystore.get_key(endpoint_id)),
        }
        settings.setdefault("endpoints", {})[endpoint_id] = endpoint
        if endpoint["key"] and endpoint_id not in settings["providers"]:
            settings["providers"].append(endpoint_id)
        config.save_settings(settings)
    return endpoint


def remove_endpoint(endpoint_id: str) -> None:
    """Remove a custom endpoint and its key. Raises KeyError if there's none,
    ValueError while an agent or the fallback still uses it."""
    with config.settings_lock:
        settings = config.load_settings()
        endpoints = settings.get("endpoints") or {}
        if endpoint_id not in endpoints:
            raise KeyError(endpoint_id)
        prefix = endpoint_id + ":"
        users = [n for n, a in settings["agents"].items() if isinstance(a, dict) and str(a.get("model", "")).startswith(prefix)]
        if str(settings["run"].get("fallback_model") or "").startswith(prefix):
            users.append("the fallback model")
        if users:
            raise ValueError(f"Still in use by {', '.join(users)}")
        keystore.delete_key(endpoint_id)
        del endpoints[endpoint_id]
        if endpoint_id in settings["providers"]:
            settings["providers"].remove(endpoint_id)
        config.save_settings(settings)
