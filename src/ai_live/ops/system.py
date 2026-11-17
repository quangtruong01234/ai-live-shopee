"""Power source and free disk space for the readiness list (research R5): stdlib only."""

from __future__ import annotations

import ctypes
import shutil
import sys
from pathlib import Path
from typing import Literal

PowerStatus = Literal["ac", "battery"] | None

_GIB = 1024**3


class _SystemPowerStatus(ctypes.Structure):
    _fields_ = [  # noqa: RUF012 - ctypes reads this class attribute by name
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def _read_ac_line_status() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        status = _SystemPowerStatus()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return None
        return int(status.ACLineStatus)
    except (AttributeError, OSError):
        return None


def power_status() -> PowerStatus:
    """ "ac" when plugged in, "battery" when not, None when the OS does not say (255) or this is not Windows."""
    return {1: "ac", 0: "battery"}.get(_read_ac_line_status())  # type: ignore[return-value]


def free_disk_gb(path: Path) -> float:
    """Free space of the drive holding `path`; a path that does not exist yet is measured at its nearest parent."""
    target = Path(path)
    if not target.exists():
        target = target.resolve()
        while not target.exists() and target.parent != target:
            target = target.parent
    return shutil.disk_usage(target).free / _GIB
