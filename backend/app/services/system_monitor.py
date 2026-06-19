"""System resource monitoring — CPU, memory, GPU, battery."""

import json as _json
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger("system_monitor")


_HAS_PSUTIL = False
try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore


def _is_wsl() -> bool:
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower() or "wsl" in f.read().lower()
    except Exception:
        return False


def _wsl_memory() -> Optional[dict]:
    """Query Windows host memory via PowerShell on WSL."""
    try:
        r = subprocess.run(
            ["powershell.exe", "-Command",
             "$os = Get-CimInstance -ClassName Win32_OperatingSystem;"
             "$cs = Get-CimInstance -ClassName Win32_ComputerSystem;"
             "@{TotalPhysicalMemory=$cs.TotalPhysicalMemory;"
             "TotalVisibleMemorySize=$os.TotalVisibleMemorySize;"
             "FreePhysicalMemory=$os.FreePhysicalMemory} | ConvertTo-Json"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            data = _json.loads(r.stdout.strip())
            total_bytes = data.get("TotalPhysicalMemory")
            total_kb = data.get("TotalVisibleMemorySize")
            free_kb = data.get("FreePhysicalMemory")
            if total_bytes:
                total_gb = round(total_bytes / (1024 ** 3), 1)
            elif total_kb:
                total_gb = round(float(total_kb) / (1024 * 1024), 1)
            else:
                return None
            if free_kb and total_kb:
                used_kb = float(total_kb) - float(free_kb)
                used_gb = round(used_kb / (1024 * 1024), 1)
                percent = round(100 * used_kb / float(total_kb), 1)
            else:
                used_gb = 0.0
                percent = 0.0
            return {"used_gb": used_gb, "total_gb": total_gb, "percent": percent}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception:
        pass
    return None


def get_system_resources() -> dict:
    """Collect current CPU, memory, GPU, and battery stats."""
    result = {
        "cpu_percent": _get_cpu(),
        "gpu": _get_gpu(),
        "battery": _get_battery(),
    }
    # Memory — prefer WSL host values, fall back to local /proc
    wsl_mem = _wsl_memory() if _is_wsl() else None
    if wsl_mem:
        result["memory_used_gb"] = wsl_mem["used_gb"]
        result["memory_total_gb"] = wsl_mem["total_gb"]
        result["memory_percent"] = wsl_mem["percent"]
    else:
        result["memory_percent"] = _get_memory_percent()
        result["memory_used_gb"] = _get_memory_used_gb()
        result["memory_total_gb"] = _get_memory_total_gb()
    return result


def _get_cpu() -> float:
    if _HAS_PSUTIL:
        try:
            return psutil.cpu_percent(interval=0.1)
        except Exception:
            pass
    try:
        with open("/proc/stat") as f:
            lines = f.readlines()
        for line in lines:
            if line.startswith("cpu "):
                parts = line.split()
                if len(parts) >= 5:
                    total = sum(int(v) for v in parts[1:])
                    idle = int(parts[4])
                    return round(100 * (1 - idle / total), 1)
    except Exception:
        pass
    return 0.0


def _get_memory_percent() -> float:
    if _HAS_PSUTIL:
        try:
            return psutil.virtual_memory().percent
        except Exception:
            pass
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        mem_total = 0
        mem_available = 0
        for line in lines:
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                mem_available = int(line.split()[1])
        if mem_total:
            return round(100 * (1 - mem_available / mem_total), 1)
    except Exception:
        pass
    return 0.0


def _get_memory_used_gb() -> float:
    if _HAS_PSUTIL:
        try:
            mem = psutil.virtual_memory()
            return round(mem.used / (1024 ** 3), 1)
        except Exception:
            pass
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        mem_total = 0
        mem_available = 0
        for line in lines:
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                mem_available = int(line.split()[1])
        if mem_total:
            used_kb = mem_total - mem_available
            return round(used_kb / (1024 * 1024), 1)
    except Exception:
        pass
    return 0.0


def _get_memory_total_gb() -> float:
    if _HAS_PSUTIL:
        try:
            return round(psutil.virtual_memory().total / (1024 ** 3), 1)
        except Exception:
            pass
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        for line in lines:
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
                return round(total_kb / (1024 * 1024), 1)
    except Exception:
        pass
    return 0.0


def _get_gpu() -> Optional[dict]:
    """Query nvidia-smi for GPU utilization if available."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,name",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            lines = r.stdout.strip().split("\n")
            gpus = []
            for line in lines:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    gpus.append({
                        "name": parts[3],
                        "utilization_percent": float(parts[0]),
                        "memory_used_mb": float(parts[1]),
                        "memory_total_mb": float(parts[2]),
                    })
            if gpus:
                return gpus[0] if len(gpus) == 1 else gpus
    except Exception:
        pass
    return None


def _get_battery() -> Optional[dict]:
    if _is_wsl():
        return _wsl_battery_power()
    # Native Linux: read /sys/class/power_supply
    try:
        supply_dir = Path("/sys/class/power_supply")
        if supply_dir.is_dir():
            for dev in supply_dir.iterdir():
                capacity_file = dev / "capacity"
                status_file = dev / "status"
                if capacity_file.exists() and status_file.exists():
                    percent = int(capacity_file.read_text().strip())
                    status = status_file.read_text().strip()
                    power_plugged = status == "Charging" or status == "Full"
                    return {"percent": percent, "power_plugged": power_plugged}
    except Exception:
        pass
    # psutil fallback
    if _HAS_PSUTIL:
        try:
            batt = psutil.sensors_battery()
            if batt:
                return {"percent": batt.percent, "power_plugged": batt.power_plugged}
        except Exception:
            pass
    return None


def _wsl_battery_power() -> Optional[dict]:
    """Query Windows host battery + total system power via WMI."""
    try:
        r = subprocess.run(
            ["powershell.exe", "-Command",
             "$bs = Get-WmiObject -Namespace root/wmi -Class BatteryStatus | "
             "Select-Object ChargeRate, DischargeRate, Charging, Discharging; "
             "$wb = Get-CimInstance -ClassName Win32_Battery | "
             "Select-Object EstimatedChargeRemaining, BatteryStatus; "
             "Write-Output (@{ "
             "  charge_rate = $bs.ChargeRate; "
             "  discharge_rate = $bs.DischargeRate; "
             "  charging = $bs.Charging; "
             "  discharging = $bs.Discharging; "
             "  percent = $wb.EstimatedChargeRemaining; "
             "  battery_status = $wb.BatteryStatus "
             "} | ConvertTo-Json -Compress)"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            d = _json.loads(r.stdout.strip())
            percent = d.get("percent")
            if percent is None:
                return None
            discharging = d.get("discharging", False)
            power_plugged = not discharging
            result = {"percent": float(percent), "power_plugged": power_plugged}
            if discharging:
                rate = d.get("discharge_rate", 0) or 0
            else:
                rate = d.get("charge_rate", 0) or 0
            if rate:
                result["power_watts"] = round(rate / 1000, 1)
            return result
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception:
        pass
    return None
