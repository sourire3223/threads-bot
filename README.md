# Threads 自動截圖工具
這個專案利用 Playwright 自動化瀏覽器，定期抓取 Meta Threads 使用者的最新貼文，並將指定貼文截圖保存。支援無頭模式（背景執行）和重複圖片判斷，避免重複儲存相同貼文。此專案由 chatGPT 輔助生成。

---

## 功能
* 自動打開 Threads 頁面，登入後定期擷取最新貼文截圖。

* 自動比對新舊截圖，避免重複儲存相同圖片。

* 支援無頭模式，可在後台執行。

* 輸出時間戳記命名的圖片檔，方便後續使用和整理。

---

## 環境需求
* `Python 3.8+`

* `Playwright`

* `Pillow (PIL)`

* 其他依賴請見 `requirements.txt`

---


## 安裝
### 1. 從 GitHub 下載專案
```console
git clone git@github.com:water200427/threads_bot.git
cd threads_bot
```
### 2. 安裝依賴
```console
pip install -r requirements.txt
python -m playwright install
```

## 使用前準備
```console
python record_login.py
```
首次需要使用 `playwright` 進入瀏覽器登入帳號，登入後在 `console` 按下 `Enter`，會自動儲存登入狀態檔 `auth.json`。


## 使用
```console
python main_loop.py
```
程式將每 10 分鐘抓取最新貼文截圖，並與前次圖片比對。
若圖片不同則儲存，否則略過。

## **結果位置**：
所有截圖會存在 `screenshots/` 資料夾，圖片名稱包含截圖時間。

---

## 檔案說明
* `screenshot_threads.py`：封裝擷取單則 Threads 貼文的函式。

* `main_loop.py`：定時呼叫截圖函式，進行圖片比對與管理。

* `auth.json`：Playwright 登入狀態檔（需自行產生）。

* `screenshots/`：存放所有截圖和 hash 記錄。

---

## 注意事項

* `Threads` 介面和 `class` 名可能變動，如失效請更新 `screenshot_threads.py` 中的 CSS 選擇器。

* 無頭模式下無法手動操作，請確保登入狀態有效。

* 需要穩定網路和持續運行 Python 腳本。

---

## 可擴充功能建議
* 新增錯誤日誌記錄功能。

* 串接通知機制（如 Discord、Telegram）提醒有新貼文截圖。

* 自動清理過舊的截圖檔案。