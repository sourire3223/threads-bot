from playwright.sync_api import sync_playwright


def capture_latest_thread_post(
    url="https://www.threads.com/@paul_pork/",
    selector="div.x78zum5.xdt5ytf>div.x9f619.x1n2onr6.x1ja2u2z",
    output_path="single_thread_post.png",
    debug_path="debug_full_page.png",
    storage_state="auth.json"
):
    """
    擷取 Threads 首則串文的截圖，若失敗則截整頁 debug 畫面。
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=storage_state,
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
        )

        page = context.new_page()
        page.goto(url)
        page.wait_for_timeout(3000)

        # Optional: 儲存整頁方便除錯
        page.screenshot(path=debug_path, full_page=True)

        try:
            page.wait_for_selector(selector, timeout=3000)
            first_post = page.locator(selector).first
            first_post.screenshot(path=output_path)
            print(f"✅ 已擷取單一貼文至 {output_path}")
            success = True
        except Exception as e:
            print("❌ 擷取失敗，儲存整頁 debug 畫面")
            page.screenshot(path="debug.png")
            print(e)
            success = False
        finally:
            browser.close()

    return success
