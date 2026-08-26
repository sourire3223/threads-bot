import contextlib
import shutil
import tempfile
from pathlib import Path


def remove_stale_playwright_artifacts() -> None:
    """移除上次 Chromium 異常結束時遺留的 Playwright 暫存目錄。"""
    for path in Path(tempfile.gettempdir()).glob("playwright-artifacts-*"):
        if path.is_dir():
            with contextlib.suppress(OSError):
                shutil.rmtree(path)
