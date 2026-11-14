"""Threaded background job manager for CPU-bound simulation tasks.

Workers never access Streamlit APIs. UI sessions poll immutable job snapshots.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, RLock
from uuid import uuid4
import time

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pas-solver")
_JOBS = {}
_LOCK = RLock()
_MAX_JOBS = 32


class SolverCancelled(Exception):
    """Raised when a cooperative solver cancellation is requested."""


def submit_job(kind, function, *args, **kwargs):
    with _LOCK:
        # Bound retained results to avoid unbounded process memory growth.
        finished = [key for key, item in _JOBS.items()
                    if item["status"] in ("completed", "failed", "cancelled")]
        for key in finished[:-_MAX_JOBS + 1]:
            _JOBS.pop(key, None)
        job_id = uuid4().hex
        cancel_event = Event()
        job = {
            "id": job_id, "kind": str(kind), "status": "queued",
            "progress": 0, "current": 0, "total": 0, "metric": None,
            "message": "Menunggu worker…", "result": None, "error": None,
            "created_at": time.time(), "updated_at": time.time(),
            "cancel_event": cancel_event, "future": None,
        }
        _JOBS[job_id] = job

    def report(current, total, metric=None):
        with _LOCK:
            item = _JOBS.get(job_id)
            if item is None:
                return
            item["current"] = int(current)
            item["total"] = max(1, int(total))
            item["progress"] = min(100, max(0, int(100 * current / max(1, total))))
            item["metric"] = None if metric is None else float(metric)
            item["message"] = f"{item['progress']}% · {current:,}/{total:,}"
            item["updated_at"] = time.time()

    def run():
        with _LOCK:
            _JOBS[job_id]["status"] = "running"
            _JOBS[job_id]["message"] = "Perhitungan berjalan…"
        try:
            if cancel_event.is_set():
                raise SolverCancelled("Simulasi dibatalkan sebelum dimulai.")
            call_kwargs = dict(kwargs)
            call_kwargs["progress_callback"] = report
            call_kwargs["cancel_event"] = cancel_event
            result = function(*args, **call_kwargs)
            if cancel_event.is_set():
                raise SolverCancelled("Simulasi dibatalkan oleh pengguna.")
            with _LOCK:
                item = _JOBS[job_id]
                item.update(status="completed", progress=100, result=result,
                             message="Simulasi selesai.", updated_at=time.time())
        except SolverCancelled as exc:
            with _LOCK:
                _JOBS[job_id].update(status="cancelled", error=str(exc),
                                     message="Simulasi dibatalkan.", updated_at=time.time())
        except Exception as exc:
            with _LOCK:
                _JOBS[job_id].update(status="failed", error=f"{type(exc).__name__}: {exc}",
                                     message="Simulasi gagal.", updated_at=time.time())

    future = _EXECUTOR.submit(run)
    with _LOCK:
        _JOBS[job_id]["future"] = future
    return job_id


def cancel_job(job_id):
    with _LOCK:
        item = _JOBS.get(job_id)
        if item is None or item["status"] not in ("queued", "running"):
            return False
        item["cancel_event"].set()
        item["message"] = "Permintaan pembatalan dikirim…"
        item["updated_at"] = time.time()
        return True


def get_job(job_id):
    with _LOCK:
        item = _JOBS.get(job_id)
        if item is None:
            return None
        return {key: value for key, value in item.items()
                if key not in ("cancel_event", "future")}


def check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise SolverCancelled("Simulasi dihentikan atas permintaan pengguna.")
