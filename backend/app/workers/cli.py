import os
import sys
import signal
import asyncio
import argparse
from app.workers.engine import WorkerEngine
from app.core.config import settings


def main():
    parser = argparse.ArgumentParser(description="Run a Background Job System Worker process.")
    parser.add_argument("--worker-id", type=str, default=None, help="Custom unique identifier for the worker.")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=settings.WORKER_POLL_INTERVAL_SECONDS,
        help="Polling interval in seconds when queue is idle.",
    )
    args = parser.parse_args()

    worker = WorkerEngine(worker_id=args.worker_id)
    print(f"[*] Starting worker process: {worker.worker_id} (PID: {os.getpid()})")
    print(f"[*] Capabilities ({len(worker.capabilities)} tasks): {', '.join(worker.capabilities)}")

    stop_event = asyncio.Event()

    def handle_exit_signal(*_):
        print(f"\n[!] Shutdown signal received for worker {worker.worker_id}. Draining...")
        stop_event.set()

    if sys.platform != "win32":
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_exit_signal)
    else:
        # On Windows, register console signal handler
        signal.signal(signal.SIGINT, handle_exit_signal)
        signal.signal(signal.SIGTERM, handle_exit_signal)

    try:
        asyncio.run(worker.run_loop(poll_interval=args.poll_interval, stop_event=stop_event))
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        print(f"[*] Worker {worker.worker_id} terminated cleanly.")


if __name__ == "__main__":
    main()
