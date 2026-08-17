import os
import sys

from loguru import logger

LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)


def setup_logging():
    """統一 log 格式與等級。設 LOG_LEVEL=DEBUG 可看到被跳過的貼文等細節。"""
    logger.remove()
    logger.add(
        sys.stderr,
        format=LOG_FORMAT,
        level=os.getenv("LOG_LEVEL", "INFO"),
        backtrace=True,
        diagnose=False,  # 關掉逐行變數 dump，例外的 traceback 才不會洗版
    )
