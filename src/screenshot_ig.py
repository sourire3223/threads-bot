from datetime import datetime
from pathlib import Path

import requests
from loguru import logger
from playwright.sync_api import expect, sync_playwright


def post_time_to_int(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())


def capture_latest_stories(folder: Path, username: str):
    url = f"https://www.instagram.com/stories/{username}/"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 1024, "height": 1366},
            is_mobile=True,
            has_touch=True,
            storage_state=str(Path("auth.json")) if Path("auth.json").exists() else None,
        )
        page = context.new_page()
        page.goto(url)

        # 點擊查看限時動態
        view_btn = page.locator('div[role="button"]:has-text("查看限時動態")').first
        try:
            view_btn.wait_for(state="visible", timeout=10000)
            view_btn.click(force=True)
        except Exception:
            logger.info("未找到「查看限時動態」按鈕，直接開始。")

        downloaded_times = set()

        while True:
            try:
                # 1. 確保限動載入（以 time 標籤為基準）
                time_loc = page.locator("time").first
                time_loc.wait_for(state="visible", timeout=10000)

                # 2. 定位按鈕容器
                pause_btn = page.locator('div[role="button"]').filter(has=page.locator('svg[aria-label="暫停"]')).first
                play_btn = page.locator('div[role="button"]').filter(has=page.locator('svg[aria-label="播放"]')).first
                next_btn = page.locator('div[role="button"]').filter(has=page.locator('svg[aria-label="下一則"]')).first

                # 3. 執行暫停並確認狀態
                if pause_btn.is_visible():
                    pause_btn.click(force=True)
                    try:
                        expect(play_btn).to_be_visible(timeout=5000)
                    except Exception:
                        logger.warning("未能確認暫停狀態，繼續執行。")

                # 4. 抓取時間與圖片
                datetime_str = time_loc.get_attribute("datetime")
                if not datetime_str:
                    break

                time_s = post_time_to_int(datetime_str)

                # 鎖定主圖：排除大頭貼，利用 referrerpolicy 與 draggable
                img_locator = page.locator('img[referrerpolicy="origin-when-cross-origin"][draggable="false"]').last
                img_locator.wait_for(state="visible", timeout=5000)
                img_url = img_locator.get_attribute("src")

                # 5. 下載
                if img_url and time_s not in downloaded_times:
                    path = folder / f"{time_s}.webp"
                    if not path.exists():
                        img_data = requests.get(img_url).content
                        path.write_bytes(img_data)
                        logger.info(f"✅ 下載成功: {path}")
                    else:
                        logger.info(f"❌ 檔案已存在: {path}")

                    downloaded_times.add(time_s)

                # 6. 點擊下一則
                if next_btn.is_visible():
                    next_btn.click(force=True)
                    # 等待圖片 URL 變化，確保換頁完成
                    if img_url:
                        expect(img_locator).not_to_have_attribute("src", img_url, timeout=5000)
                else:
                    logger.info("已無「下一則」按鈕，結束抓取。")
                    break

            except Exception as e:
                logger.error(f"❌ 迴圈中斷: {e}")
                break

        browser.close()


if __name__ == "__main__":
    story_dir = Path("stories")
    story_dir.mkdir(parents=True, exist_ok=True)
    capture_latest_stories(story_dir, "paul_pork")
