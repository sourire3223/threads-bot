from loguru import logger
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # 開啟有頭模式讓你看到畫面
    context = browser.new_context()
    page = context.new_page()

    page.goto("https://www.threads.com/")

    input("📲 請登入 Instagram / Threads 並完成驗證後，按下 Enter 鍵繼續...")

    # 儲存登入狀態
    context.storage_state(path="auth.json")
    logger.info("✅ 登入狀態已儲存至 auth.json")
    browser.close()
