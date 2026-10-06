from __future__ import annotations

import ctypes
import os


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False

    if os.name == "nt":
        try:
            handle = ctypes.windll.kernel32.OpenProcess(
                0x1000,
                False,
                int(pid),
            )
        except Exception:
            return False
        if not handle:
            return False
        try:
            return True
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True
