from __future__ import annotations

import ctypes
import os


_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False

    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(
                _PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                int(pid),
            )
        except Exception:
            return False
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(
                handle,
                ctypes.byref(exit_code),
            ):
                return False
            return int(exit_code.value) == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True
