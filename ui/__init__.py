import logging
from datetime import datetime

from core.config import REPO_ROOT

LOG_DIR = REPO_ROOT / "logs"


def _log_to_file() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    handler = logging.FileHandler(LOG_DIR / f"{datetime.now():%Y-%m-%d_%H-%M-%S}.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)


_log_to_file()
