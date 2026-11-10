"""
What this machine can run: RAM, CPU, GPU, disk, and the fit check.

detect() is a pure function over Readings, so it's tested without real
hardware; read() gathers the real readings. Sizes are decimal GB (1e9 bytes),
the unit ollama.com uses for model sizes.

GPU memory comes from nvidia-smi, rocm-smi (Linux), Apple Silicon's unified
memory, or on Windows the registry's HardwareInformation.qwMemorySize. WMI
AdapterRAM isn't used: it caps at 4 GB. Intel and other integrated GPUs count
as CPU only.
"""

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import psutil  # type: ignore[import-untyped]  # ships no type stubs

GB = 1e9
MIB = 1024 * 1024

# A Windows GPU with less dedicated memory than this is treated as integrated.
MIN_DISCRETE_VRAM = 2 * GB

NVIDIA_QUERY = ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"]
ROCM_QUERY = ["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--json"]
WINDOWS_GPU_CLASS = r"SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"


@dataclass
class Readings:
    """Raw facts about the machine, as read from the OS and its tools."""

    system: str  # platform.system(): Windows, Linux, Darwin
    machine: str  # platform.machine(): AMD64, x86_64, arm64
    cpu: str
    cores: int
    ram_bytes: int
    disk_free_bytes: int | None  # on the drive that holds Ollama's models
    models_dir: str
    nvidia_smi: str | None = None  # output of NVIDIA_QUERY, None if it isn't there
    rocm_smi: str | None = None  # output of ROCM_QUERY
    windows_gpus: list[tuple[str, int | None]] = field(default_factory=list)  # (name, qwMemorySize)


# ─── Detection (pure) ────────────────────────────────────────


def parse_nvidia_smi(text: str) -> list[dict]:
    """One dict per GPU from `name, memory.total, memory.free` lines (MiB)."""
    gpus = []
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.rsplit(",", 2)]
        if len(parts) != 3:
            continue
        try:
            gpus.append({"name": parts[0], "vram_bytes": int(float(parts[1]) * MIB)})
        except ValueError:
            continue
    return gpus


def parse_rocm_smi(text: str) -> list[dict]:
    """One dict per card from rocm-smi's JSON output."""
    try:
        cards = json.loads(text)
    except ValueError:
        return []
    gpus = []
    for card in cards.values() if isinstance(cards, dict) else []:
        if not isinstance(card, dict):
            continue
        total = next((str(v) for k, v in card.items() if k.startswith("VRAM Total Memory")), "")
        try:
            vram = int(total)
        except ValueError:
            continue
        name = card.get("Card Series") or card.get("Card series") or card.get("Card SKU") or "AMD GPU"
        gpus.append({"name": str(name), "vram_bytes": vram})
    return gpus


def _vendor(name: str) -> str | None:
    lowered = name.lower()
    if "nvidia" in lowered:
        return "nvidia"
    if "amd" in lowered or "radeon" in lowered:
        return "amd"
    return None  # Intel and the rest run models on the CPU


def _gpu(r: Readings) -> dict | None:
    def largest(gpus: list[dict], vendor: str) -> dict | None:
        if not gpus:
            return None
        best = max(gpus, key=lambda g: g["vram_bytes"])
        return {"vendor": vendor, "name": best["name"], "vram_gb": round(best["vram_bytes"] / GB, 2), "unified": False}

    if r.nvidia_smi:
        gpu = largest(parse_nvidia_smi(r.nvidia_smi), "nvidia")
        if gpu:
            return gpu
    if r.system == "Darwin" and r.machine == "arm64":
        return {"vendor": "apple", "name": r.cpu or "Apple Silicon", "vram_gb": round(r.ram_bytes * 0.7 / GB, 2), "unified": True}
    if r.system == "Linux" and r.rocm_smi:
        gpu = largest(parse_rocm_smi(r.rocm_smi), "amd")
        if gpu:
            return gpu
    discrete = [
        (name, size, vendor)
        for name, size in r.windows_gpus
        if size and size >= MIN_DISCRETE_VRAM and (vendor := _vendor(name))
    ]
    if discrete:
        name, size, vendor = max(discrete, key=lambda g: g[1])
        return {"vendor": vendor, "name": name, "vram_gb": round(size / GB, 2), "unified": False}
    return None


def fingerprint(r: Readings, gpu: dict | None) -> str:
    """Stable id of the hardware that model speed depends on."""
    parts = [r.system, r.machine, r.cpu, r.cores, round(r.ram_bytes / GB), gpu and gpu["name"], gpu and round(gpu["vram_gb"])]
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:16]


def detect(r: Readings) -> dict:
    gpu = _gpu(r)
    return {
        "os": r.system,
        "cpu": r.cpu,
        "cores": r.cores,
        "ram_gb": round(r.ram_bytes / GB, 2),
        "disk_free_gb": None if r.disk_free_bytes is None else round(r.disk_free_bytes / GB, 2),
        "models_dir": r.models_dir,
        "gpu": gpu,
        "fingerprint": fingerprint(r, gpu),
    }


# ─── Fit check (pure) ────────────────────────────────────────

CONTEXTS = (4096, 8192, 16384, 32768, 65536, 131072, 262144)
OVERHEAD_GB = 0.6
# For models whose context length isn't known (some Hugging Face GGUFs).
UNKNOWN_CONTEXT = 32768


