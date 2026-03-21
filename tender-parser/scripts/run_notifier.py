"""Entry point для GitHub Actions: рассылка уведомлений по подпискам."""

from __future__ import annotations

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("notifier")


def main():
    from pipeline.notifier import run_notifications

    logger.info("=== Starting notification sender ===")
    stats = run_notifications(since_minutes=65)
    logger.info(f"=== Done. Stats: {stats} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
