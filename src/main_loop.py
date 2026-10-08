import os
import time
from http import HTTPStatus
from pathlib import Path

import requests
from dotenv import load_dotenv
from loguru import logger

from src.logging_config import setup_logging
from src.screenshot_ig import capture_latest_stories
from src.screenshot_threads import capture_latest_post_screenshots, capture_latest_reply_parent_screenshots

load_dotenv()
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
THREAD_URLS = [
    "https://www.threads.com/@paul_pork/",
    "https://www.threads.com/@paul_pork/replies",
]
IG_USER = "paul_pork"
SCREENSHOT_DIR = Path("screenshots")

INTERVAL_SECONDS = 10 * 60  # 每 10 分鐘截圖一次


def send_image_to_discord(image_path: Path, webhook_url: str):
    with image_path.open("rb") as f:
        files = {"attachment": (image_path.as_posix(), f, "image/jpeg")}
        response = requests.post(webhook_url, files=files, timeout=10)
        if response.status_code == HTTPStatus.OK:
            logger.success(f"✅ 已發送到 Discord: {image_path.name}")
        else:
            logger.error(f"❌ 發送失敗（HTTP {response.status_code}）: {image_path.name}")
        return response


def main_loop():
    while True:
        new_post_paths = capture_latest_post_screenshots(
            SCREENSHOT_DIR, THREAD_URLS[0], n_lookback=24, time_lookback=144 * INTERVAL_SECONDS
        )
        new_reply_paths = capture_latest_post_screenshots(
            SCREENSHOT_DIR, THREAD_URLS[1], n_lookback=24, time_lookback=144 * INTERVAL_SECONDS
        )
        new_reply_parent_paths = capture_latest_reply_parent_screenshots(
            SCREENSHOT_DIR, THREAD_URLS[1], n_lookback=24, time_lookback=144 * INTERVAL_SECONDS
        )
        # new_story_paths = capture_latest_stories(SCREENSHOT_DIR, IG_USER, auth_file=Path("auth.json"))

        new_paths = sorted(new_reply_paths + new_post_paths + new_reply_parent_paths)
        if new_paths:
            logger.info(f"✨ 偵測到 {len(new_paths)} 則新內容，準備發送")
        else:
            logger.info("ℹ️ 沒有新內容")

        for post_path in new_paths:
            send_image_to_discord(post_path, WEBHOOK_URL)

        logger.info(f"⏳ 等待 {INTERVAL_SECONDS // 60} 分鐘")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    setup_logging()
    main_loop()
