import contextlib
import time
from datetime import datetime
from pathlib import Path

from loguru import logger
from playwright.sync_api import sync_playwright

SELECTOR = 'div[data-pagelet^="threads_profile_posts_timeline_"]'

# 「Get the full app experience」安裝 App 彈窗。連同背景遮罩一起移除，所以要往上五層。
REMOVE_DIALOG_JS = """
    document.querySelectorAll('div[role="dialog"]').forEach(el => {
        el.parentElement?.parentElement?.parentElement?.parentElement?.parentElement?.remove();
    });
"""
# 「Threads terms of use」橫幅
REMOVE_ALERT_JS = """
    document.querySelectorAll('div[role="alert"]').forEach(el => {
        el.parentElement?.parentElement?.parentElement?.parentElement?.remove();
    });
"""
REMOVE_NAV_JS = """
    document.querySelectorAll('nav').forEach(el => {
        el.remove();
    });
"""


def post_time_to_int(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z").timestamp())


def capture_latest_post_screenshots(
    folder: Path, url: str, n_lookback: int = 5, time_lookback: int = 2147483647
) -> list[Path]:
    """擷取最新的 n 張，且時間在 current_time - time_lookback 之後的截圖"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 1688},  # height for long post
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
            color_scheme="dark",
            locale="zh-TW",  # 不設的話會跟著機器語系跑，截圖的 UI 語言會不一致
        )
        page = context.new_page()
        response = page.goto(url)
        page.wait_for_timeout(3000)
        screenshot_paths = []
        try:
            # 部署機比本機慢（本機量到 goto 後 2.1 秒才出現），選擇器一出現就會往下走，
            # 所以設寬一點不會讓正常情況變慢，只是別讓慢機器整輪擷取直接失敗。
            page.wait_for_selector(SELECTOR, timeout=30000)
            page.evaluate(REMOVE_DIALOG_JS)
            page.evaluate(REMOVE_NAV_JS)

            current_time = int(time.time())

            # 頁面上的貼文可能少於 n_lookback，不先數就會卡在不存在的 nth(i) 直到 timeout
            posts = page.locator(SELECTOR)
            n_posts = posts.count()
            if n_posts < n_lookback:
                logger.info(f"ℹ️ 頁面只有 {n_posts} 則貼文，少於 n_lookback={n_lookback}")
            logger.info(f"🔍 檢查 {url} 的 {min(n_lookback, n_posts)} 則貼文")

            for i in range(min(n_lookback, n_posts)):
                post = posts.nth(i)
                for _ in range(3):
                    page.evaluate(REMOVE_ALERT_JS)
                    time.sleep(1)
                datetimes = post.evaluate("""
                    (post) => Array.from(post.querySelectorAll('time'))
                        .map(el => el.getAttribute('datetime'))
                """)

                time_s = post_time_to_int(max(datetimes))
                if time_s < current_time - time_lookback:
                    logger.debug(f"⏭️ 貼文太舊，跳過: {time_s} < {current_time - time_lookback}")
                    continue

                path = folder / f"{time_s}.png"
                if path.exists():
                    logger.debug(f"⏭️ 檔案已存在，跳過: {path.name}")
                    continue

                # 安裝 App 彈窗可能在載入後才出現，或被截圖的捲動重新觸發，
                # 所以每次拍照前都要再清一次，不能只靠載入時那一次。
                page.evaluate(REMOVE_DIALOG_JS)

                post.screenshot(path=path)
                screenshot_paths.append(path)
                logger.success(f"✅ 貼文擷取成功: {path.name}")
        except Exception:
            # 光看 traceback 分不出是「載入太慢」還是「被 Meta 擋掉／登入牆」，
            # 所以把 HTTP 狀態、最終網址和頁面開頭一起記下來。
            status = response.status if response else "unknown"
            page_text = ""
            with contextlib.suppress(Exception):
                page_text = page.inner_text("body")[:200].replace("\n", " ")
            logger.exception(f"❌ 貼文擷取失敗（HTTP {status}｜{page.url}｜{page_text}）")
        finally:
            browser.close()

        return screenshot_paths


if __name__ == "__main__":
    from src.logging_config import setup_logging

    setup_logging()

    # 確保目錄存在
    screenshot_dir = Path("screenshots")
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    # 擷取最新的 n 張截圖
    capture_latest_post_screenshots(screenshot_dir, "https://www.threads.com/@paul_pork/replies", n_lookback=7)
