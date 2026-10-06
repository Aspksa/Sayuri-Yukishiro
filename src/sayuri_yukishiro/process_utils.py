from __future__ import annotations

import ctypes
import errno
import os


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False

    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(
                process_query_limited_information,
                False,
                int(pid),
            )
        except Exception:
            return False
        if not handle:
            return False

        exit_code = ctypes.c_ulong()
        try:
            ok = bool(
                kernel32.GetExitCodeProcess(
                    handle,
                    ctypes.byref(exit_code),
                )
            )
            return ok and exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True
