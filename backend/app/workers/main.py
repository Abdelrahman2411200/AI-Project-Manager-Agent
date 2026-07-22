import logging
import signal
import threading

from app.core.config import get_settings

logger = logging.getLogger(__name__)
shutdown_requested = threading.Event()


def _request_shutdown(signum: int, _frame: object) -> None:
    logger.info("worker_shutdown_requested", extra={"signal": signum})
    shutdown_requested.set()


def run() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)
    logger.info("worker_started", extra={"environment": settings.app_env})

    while not shutdown_requested.wait(timeout=15):
        logger.debug("worker_idle")

    logger.info("worker_stopped")


if __name__ == "__main__":
    run()
