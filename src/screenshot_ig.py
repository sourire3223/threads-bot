import time
from datetime import datetime
from pathlib import Path

import requests
from loguru import logger
from playwright.sync_api import expect, sync_playwright


def post_time_to_int(s: str) -> int:
    # 處理 ISO 格式時間戳
    return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())


def capture_latest_stories(folder: Path, username: str, auth_file: Path) -> list[Path]:
    url = f"https://www.instagram.com/stories/{username}/"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 1024, "height": 1366},
            is_mobile=True,
            has_touch=True,
            locale="zh-TW",
            storage_state=str(auth_file) if auth_file.exists() else None,
        )
        page = context.new_page()
        page.goto(url)
        # page.screenshot(path="debug.png")
        # 初始點擊進入限動
        try:
            view_btn = page.get_by_role("button", name="查看限時動態")
            view_btn.wait_for(state="visible", timeout=10000)
            view_btn.click(force=True)
        except Exception:
            logger.info("未發現起始按鈕，嘗試直接執行。")

        downloaded_times = set()
        story_paths = []
        last_img_url = ""

        while True:
            try:
                # 1. 等待時間標籤載入，確保內容已呈現
                time_loc = page.locator("time").first
                time_loc.wait_for(state="visible", timeout=10000)

                # 2. 執行暫停 (注入你測試成功的 JS)
                page.evaluate("""() => {
                    const btn = document.querySelector('div[role="button"] svg[aria-label="暫停"]')?.closest('div[role="button"]');
                    if (btn) btn.click();
                }""")

                # 3. 抓取主要圖片
                # 排除大頭貼，鎖定最後一個符合 referrerpolicy 的 img
                img_locator = page.locator('img[referrerpolicy="origin-when-cross-origin"][draggable="false"]').last
                img_locator.wait_for(state="visible", timeout=5000)

                # 確保圖片 URL 與上一張不同，避免重複抓取第一張
                if last_img_url:
                    expect(img_locator).not_to_have_attribute("src", last_img_url, timeout=7000)

                img_url = img_locator.get_attribute("src")
                datetime_str = time_loc.get_attribute("datetime")

                if not img_url or not datetime_str:
                    break

                time_s = post_time_to_int(datetime_str)

                # 4. 下載與存檔
                if time_s not in downloaded_times:
                    path = folder / f"{time_s}.webp"
                    if not path.exists():
                        img_data = requests.get(img_url).content
                        path.write_bytes(img_data)
                        logger.info(f"✅ 下載成功: {path}")
                        story_paths.append(path)

                    downloaded_times.add(time_s)
                    last_img_url = img_url

                # 5. 點擊下一則 (同樣使用 JS 點擊)
                has_next = page.evaluate("""() => {
                    const btn = document.querySelector('div[role="button"] svg[aria-label="下一則"]')?.closest('div[role="button"]');
                    if (btn) {
                        btn.click();
                        return true;
                    }
                    return false;
                }""")

                if not has_next:
                    logger.info("已達最後一則，抓取結束。")
                    break

            except Exception as e:
                logger.error(f"❌ 流程中斷: {e}")
                break

        browser.close()
        return story_paths


if __name__ == "__main__":
    story_dir = Path("stories")
    story_dir.mkdir(parents=True, exist_ok=True)
    # 執行抓取
    capture_latest_stories(story_dir, "paul_pork", auth_file=Path("auth.json"))
