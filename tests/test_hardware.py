import json

import pytest

from juli.local import catalogue, hardware
from juli.local.hardware import GB, Readings


def readings(**overrides) -> Readings:
    """A 16 GB Windows laptop with an Intel iGPU, like the dev machine."""
    base = {
        "system": "Windows",
        "machine": "AMD64",
        "cpu": "11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz",
        "cores": 4,
        "ram_bytes": 16_948_453_376,
        "disk_free_bytes": 40_693_530_624,
        "models_dir": r"C:\Users\me\.ollama\models",
        "windows_gpus": [("Intel(R) Iris(R) Xe Graphics", None)],
    }
    return Readings(**{**base, **overrides})


def machine(ram_gb: float, vram_gb: float | None = None, unified: bool = False, disk_gb: float | None = 500) -> dict:
    gpu = None
    if vram_gb is not None or unified:
        gpu = {"vendor": "apple" if unified else "nvidia", "name": "GPU", "vram_gb": vram_gb or ram_gb * 0.7, "unified": unified}
    return {"ram_gb": ram_gb, "gpu": gpu, "disk_free_gb": disk_gb}


# ─── Detection ───────────────────────────────────────────────


def test_intel_igpu_runs_on_the_cpu():
    hw = hardware.detect(readings())
    assert hw["gpu"] is None
    assert hw["ram_gb"] == pytest.approx(16.95, abs=0.01)
    assert hw["disk_free_gb"] == pytest.approx(40.69, abs=0.01)
    assert hw["cores"] == 4


def test_nvidia_smi_wins_and_the_largest_gpu_counts():
    smi = "NVIDIA GeForce RTX 3060, 12288, 11800\nNVIDIA GeForce RTX 4090, 24564, 23900\n"
    hw = hardware.detect(readings(nvidia_smi=smi, windows_gpus=[("NVIDIA GeForce RTX 3060", 12 * 1024**3)]))
    assert hw["gpu"]["name"] == "NVIDIA GeForce RTX 4090"
    assert hw["gpu"]["vram_gb"] == pytest.approx(24564 * 1024 * 1024 / GB, abs=0.01)
    assert hw["gpu"]["unified"] is False


def test_windows_registry_reads_qwmemorysize_beyond_4gb():
    # 16 GiB: WMI AdapterRAM would cap this at 4 GB.
    hw = hardware.detect(readings(windows_gpus=[("Intel(R) UHD Graphics", 128 * 1024**2), ("AMD Radeon RX 7800 XT", 16 * 1024**3)]))
    assert hw["gpu"]["vendor"] == "amd"
    assert hw["gpu"]["vram_gb"] == pytest.approx(17.18, abs=0.01)


def test_small_amd_apu_memory_counts_as_integrated():
    assert hardware.detect(readings(windows_gpus=[("AMD Radeon(TM) Graphics", 512 * 1024**2)]))["gpu"] is None


def test_apple_silicon_uses_unified_memory():
    hw = hardware.detect(readings(system="Darwin", machine="arm64", cpu="Apple M3 Pro", ram_bytes=36 * 10**9, windows_gpus=[]))
    assert hw["gpu"] == {"vendor": "apple", "name": "Apple M3 Pro", "vram_gb": pytest.approx(25.2), "unified": True}


def test_amd_on_linux_via_rocm_smi():
    rocm = json.dumps(
        {"card0": {"Card Series": "Radeon RX 7900 XTX", "VRAM Total Memory (B)": "25753026560", "VRAM Total Used Memory (B)": "1000"}}
    )
    hw = hardware.detect(readings(system="Linux", machine="x86_64", rocm_smi=rocm, windows_gpus=[]))
    assert hw["gpu"]["name"] == "Radeon RX 7900 XTX"
    assert hw["gpu"]["vram_gb"] == pytest.approx(25.75, abs=0.01)


def test_unparseable_tool_output_is_ignored():
    assert hardware.parse_nvidia_smi("garbage\n") == []
    assert hardware.parse_rocm_smi("not json") == []
    assert hardware.detect(readings(nvidia_smi="[N/A]"))["gpu"] is None


def test_fingerprint_is_stable_and_changes_with_the_gpu():
    a = hardware.detect(readings())["fingerprint"]
    assert a == hardware.detect(readings(disk_free_bytes=1))["fingerprint"]  # disk space isn't hardware
    assert a != hardware.detect(readings(nvidia_smi="NVIDIA RTX 4090, 24564, 0"))["fingerprint"]
    assert len(a) == 16


def test_real_readings_work_on_this_machine():
    hw = hardware.current()
    assert hw["ram_gb"] > 0 and hw["cores"] >= 1 and hw["cpu"]


# ─── Fit check ───────────────────────────────────────────────


def test_budgets():
    assert hardware.budgets(machine(32)) == (0.0, 24.0)
    gpu, total = hardware.budgets(machine(32, vram_gb=24))
    assert (gpu, total) == (pytest.approx(22.8), pytest.approx(48.0))
    gpu, total = hardware.budgets(machine(36, unified=True))
    assert (gpu, total) == (pytest.approx(25.2), pytest.approx(27.0))  # VRAM isn't added on top


