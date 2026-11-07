import contextlib
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger
from playwright.sync_api import sync_playwright

from src.playwright_utils import remove_stale_playwright_artifacts

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
REPLYING_TO_TARGET_PATTERN = re.compile(r"(?:Replying to|正在回覆|正在回复)\s*@paul_pork", re.IGNORECASE)
GHOST_EXPIRY_PATTERN = re.compile(r"\b\d+\s*(?:s|m|h|d)\s+left\b", re.IGNORECASE)
POST_PATH_PART_COUNT = 3
MAX_UNCHANGED_SCROLL_ROUNDS = 3
_threads_aymh_state = {"redirect_seen": False}


def is_post_permalink(url: str, username: str | None = None) -> bool:
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    if len(path_parts) != POST_PATH_PART_COUNT or path_parts[1] != "post":
        return False
    return username is None or path_parts[0] == f"@{username}"


def is_threads_aymh_redirect(url: str) -> bool:
    return urlparse(url).path.startswith("/aymh/")


def reset_threads_aymh_redirect_state() -> None:
    _threads_aymh_state["redirect_seen"] = False


def threads_aymh_redirect_seen() -> bool:
    return _threads_aymh_state["redirect_seen"]


def log_threads_navigation(page, response, requested_url: str, action: str) -> None:
    redirect_chain = []
    request = response.request if response else None
    while request:
        redirect_chain.append(request.url)
        request = request.redirected_from
    redirect_chain.reverse()
    status = response.status if response else "unknown"
    response_url = response.url if response else "unknown"
    content_type = response.headers.get("content-type", "unknown") if response else "unknown"
    logger.debug(
        f"Threads navigation [{action}] requested={requested_url} final={page.url} "
        f"response_url={response_url} status={status} content_type={content_type} "
        f"redirect_chain={redirect_chain}"
    )


def log_threads_aymh_redirect(page, response, requested_url: str, action: str) -> None:
    _threads_aymh_state["redirect_seen"] = True
    title = ""
    body = ""
    ready_state = "unknown"
    with contextlib.suppress(Exception):
        ready_state = page.evaluate("document.readyState")
    with contextlib.suppress(Exception):
        title = page.title()
    with contextlib.suppress(Exception):
        body = page.locator("body").inner_text(timeout=2000)[:1000].replace("\n", " ")
    log_threads_navigation(page, response, requested_url, action)
    logger.warning(
        f"⚠️ Threads 導向 /aymh/ 頁面，略過{action} "
        f"(requested={requested_url} final={page.url} readyState={ready_state} title={title!r} body={body!r})"
    )


def has_rendered_post_content(post) -> bool:
    return post.evaluate("""
        (post) => {
            const hasVisibleBodyText = Array.from(post.querySelectorAll('div[dir="auto"]'))
                .some(node => {
                    const text = node.innerText.trim();
                    const metadataPattern =
                        /^(paul_pork|translate|翻譯|[0-9]+|[0-9]+ *(?:秒|分鐘|小時|天|週|月|年|s|m|h|d))$/i;
                    const isMetadata = metadataPattern.test(text);
                    if (!text || isMetadata) return false;
                    if (!node.getClientRects().length) return false;
                    for (let ancestor = node; ancestor && ancestor !== post; ancestor = ancestor.parentElement) {
                        const style = getComputedStyle(ancestor);
                        if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) {
                            return false;
                        }
                    }
                    return true;
                });
            const hasLoadedMedia = Array.from(post.querySelectorAll('img'))
                .some(image => image.complete && image.naturalWidth > 150)
                || Array.from(post.querySelectorAll('video'))
                    .some(video => video.readyState >= 2);
            return Boolean(
                post.querySelector('time[datetime]')
                && post.querySelector('a[href*="/post/"]')
                && (hasVisibleBodyText || hasLoadedMedia)
            );
        }
    """)


