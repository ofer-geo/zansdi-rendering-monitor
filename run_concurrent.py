from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


PROJECT_DIRECTORY = Path(__file__).resolve().parent


def start_worker(
    worker_number: int,
    stagger_seconds: float,
) -> subprocess.Popen:
    environment = os.environ.copy()

    environment["WORKER_NUMBER"] = str(worker_number)
    environment["START_DELAY_SECONDS"] = str(
        (worker_number - 1) * stagger_seconds
    )

    print(
        f"Starting User-{worker_number} "
        f"with delay "
        f"{environment['START_DELAY_SECONDS']} seconds",
        flush=True,
    )

    return subprocess.Popen(
        [
            sys.executable,
            "monitor.py",
        ],
        cwd=PROJECT_DIRECTORY,
        env=environment,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run concurrent ZanSDI synthetic users."
    )

    parser.add_argument(
        "--users",
        type=int,
        default=2,
        help="Number of synthetic users to run.",
    )

    parser.add_argument(
        "--stagger",
        type=float,
        default=8.0,
        help="Seconds between user starts.",
    )

    args = parser.parse_args()

    if args.users < 1:
        raise ValueError(
            "The number of users must be at least 1."
        )

    if args.users > 6:
        raise ValueError(
            "Only 6 monitoring accounts are currently configured."
        )

    if args.stagger < 0:
        raise ValueError(
            "The stagger value cannot be negative."
        )

    processes: list[tuple[int, subprocess.Popen]] = []

    try:
        for worker_number in range(1, args.users + 1):
            process = start_worker(
                worker_number=worker_number,
                stagger_seconds=args.stagger,
            )

            processes.append(
                (worker_number, process)
            )

        failed_workers: list[int] = []

        for worker_number, process in processes:
            return_code = process.wait()

            if return_code != 0:
                failed_workers.append(worker_number)

        print()
        print("=" * 80)

        if failed_workers:
            print(
                "Failed users: "
                + ", ".join(
                    f"User-{number}"
                    for number in failed_workers
                )
            )
        else:
            print(
                f"All {args.users} users completed successfully."
            )

        print("=" * 80)

    except KeyboardInterrupt:
        print(
            "\nStopping all users...",
            flush=True,
        )

        for _, process in processes:
            if process.poll() is None:
                process.terminate()

        for _, process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()