import os
import sys
import signal
import asyncio
import argparse
from app.services.outbox_publisher import OutboxPublisher
from app.core.config import settings


def main():
    parser = argparse.ArgumentParser(description="Run the Transactional Outbox Publisher daemon.")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=settings.OUTBOX_POLL_INTERVAL_SECONDS,
        help="Polling interval in seconds when no unpublished events exist.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=settings.OUTBOX_BATCH_SIZE,
        help="Maximum number of outbox events to publish per batch.",
    )
    args = parser.parse_args()

    publisher = OutboxPublisher(batch_size=args.batch_size)
    print(f"[*] Starting Outbox Publisher daemon (PID: {os.getpid()})")
    print(f"[*] Batch size: {publisher.batch_size}, poll interval: {args.poll_interval}s")

    stop_event = asyncio.Event()

    def handle_exit_signal(*_):
        print("\n[!] Shutdown signal received for Outbox Publisher. Draining...")
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
        asyncio.run(publisher.run_loop(poll_interval=args.poll_interval, stop_event=stop_event))
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        print("[*] Outbox Publisher daemon terminated cleanly.")


if __name__ == "__main__":
    main()