def capture_ghost_root(  # noqa: PLR0911
    page, root_url: str, folder: Path, current_time: int, time_lookback: int
) -> Path | None:
    if threads_aymh_redirect_seen():
        return None
    response = page.goto(root_url, wait_until="domcontentloaded")
    page.wait_for_timeout(1800)
    log_threads_navigation(page, response, root_url, "ghost root")
    if is_threads_aymh_redirect(page.url):
        log_threads_aymh_redirect(page, response, root_url, "root 擷取")
        return None
    with contextlib.suppress(Exception):
        page.evaluate(REMOVE_DIALOG_JS)
    post = page.locator('div[data-pagelet="threads_post_page_1"]')
    if not post.count() or not post.get_by_text(GHOST_EXPIRY_PATTERN).count():
        logger.debug(f"⏭️ root 不是可見的 Ghost Post: {root_url}")
        return None
    datetimes = post.evaluate("""
        (post) => Array.from(post.querySelectorAll('time'))
            .map(el => el.getAttribute('datetime'))
            .filter(Boolean)
    """)
    if not datetimes:
        return None
    try:
        time_s = post_time_to_int(max(datetimes))
    except ValueError:
        return None
    if time_s < current_time - time_lookback:
        return None
    path = folder / f"{time_s}.png"
    if path.exists():
        return None
    for _ in range(3):
        page.evaluate(REMOVE_ALERT_JS)
        time.sleep(1)
    page.evaluate(REMOVE_DIALOG_JS)
    try:
        post.screenshot(path=path)
    except Exception:
        logger.exception(f"❌ Ghost 貼文截圖失敗: {root_url}")
        return None
    logger.success(f"✅ Ghost 貼文擷取成功: {path.name}")
    return path


