import logging

logger = logging.getLogger(__name__)


class Scheduler:
    """定时调度占位。"""

    def start(self):
        logger.info("scheduler started")


__all__ = ["Scheduler"]