def test_need_uses_the_kv_estimate_or_the_entry():
    model = {"size_gb": 5.2, "params_b": 8}
    assert hardware.need_gb(model, 4096) == pytest.approx(5.2 + 0.125 * 4.096 + 0.6)
    assert hardware.kv_gb({**model, "kv_mb_per_token": 0.5}, 1000) == pytest.approx(0.5)


def test_tiers():
    qwen8 = catalogue.entry("qwen3:8b")
    assert hardware.fit(qwen8, machine(16, vram_gb=12))["tier"] == "great"
    assert hardware.fit(qwen8, machine(16))["tier"] == "slow"
    cannot = hardware.fit(catalogue.entry("gpt-oss:120b"), machine(16))
    assert cannot["tier"] == "cannot" and cannot["num_ctx"] is None
    assert cannot["reason"] == "needs 69.0 GB, this machine has 12.0 GB for models"


def test_missing_disk_space_blocks_unless_installed():
    qwen14 = catalogue.entry("qwen3:14b")
    blocked = hardware.fit(qwen14, machine(64, disk_gb=5))
    assert blocked["tier"] == "cannot" and "disk space" in blocked["reason"]
    assert hardware.fit(qwen14, machine(64, disk_gb=5), installed=True)["tier"] == "slow"
    assert hardware.fit(qwen14, machine(64, disk_gb=None))["tier"] == "slow"  # unknown disk doesn't block


def test_num_ctx_is_the_largest_context_that_fits_capped_at_the_maximum():
    qwen8 = catalogue.entry("qwen3:8b")  # 40K maximum
    assert hardware.fit(qwen8, machine(64, vram_gb=48))["num_ctx"] == 40960
    qwen4 = catalogue.entry("qwen3:4b")  # 256K maximum
    assert hardware.fit(qwen4, machine(128, vram_gb=96))["num_ctx"] == 262144
    roomy = hardware.fit(qwen4, machine(16, vram_gb=8))
    assert roomy["tier"] == "great"
    assert hardware.need_gb(qwen4, roomy["num_ctx"]) <= 8 * 0.95 < hardware.need_gb(qwen4, roomy["num_ctx"] * 2)


def test_unknown_context_is_capped_conservatively():
    model = {"size_gb": 1.0, "params_b": 1, "context_max": None}
    assert hardware.fit(model, machine(256, vram_gb=80))["num_ctx"] == hardware.UNKNOWN_CONTEXT


def test_gpu_scans_are_cached_but_ram_and_disk_are_not(monkeypatch):
    calls = []
    monkeypatch.setattr(hardware, "_run", lambda cmd: calls.append(cmd[0]) or None)
    monkeypatch.setattr(hardware, "_windows_gpus", lambda: calls.append("winreg") or [("Intel(R) Iris(R) Xe Graphics", None)])
    disk = iter([10 * 10**9, 5 * 10**9])
    monkeypatch.setattr(hardware, "_disk_free", lambda path: next(disk))
    hardware._gpu_readings.cache_clear()
    try:
        first, second = hardware.read(), hardware.read()
    finally:
        hardware._gpu_readings.cache_clear()
    assert calls.count("nvidia-smi") == 1
    assert (first.disk_free_bytes, second.disk_free_bytes) == (10 * 10**9, 5 * 10**9)
    assert first.windows_gpus == second.windows_gpus and first.windows_gpus is not second.windows_gpus


def test_cpu_name_on_linux_and_macos(monkeypatch):
    real_read_text = hardware.Path.read_text

    def read_text(self, *args, **kwargs):
        if self.as_posix() == "/proc/cpuinfo":
            return "processor\t: 0\nmodel name\t: AMD Ryzen 7 7840U\n"
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(hardware.Path, "read_text", read_text)
    assert hardware._cpu_name("Linux") == "AMD Ryzen 7 7840U"
    monkeypatch.setattr(hardware, "_run", lambda cmd: "Apple M3 Pro\n" if cmd[0] == "sysctl" else None)
    assert hardware._cpu_name("Darwin") == "Apple M3 Pro"
    monkeypatch.setattr(hardware.platform, "processor", lambda: "")
    monkeypatch.setattr(hardware.platform, "machine", lambda: "riscv64")
    assert hardware._cpu_name("FreeBSD") == "riscv64"  # nothing better: the machine type


def test_run_returns_none_when_a_tool_is_missing_or_fails(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(hardware.subprocess, "run", missing)
    assert hardware._run(["nvidia-smi"]) is None
    monkeypatch.setattr(hardware.subprocess, "run", lambda *a, **kw: hardware.subprocess.CompletedProcess(a[0], 9, "partial", ""))
    assert hardware._run(["nvidia-smi"]) is None


def test_disk_free_uses_the_nearest_existing_folder(tmp_path):
    assert hardware._disk_free(tmp_path / "not" / "made" / "yet") == hardware.shutil.disk_usage(tmp_path).free


def test_windows_gpus_are_empty_elsewhere(monkeypatch):
    monkeypatch.setattr(hardware.sys, "platform", "linux")
    assert hardware._windows_gpus() == []
