#!/usr/bin/env python3
"""
Copyright LUT University 2026, all rights reserved.

Minimal service that

  * Scans a directory for *.yaml files,
  * Parses the booking information,
  * Stores it in Redis using RedisDict (key = order_number),
  * Re-scans the directory every 15 s for new/updated files.

All configuration values are defined as module-level constants so that
no external config files are required.
"""

from __future__ import annotations

import time
from datetime import datetime
from logging import getLogger
from zoneinfo import ZoneInfo
from pathlib import Path

import redis
import yaml
import dateparser

from server.data import BookingDetails
from server.utils.data_providers import BookingManager

INPUT_DIR: str = "/data/input"      # read-only bind-mount in the container
FILE_GLOB: str = "*.yaml"
SCAN_INTERVAL: int = 15             # seconds

# DB
REDIS_HOST: str = "redis"
REDIS_PORT: int = 6379
REDIS_DB: int = 0

log = getLogger()

def get_redis_client() -> redis.Redis:
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=None,
        decode_responses=True,
    )


def _try_parse_date(text: str) -> datetime | None:
    """Parse the Portuguese-style date string used by the service."""
    try:
        dt = dateparser.parse(
            text.replace("�s", "às"),
            languages=["pt"],
            settings={"DATE_ORDER": "MDY",
                      "PREFER_LOCALE_DATE_ORDER": False,
                      "TIMEZONE": "Europe/Lisbon",
                      "RETURN_AS_TIMEZONE_AWARE": True,
                      },
        )
        return dt
    except Exception as exc:
        log.error("Could not parse date %r - %s", text, exc)
        return None

def load_yaml_file(path: Path) -> tuple[str, BookingDetails] | None:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        order = str(raw["order_number"])
        order = "0"*(8-len(order)) + order
        start = _try_parse_date(raw["start_date"])
        end   = _try_parse_date(raw["end_date"])

        if not (order and start and end):
            raise ValueError("Missing or unparsable fields")

        duration = end - start
        details = BookingDetails(
            arrival_time=start,
            original_departure_time=end,
            departure_time=end,
            session_duration=duration,
        )
        return order, details
    except Exception as exc:
        log.error("Failed to process %s - %s", path, exc)
        return None


def scan_and_store(already_seen: set[Path], booking_store : BookingManager) -> set[Path]:
    input_path = Path(INPUT_DIR)
    if not input_path.is_dir():
        log.error("Input directory %s does not exist or is not a directory", INPUT_DIR)
        return already_seen

    yaml_files = sorted(input_path.glob(FILE_GLOB), key=lambda p: p.stat().st_mtime)

    for file_path in yaml_files:
        if file_path in already_seen:
            continue

        already_seen.add(file_path)
        result = load_yaml_file(file_path)
        if result is None:
            continue

        order_number, details = result
        try:
            booking_store[order_number] = details
            log.info("Processed %s (order %s)", file_path.name, order_number)
        except Exception as exc:
            log.error("Storing %s failed - %s", file_path.name, exc)

    return already_seen


def main() -> None:
    booking_store = BookingManager(redis=get_redis_client())
    log.info("Booking loader starting - watching %s", INPUT_DIR)

    seen = set()
    seen = scan_and_store(seen, booking_store)

    while True:
        time.sleep(SCAN_INTERVAL)
        seen = scan_and_store(seen, booking_store)


if __name__ == "__main__":
    main()