def post_time_to_int(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z").timestamp())


def capture_latest_post_screenshots(  # noqa: PLR0912, PLR0915
    folder: Path, url: str, n_lookback: int = 5, time_lookback: int = 2147483647
) -> list[Path]:
    """擷取最新的 n 張，且時間在 current_time - time_lookback 之後的截圖"""
    screenshot_paths = []
    if threads_aymh_redirect_seen():
        logger.warning("⏸️ 本輪已遇到 Threads /aymh/ 導頁，略過後續擷取")
        return screenshot_paths
    try:
        remove_stale_playwright_artifacts()
        with sync_playwright() as p:
            browser = None
            try:
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
                log_threads_navigation(page, response, url, "profile/replies")
                if is_threads_aymh_redirect(page.url):
                    log_threads_aymh_redirect(page, response, url, "本輪擷取")
                    return screenshot_paths
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
                    post.scroll_into_view_if_needed()
                    for _ in range(20):
                        if has_rendered_post_content(post):
                            break
                        page.wait_for_timeout(1000)
                    else:
                        logger.warning(f"⚠️ 貼文內容或媒體未載入，略過第 {i + 1} 則")
                        continue

                    for _ in range(3):
                        page.evaluate(REMOVE_ALERT_JS)
                        time.sleep(1)
                    datetimes = post.evaluate("""
                        (post) => Array.from(post.querySelectorAll('time'))
                            .map(el => el.getAttribute('datetime'))
                            .filter(Boolean)
                    """)
                    if not datetimes:
                        logger.debug(f"⏭️ 貼文沒有有效時間，跳過第 {i + 1} 則")
                        continue

                    try:
                        time_s = post_time_to_int(max(datetimes))
                    except ValueError:
                        logger.debug(f"⏭️ 貼文時間格式無法解析，跳過第 {i + 1} 則: {datetimes}")
                        continue
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
                status = response.status if "response" in locals() and response else "unknown"
                page_text = ""
                with contextlib.suppress(Exception):
                    page_text = page.inner_text("body")[:200].replace("\n", " ")
                page_url = page.url if "page" in locals() else url
                logger.exception(f"❌ 貼文擷取失敗（HTTP {status}｜{page_url}｜{page_text}）")
            finally:
                if browser:
                    browser.close()
    except Exception:
        logger.exception(f"❌ 無法啟動 Playwright（{url}）")

    return screenshot_paths


def capture_latest_reply_parent_screenshots(  # noqa: PLR0912, PLR0915
    folder: Path, url: str, n_lookback: int = 5, time_lookback: int = 2147483647
) -> list[Path]:
    """Follow marked reply permalinks and capture Ghost parent posts."""
    screenshot_paths = []
    if threads_aymh_redirect_seen():
        logger.warning("⏸️ 本輪已遇到 Threads /aymh/ 導頁，略過後續擷取")
        return screenshot_paths
    try:
        remove_stale_playwright_artifacts()
        with sync_playwright() as p:
            browser = None
            try:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    color_scheme="dark",
                    locale="en-US",
                )
                page = context.new_page()
                response = page.goto(url)
                page.wait_for_timeout(3000)
                log_threads_navigation(page, response, url, "reply index")
                page.evaluate(REMOVE_DIALOG_JS)
                page.evaluate(REMOVE_NAV_JS)
                if is_threads_aymh_redirect(page.url):
                    log_threads_aymh_redirect(page, response, url, "本輪擷取")
                    return screenshot_paths

                reply_urls = []
                unchanged_rounds = 0
                for _ in range(30):
                    reply_markers = page.get_by_text(REPLYING_TO_TARGET_PATTERN)
                    previous_count = len(reply_urls)
                    for index in range(reply_markers.count()):
                        marker = reply_markers.nth(index)
                        card = marker.locator("xpath=ancestor::div[.//time][1]")
                        hrefs = card.locator("a[href*='/post/']").evaluate_all(
                            "links => [...new Set(links.map(link => link.href))]"
                        )
                        for href in hrefs:
                            if is_post_permalink(href) and not is_post_permalink(href, "paul_pork"):
                                if href not in reply_urls:
                                    reply_urls.append(href)
                                break
                    if len(reply_urls) >= n_lookback:
                        break
                    if len(reply_urls) == previous_count:
                        unchanged_rounds += 1
                        if unchanged_rounds >= MAX_UNCHANGED_SCROLL_ROUNDS:
                            break
                    else:
                        unchanged_rounds = 0
                    page.mouse.wheel(0, 1400)
                    page.wait_for_timeout(1200)
                    page.evaluate(REMOVE_DIALOG_JS)
                    page.evaluate(REMOVE_ALERT_JS)

                reply_urls = reply_urls[:n_lookback]
                logger.info(f"🔍 檢查 {url} 的 {len(reply_urls)} 則目標回覆")
                current_time = int(time.time())
                visited_roots = set()

                for reply_url in reply_urls:
                    if threads_aymh_redirect_seen():
                        return screenshot_paths
                    try:
                        reply_response = page.goto(reply_url, wait_until="domcontentloaded")
                    except Exception:
                        logger.exception(f"❌ 回覆 permalink 載入失敗: {reply_url}")
                        continue
                    page.wait_for_timeout(1800)
                    log_threads_navigation(page, reply_response, reply_url, "reply permalink")
                    if is_threads_aymh_redirect(page.url):
                        log_threads_aymh_redirect(page, reply_response, reply_url, "回覆 permalink 擷取")
                        return screenshot_paths
                    page.evaluate(REMOVE_DIALOG_JS)
                    parent_hrefs = page.locator("a[href*='/@paul_pork/post/']").evaluate_all(
                        "links => [...new Set(links.map(link => link.href))]"
                    )
                    root_urls = [href for href in parent_hrefs if is_post_permalink(href, "paul_pork")]
                    for root_url in root_urls:
                        if root_url in visited_roots:
                            continue
                        visited_roots.add(root_url)
                        path = capture_ghost_root(page, root_url, folder, current_time, time_lookback)
                        if path:
                            screenshot_paths.append(path)
            except Exception:
                status = response.status if "response" in locals() and response else "unknown"
                page_text = ""
                with contextlib.suppress(Exception):
                    page_text = page.inner_text("body")[:200].replace("\n", " ")
                page_url = page.url if "page" in locals() else url
                logger.exception(f"❌ 回覆 parent 擷取失敗（HTTP {status}｜{page_url}｜{page_text}）")
            finally:
                if browser:
                    browser.close()
    except Exception:
        logger.exception(f"❌ 無法啟動 Playwright（{url}）")

    return screenshot_paths


if __name__ == "__main__":
    from src.logging_config import setup_logging

    setup_logging()

    # 確保目錄存在
    screenshot_dir = Path("screenshots")
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    # 擷取最新的 n 張截圖
    capture_latest_post_screenshots(screenshot_dir, "https://www.threads.com/@paul_pork/replies", n_lookback=7)
