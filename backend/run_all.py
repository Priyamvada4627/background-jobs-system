"""
Process Orchestrator for Single-Container / Single-Service Deployments.
Runs Alembic database migrations followed by:
1. Web API Server (Uvicorn / FastAPI)
2. Transactional Outbox Publisher Daemon
3. Worker Engine Pool
4. Lease Reaper Daemon
5. Cron Scheduler Daemon

Gracefully propagates SIGTERM/SIGINT signals to all child processes for zero-downtime restarts.
"""
import os
import sys
import time
import signal
import subprocess
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
os.chdir(str(backend_dir))

processes = []
is_shutting_down = False


def log(msg: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [Orchestrator] {msg}", flush=True)


def run_migrations():
    """Runs Alembic database migrations to ensure PostgreSQL schema is up to date."""
    log("Running database migrations (alembic upgrade head)...")
    possible_paths = [
        backend_dir.parent / "alembic.ini",
        backend_dir / "alembic.ini",
        Path("alembic.ini").resolve(),
    ]
    ini_path = None
    for p in possible_paths:
        if p.exists():
            ini_path = p
            break

    cmd = [sys.executable, "-m", "alembic"]
    if ini_path:
        cmd.extend(["-c", str(ini_path)])
    cmd.extend(["upgrade", "head"])

    cwd = ini_path.parent if ini_path else backend_dir
    log(f"Executing: {' '.join(cmd)} (cwd: {cwd})")

    try:
        res = subprocess.run(
            cmd,
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
        )
        if res.stdout.strip():
            print(res.stdout.strip(), flush=True)
        log("Database schema migrations applied successfully.")
    except subprocess.CalledProcessError as err:
        log(f"WARNING: Alembic migration failed: {err.stderr.strip() or err.stdout.strip() or err}")
        log("Proceeding to start services (schema might already be initialized)...")


def shutdown(*_):
    global is_shutting_down
    if is_shutting_down:
        return
    is_shutting_down = True
    log("Shutdown signal received. Gracefully terminating all processes...")

    # Send SIGTERM to all child processes
    for name, proc in processes:
        if proc.poll() is None:
            log(f"Stopping {name} (PID: {proc.pid})...")
            try:
                proc.terminate()
            except Exception:
                pass

    # Wait up to 10 seconds for clean termination
    deadline = time.time() + 10.0
    for name, proc in processes:
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.2)
        if proc.poll() is None:
            log(f"Force killing {name} (PID: {proc.pid})...")
            try:
                proc.kill()
            except Exception:
                pass

    log("All processes terminated cleanly.")
    sys.exit(0)


def main():
    # Setup exit signal handlers
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # 1. Run migrations first
    run_migrations()

    port = os.environ.get("PORT", "8000")
    python_bin = sys.executable

    # Define the 5 core processes
    services = [
        ("Web API Server", [
            python_bin, "-m", "uvicorn", "app.main:app",
            "--host", "0.0.0.0",
            "--port", str(port),
        ]),
        ("Outbox Publisher", [python_bin, "-m", "app.services.outbox_cli"]),
        ("Worker Engine", [python_bin, "-m", "app.workers.cli"]),
        ("Lease Reaper", [python_bin, "-m", "app.services.reaper_cli"]),
        ("Cron Scheduler", [python_bin, "-m", "app.scheduler.cli"]),
    ]

    log(f"Launching {len(services)} system services...")

    for name, cmd in services:
        log(f"Starting {name}: {' '.join(cmd)}")
        proc = subprocess.Popen(cmd, cwd=str(backend_dir))
        processes.append((name, proc))

    log("All services running. Orchestrator entered supervision loop.")

    # Supervision loop
    while not is_shutting_down:
        time.sleep(2.0)
        for name, proc in processes:
            ret = proc.poll()
            if ret is not None:
                log(f"CRITICAL: {name} (PID {proc.pid}) exited unexpectedly with code {ret}!")
                # If API crashes, trigger shutdown so orchestrator restarts via host container
                if name == "Web API Server":
                    shutdown()


if __name__ == "__main__":
    main()
