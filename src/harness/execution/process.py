"""harness/execution/process.py - contained process execution."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

# resource limits are Unix-only; provide a no-op shim on Windows
if sys.platform != "win32":
    import resource as _resource
else:
    _resource = None  # type: ignore[assignment]


@dataclass(frozen=True)
class RunLimits:
    wall_seconds: int = 600
    cpu_seconds: int = 300
    max_file_bytes: int = 200_000_000
    max_procs: int = 512
    tail_bytes: int = 16_384
    grace_seconds: int = 3


@dataclass(frozen=True)
class RunResult:
    exit_code: int | None      # None when killed by the harness
    timed_out: bool
    duration_ms: int
    stdout_tail: str
    stderr_tail: str


def _limits_fn(lim: RunLimits):
    if _resource is None:
        # Windows: no resource limits available via stdlib; return no-op
        return None

    def apply() -> None:               # runs in the child, pre-exec
        _resource.setrlimit(_resource.RLIMIT_CPU,
                            (lim.cpu_seconds, lim.cpu_seconds))
        _resource.setrlimit(_resource.RLIMIT_FSIZE,
                            (lim.max_file_bytes, lim.max_file_bytes))
        _resource.setrlimit(_resource.RLIMIT_NPROC,
                            (lim.max_procs, lim.max_procs))
        _resource.setrlimit(_resource.RLIMIT_CORE, (0, 0))
    return apply


def _tail(f, n: int) -> str:
    f.flush()
    size = f.seek(0, os.SEEK_END)
    f.seek(max(0, size - n))
    return f.read().decode("utf-8", errors="replace")


def _kill_group(pid: int, sig: int) -> None:
    """Send signal to process group (Unix) or just the process (Windows)."""
    if sys.platform == "win32":
        try:
            import subprocess as _sp
            _sp.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True)
        except Exception:
            pass
        return
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


def run_contained(argv, *, cwd: str, env: dict[str, str],
                  limits: RunLimits = RunLimits()) -> RunResult:
    if (not isinstance(argv, (list, tuple)) or not argv
            or not all(isinstance(a, str) for a in argv)):
        raise TypeError("argv must be a non-empty list of str")
    if not os.path.isabs(argv[0]):
        raise ValueError("argv[0] must be an absolute path")
    start = time.monotonic()
    timed_out = False
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        popen_kwargs: dict = dict(
            cwd=cwd, env=env, shell=False,
            stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            close_fds=True,
        )
        if sys.platform != "win32":
            popen_kwargs["start_new_session"] = True   # own process group
            popen_kwargs["preexec_fn"] = _limits_fn(limits)

        proc = subprocess.Popen(list(argv), **popen_kwargs)
        try:
            proc.wait(timeout=limits.wall_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(proc.pid, signal.SIGTERM if sys.platform != "win32" else 0)
            try:
                proc.wait(timeout=limits.grace_seconds)
            except subprocess.TimeoutExpired:
                pass
        finally:
            _kill_group(proc.pid, signal.SIGKILL if sys.platform != "win32" else 0)
            proc.wait()
        code = None if timed_out else proc.returncode
        return RunResult(code, timed_out,
                         int((time.monotonic() - start) * 1000),
                         _tail(out, limits.tail_bytes),
                         _tail(err, limits.tail_bytes))
