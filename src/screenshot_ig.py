import contextlib
import time
from datetime import datetime
from pathlib import Path

import requests
from loguru import logger
from playwright.sync_api import expect, sync_playwright

from src.playwright_utils import remove_stale_playwright_artifacts


def post_time_to_int(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z").timestamp())


class IGStoryCrawler:
    def __init__(self, page):
        self.page = page

    def enter_story(self):
        """初始點擊進入限動，同時檢查是否已經自動開始播放"""
        try:
            view_btn = self.page.get_by_role("button", name="查看限時動態")
            time_loc = self.page.locator("time")

            # 同時等待「查看限時動態」按鈕或「時間標籤」(表示已進入動態)
            view_btn.or_(time_loc).first.wait_for(state="visible", timeout=10000)

            if view_btn.is_visible():
                logger.debug("👆 點擊「查看限時動態」按鈕")
                view_btn.click(force=True)
            else:
                logger.debug("▶️ 已經進入限時動態播放畫面")
        except Exception:
            logger.debug("❔ 未發現起始狀態，嘗試直接執行")

    def pause_story(self):
        """執行暫停 (使用 JS 點擊)"""
        self.page.evaluate("""() => {
            const btn = document
                .querySelector('div[role="button"] svg[aria-label="暫停"]')
                ?.closest('div[role="button"]');
            if (btn) btn.click();
        }""")

    def next_story(self) -> bool:
        """點擊下一則 (使用 JS 點擊)"""
        return self.page.evaluate("""() => {
            const selector = 'div[role="button"] svg[aria-label="下一則"], '
                + 'div[role="button"] svg[aria-label="Next"]';
            const btn = document.querySelector(selector)?.closest('div[role="button"]');
            if (btn) { btn.click(); return true; }
            return false;
        }""")

    def wait_for_time_label(self):
        time_loc = self.page.locator("time").first
        time_loc.wait_for(state="visible", timeout=10000)
        return time_loc

    def get_image_locator(self):
        # 排除大頭貼，鎖定最後一個符合 referrerpolicy 的 img
        return self.page.locator('img[referrerpolicy="origin-when-cross-origin"][draggable="false"]').last

    def capture(self, folder: Path) -> list[Path]:
        """主要抓取流程：尋訪、截圖與下載"""
        self.enter_story()

        downloaded_times = set()
        story_paths = []
        last_img_url = ""

        while True:
            try:
                # 1. 等待時間標籤載入，確保內容已呈現
                time_loc = self.wait_for_time_label()

                # 2. 執行暫停
                self.pause_story()

                # 3. 判斷畫面是圖片、影片或錯誤
                img_base = self.page.locator('img[referrerpolicy="origin-when-cross-origin"][draggable="false"]')
                video_loc = self.page.locator("video")
                error_loc = self.page.get_by_text("播放此影片時發生問題")

                # 同時等待，任一出現即解除阻塞，避免影片浪費等待時間
                with contextlib.suppress(Exception):
                    img_base.or_(video_loc).or_(error_loc).first.wait_for(state="visible", timeout=3000)

                img_locator = self.get_image_locator()
                if not img_locator.is_visible():
                    logger.debug("⏭️ 畫面不是圖片（可能是影片或無法播放），跳過")
                    if not self.next_story():
                        logger.debug("🏁 已達最後一則")
                        break
                    time.sleep(0.5)  # 給予換頁緩衝
                    continue  # 進入下一輪迴圈

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
                        img_data = requests.get(img_url, timeout=30).content
                        path.write_bytes(img_data)
                        logger.success(f"✅ 限動下載成功: {path.name}")
                        story_paths.append(path)

                    downloaded_times.add(time_s)
                    last_img_url = img_url

                # 5. 點擊下一則
                if not self.next_story():
                    logger.debug("🏁 已達最後一則")
                    break

            except Exception:
                logger.exception("❌ 限動擷取流程中斷")
                break

        return story_paths


def capture_latest_stories(folder: Path, username: str, auth_file: Path) -> list[Path]:
    url = f"https://www.instagram.com/stories/{username}/"

    try:
        remove_stale_playwright_artifacts()
        with sync_playwright() as p:
            browser = None
            try:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15",
                    viewport={"width": 1024, "height": 1366},
                    is_mobile=True,
                    has_touch=True,
                    locale="zh-TW",
                    storage_state=str(auth_file) if auth_file.exists() else None,
                )
                page = context.new_page()
                page.goto(url)

                # 沒有限動或登入失效時，IG 會把 /stories/<user>/ 導向個人頁或登入頁。
                # IG 是 SPA，導向發生在 goto 回傳之後，所以要等 URL 變化再判斷；
                # 等到 timeout 代表沒被導走，也就是有限動可看。
                with contextlib.suppress(Exception):
                    page.wait_for_url(lambda u: "/stories/" not in u, timeout=5000)

                if "/stories/" not in page.url:
                    if "/accounts/login" in page.url:
                        logger.warning(f"⚠️ auth.json 可能已失效（被導向 {page.url}），請重跑 record_login.py")
                    else:
                        logger.info(f"ℹ️ 目前沒有可看的限時動態（被導向 {page.url}）")
                    return []

                return IGStoryCrawler(page).capture(folder)
            except Exception:
                logger.exception(f"❌ 限動擷取失敗（瀏覽器初始化或載入｜{url}）")
                return []
            finally:
                if browser:
                    browser.close()
    except Exception:
        logger.exception(f"❌ 無法啟動 Playwright（{url}）")
        return []


if __name__ == "__main__":
    from src.logging_config import setup_logging

    setup_logging()

    story_dir = Path("stories")
    story_dir.mkdir(parents=True, exist_ok=True)
    # 執行抓取
    capture_latest_stories(story_dir, "paul_pork", auth_file=Path("auth.json"))
