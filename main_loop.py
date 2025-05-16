import os
import time
from datetime import datetime

import cv2
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
from skimage.metrics import structural_similarity as ssim

THREAD_URL = "https://www.threads.net/@paul_pork/"
SELECTOR = "div.x1ypdohk.x1n2onr6.xvuun6i.x3qs2gp.x1w8tkb5.x8xoigl.xz9dl7a"
SCREENSHOT_DIR = "screenshots"
LAST_SCREENSHOT_PATH = os.path.join(SCREENSHOT_DIR, "latest.png")

INTERVAL_SECONDS = 600  # 每 10 分鐘截圖一次

os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def images_are_similar(img_path1, img_path2, threshold=0.97):
    img1 = cv2.cvtColor(np.array(Image.open(img_path1)), cv2.COLOR_RGB2GRAY)
    img2 = cv2.cvtColor(np.array(Image.open(img_path2)), cv2.COLOR_RGB2GRAY)

    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

    score, _ = ssim(img1, img2, full=True)
    print(f"🧪 SSIM 相似度：{score:.4f}")
    return score > threshold


def capture_latest_post(output_path="temp.png"):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state="auth.json",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
        )
        page = context.new_page()
        page.goto(THREAD_URL)
        page.wait_for_timeout(3000)

        try:
            page.wait_for_selector(SELECTOR, timeout=5000)
            first_post = page.locator(SELECTOR).first
            first_post.screenshot(path=output_path)
            print(f"📸 已截圖: {output_path}")
        except Exception as e:
            print("❌ 擷取失敗，儲存整頁截圖供除錯")
            page.screenshot(path="debug_full_page.png", full_page=True)
            print(e)

        browser.close()


def main_loop():
    while True:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_path = os.path.join(SCREENSHOT_DIR, "temp.png")
        capture_latest_post(temp_path)

        if os.path.exists(LAST_SCREENSHOT_PATH):
            if images_are_similar(temp_path, LAST_SCREENSHOT_PATH):
                print("🟡 與上一張圖相似，捨棄")
                os.remove(temp_path)
            else:
                new_path = os.path.join(
                    SCREENSHOT_DIR, f"post_{timestamp}.png")
                os.replace(temp_path, new_path)
                os.replace(new_path, LAST_SCREENSHOT_PATH)
                print(f"✅ 儲存新截圖: {new_path}")
        else:
            os.rename(temp_path, LAST_SCREENSHOT_PATH)
            print("✅ 儲存第一張截圖")

        print(f"⏳ 等待 {INTERVAL_SECONDS // 60} 分鐘...")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main_loop()
