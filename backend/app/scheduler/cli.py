import os
import sys
import signal
import asyncio
import argparse
from app.scheduler.cron_scheduler import CronScheduler
from app.core.config import settings


def main():
    parser = argparse.ArgumentParser(description="Run the Background Job System Cron Scheduler daemon.")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=settings.SCHEDULER_POLL_INTERVAL_SECONDS,
        help="Polling interval in seconds for schedule evaluation and delayed promotion.",
    )
    args = parser.parse_args()

    scheduler = CronScheduler()
    print(f"[*] Starting Cron Scheduler process: {scheduler.scheduler_id} (PID: {os.getpid()})")
    print(f"[*] Polling interval: {args.poll_interval}s, Leader lock TTL: {scheduler.lock_ttl_seconds}s")

    stop_event = asyncio.Event()

    def handle_exit_signal(*_):
        print(f"\n[!] Shutdown signal received for scheduler {scheduler.scheduler_id}. Draining...")
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
        asyncio.run(scheduler.run_loop(poll_interval=args.poll_interval, stop_event=stop_event))
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        print(f"[*] Scheduler {scheduler.scheduler_id} terminated cleanly.")


if __name__ == "__main__":
    main()
