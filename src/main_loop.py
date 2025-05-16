import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from loguru import logger

from src.screenshot import capture_latest_post_screenshots

load_dotenv()
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
THREAD_URLS = [
    "https://www.threads.com/@paul_pork/",
    "https://www.threads.com/@paul_pork/replies",
]
SCREENSHOT_DIR = Path("screenshots")

INTERVAL_SECONDS = 180  # 每 10 分鐘截圖一次


def send_image_to_discord(image_path: Path, webhook_url: str):
    with image_path.open("rb") as f:
        files = {"attachment": (image_path.as_posix(), f, "image/jpeg")}
        response = requests.post(webhook_url, files=files, timeout=10)
        if response.status_code == 200:
            logger.info("✅ 圖片已成功發送到 Discord")
        else:
            logger.info(f"❌ 發送失敗: {response.status_code}")
        return response


def main_loop():
    while True:
        new_post_paths = capture_latest_post_screenshots(
            SCREENSHOT_DIR, THREAD_URLS[0], n_lookback=5, time_lookback=INTERVAL_SECONDS
        )
        new_reply_paths = capture_latest_post_screenshots(
            SCREENSHOT_DIR, THREAD_URLS[1], n_lookback=5, time_lookback=INTERVAL_SECONDS
        )

        for post_path in sorted(new_reply_paths + new_post_paths):
            print("✨ 偵測到新貼文，準備發送")
            send_image_to_discord(post_path, WEBHOOK_URL)

        print(f"⏳ 等待 {INTERVAL_SECONDS // 60} 分鐘...")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main_loop()
