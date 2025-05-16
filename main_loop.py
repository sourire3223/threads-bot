import hashlib
import os
import time

import cv2
import numpy as np
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
THREAD_URL = "https://www.threads.net/@paul_pork/"
SELECTOR = "div.x1ypdohk.x1n2onr6.xvuun6i.x3qs2gp.x1w8tkb5.x8xoigl.xz9dl7a"
SCREENSHOT_DIR = "screenshots"
LAST_SCREENSHOT_PATH = os.path.join(SCREENSHOT_DIR, "latest.png")

INTERVAL_SECONDS = 600  # 每 10 分鐘截圖一次

PREVIOUS_IMAGE_PATH = os.path.join(SCREENSHOT_DIR, "previous.png")
CURRENT_IMAGE_PATH = os.path.join(SCREENSHOT_DIR, "latest.png")


def capture_post_screenshot(path: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state="auth.json",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
        )
        page = context.new_page()
        page.goto(THREAD_URL)
        page.wait_for_timeout(3000)

        try:
            page.wait_for_selector(SELECTOR, timeout=3000)
            post = page.locator(SELECTOR).nth(6)  # 第7個
            post.screenshot(path=path)
            print(f"✅ 擷取成功: {path}")
        except Exception as e:
            print("❌ 擷取失敗:", e)
        finally:
            browser.close()


def are_images_similar(path1: str, path2: str, threshold: float = 0.98) -> bool:
    if not os.path.exists(path1) or not os.path.exists(path2):
        return False

    img1 = cv2.imread(path1)
    img2 = cv2.imread(path2)

    if img1.shape != img2.shape:
        return False

    diff = cv2.absdiff(img1, img2)
    similarity = 1.0 - np.sum(diff) / (img1.shape[0] * img1.shape[1] * 255 * 3)
    print(f"🔍 圖片相似度: {similarity:.4f}")
    return similarity > threshold


def send_image_to_discord(image_path, webhook_url):
    with open(image_path, "rb") as f:
        files = {
            "attachment": (image_path, f, "image/jpeg")
        }
        response = requests.post(webhook_url, files=files, timeout=10)
        if response.status_code == 200:
            print("✅ 圖片已成功發送到 Discord")
        else:
            print(f"❌ 發送失敗: {response.status_code}")
        return response


def main_loop():
    while True:
        capture_post_screenshot(CURRENT_IMAGE_PATH)

        if not are_images_similar(PREVIOUS_IMAGE_PATH, CURRENT_IMAGE_PATH):
            print("✨ 偵測到新貼文，準備發送")
            send_image_to_discord(CURRENT_IMAGE_PATH, WEBHOOK_URL)
            os.replace(CURRENT_IMAGE_PATH, PREVIOUS_IMAGE_PATH)
        else:
            print("🟰 圖片相同，略過發送")

        print(f"⏳ 等待 {INTERVAL_SECONDS // 60} 分鐘...")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main_loop()