def budgets(hw: dict) -> tuple[float, float]:
    """(GPU budget, total budget) in GB for one model at a time."""
    ram, gpu = hw["ram_gb"], hw.get("gpu")
    if gpu and gpu.get("unified"):  # Apple Silicon: one pool, VRAM isn't extra
        return ram * 0.7, ram * 0.75
    if gpu:
        return gpu["vram_gb"] * 0.95, gpu["vram_gb"] + ram * 0.75
    return 0.0, ram * 0.75


def kv_gb(model: dict, ctx: int) -> float:
    """KV cache size for a context length, from the entry or an estimate by size."""
    per_token_mb = model.get("kv_mb_per_token") or 0.125 * (model["params_b"] / 8) ** 0.7
    return per_token_mb * ctx / 1000


def need_gb(model: dict, ctx: int) -> float:
    return model["size_gb"] + kv_gb(model, ctx) + OVERHEAD_GB


def fit(model: dict, hw: dict, installed: bool = False) -> dict:
    """How well a model runs here: tier great, slow or cannot, with num_ctx.

    great: it fits the GPU at a 4K context. slow: it fits GPU and RAM
    together (or RAM alone). num_ctx is the largest context, capped at the
    model's maximum, that fits the tier's budget. A download that doesn't
    fit on disk can't happen either.
    """
    gpu_budget, total_budget = budgets(hw)
    need = need_gb(model, 4096)
    result = {"tier": "cannot", "need_gb": round(need, 1), "num_ctx": None, "reason": ""}
    if need <= gpu_budget:
        tier, budget = "great", gpu_budget
    elif need <= total_budget:
        tier, budget = "slow", total_budget
    else:
        return {**result, "reason": f"needs {need:.1f} GB, this machine has {total_budget:.1f} GB for models"}
    free = hw.get("disk_free_gb")
    if not installed and free is not None and model["size_gb"] > free:
        return {**result, "reason": f"needs {model['size_gb']:.1f} GB of disk space, {free:.1f} GB is free"}
    cap = model.get("context_max") or UNKNOWN_CONTEXT
    sizes = sorted({min(c, cap) for c in CONTEXTS})
    num_ctx = max(c for c in sizes if c == sizes[0] or need_gb(model, c) <= budget)
    return {**result, "tier": tier, "num_ctx": num_ctx}


# ─── Real readings ───────────────────────────────────────────


def models_dir() -> Path:
    return Path(os.environ.get("OLLAMA_MODELS") or Path.home() / ".ollama" / "models")


def _disk_free(path: Path) -> int | None:
    while not path.exists() and path.parent != path:
        path = path.parent
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


def _run(cmd: list[str]) -> str | None:
    """A tool's output, or None if it's missing or fails."""
    try:
        done = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _windows_gpus() -> list[tuple[str, int | None]]:
    import winreg

    gpus: list[tuple[str, int | None]] = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WINDOWS_GPU_CLASS)
    except OSError:
        return gpus
    with root:
        index = 0
        while True:
            try:
                sub = winreg.EnumKey(root, index)
            except OSError:
                break
            index += 1
            if not re.fullmatch(r"\d{4}", sub):
                continue  # skips "Configuration" and "Properties"
            try:
                with winreg.OpenKey(root, sub) as key:
                    name = str(winreg.QueryValueEx(key, "DriverDesc")[0])
                    try:
                        size = winreg.QueryValueEx(key, "HardwareInformation.qwMemorySize")[0]
                    except OSError:
                        size = None
            except OSError:
                continue
            if isinstance(size, bytes):
                size = int.from_bytes(size, "little")
            gpus.append((name, size if isinstance(size, int) else None))
    return gpus


def _cpu_name(system: str) -> str:
    if system == "Windows":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    elif system == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("model name"):
                    return line.partition(":")[2].strip()
        except OSError:
            pass
    elif system == "Darwin":
        name = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if name:
            return name.strip()
    return platform.processor() or platform.machine()


@lru_cache(maxsize=1)
def _gpu_readings(system: str) -> tuple[str | None, str | None, tuple[tuple[str, int | None], ...]]:
    """GPU tool output, read once per process: GPUs don't change while JULI runs, and nvidia-smi is slow."""
    return (
        _run(NVIDIA_QUERY),
        _run(ROCM_QUERY) if system == "Linux" else None,
        tuple(_windows_gpus()) if system == "Windows" else (),
    )


def read() -> Readings:
    """Real readings. RAM and disk are read every time; GPU scans are cached."""
    system = platform.system()
    path = models_dir()
    nvidia_smi, rocm_smi, windows_gpus = _gpu_readings(system)
    return Readings(
        system=system,
        machine=platform.machine(),
        cpu=_cpu_name(system),
        cores=psutil.cpu_count(logical=False) or os.cpu_count() or 1,
        ram_bytes=psutil.virtual_memory().total,
        disk_free_bytes=_disk_free(path),
        models_dir=str(path),
        nvidia_smi=nvidia_smi,
        rocm_smi=rocm_smi,
        windows_gpus=list(windows_gpus),
    )


def current() -> dict:
    """This machine's hardware."""
    return detect(read())
