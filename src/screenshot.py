import time
from datetime import datetime
from pathlib import Path

from loguru import logger
from playwright.sync_api import sync_playwright

SELECTOR = "div.x78zum5.xdt5ytf>div.x9f619.x1n2onr6.x1ja2u2z"


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
        )
        page = context.new_page()
        page.goto(url)
        page.wait_for_timeout(3000)

        try:
            page.wait_for_selector(SELECTOR, timeout=3000)
            # remove dialog
            page.evaluate("""
                document.querySelectorAll('div[role="dialog"]').forEach(el => {
                    el.parentElement?.parentElement?.parentElement?.parentElement?.parentElement?.remove();
                });
            """)

            screenshot_paths = []
            current_time = int(time.time())

            for i in range(n_lookback):
                post = page.locator(SELECTOR).nth(i)
                # remove "Threads terms of use" alert
                page.evaluate("""
                    document.querySelectorAll('div[role="alert"]').forEach(el => {
                        el.parentElement?.parentElement?.parentElement?.parentElement?.remove();
                    });
                """)
                datetimes = post.evaluate("""
                    (post) => Array.from(post.querySelectorAll('time'))
                        .map(el => el.getAttribute('datetime'))
                """)

                time_s = post_time_to_int(max(datetimes))
                if time_s < current_time - time_lookback:
                    logger.info(f"❌ 時間不符合: {time_s} > {current_time - time_lookback}")
                    continue

                path = folder / f"{time_s}.png"
                if path.exists():
                    logger.info(f"❌ 檔案已存在: {path}")
                    continue

                post.screenshot(path=path)
                screenshot_paths.append(path)
                logger.info(f"✅ 擷取成功: {path}")
        except Exception as e:
            logger.info("❌ 擷取失敗:", e)
        finally:
            browser.close()

        return screenshot_paths


if __name__ == "__main__":
    # 確保目錄存在
    screenshot_dir = Path("screenshots")
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    # 擷取最新的 n 張截圖
    capture_latest_post_screenshots(screenshot_dir, "https://www.threads.com/@paul_pork/replies", n_lookback=7)
