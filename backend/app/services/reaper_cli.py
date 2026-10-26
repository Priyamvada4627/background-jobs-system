import os
import sys
import signal
import asyncio
import argparse
from app.services.lease_reaper import LeaseReaper
from app.core.config import settings


def main():
    parser = argparse.ArgumentParser(description="Run the Background Job System Lease Reaper daemon.")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=settings.REAPER_POLL_INTERVAL_SECONDS,
        help="Polling interval in seconds for checking expired leases and dead workers.",
    )
    args = parser.parse_args()

    reaper = LeaseReaper()
    print(f"[*] Starting Lease Reaper daemon (PID: {os.getpid()})")
    print(f"[*] Polling interval: {args.poll_interval}s")

    stop_event = asyncio.Event()

    def handle_exit_signal(*_):
        print("\n[!] Shutdown signal received for Lease Reaper. Draining...")
        stop_event.set()

    if sys.platform != "win32":
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_exit_signal)
    else:
        signal.signal(signal.SIGINT, handle_exit_signal)
        signal.signal(signal.SIGTERM, handle_exit_signal)

    try:
        asyncio.run(reaper.run_loop(poll_interval=args.poll_interval, stop_event=stop_event))
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        print("[*] Lease Reaper daemon terminated cleanly.")


if __name__ == "__main__":
    main()
