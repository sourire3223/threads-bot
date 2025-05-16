import time
import hashlib
from pathlib import Path
from datetime import datetime
from PIL import Image
from screenshot_threads import capture_latest_thread_post

OUTPUT_DIR = Path("screenshots")
TEMP_IMAGE = OUTPUT_DIR / "temp_latest.png"
PREV_HASH_PATH = OUTPUT_DIR / "prev_hash.txt"

def image_hash(image_path):
    with Image.open(image_path) as img:
        return hashlib.md5(img.tobytes()).hexdigest()

def load_prev_hash():
    if PREV_HASH_PATH.exists():
        return PREV_HASH_PATH.read_text().strip()
    return ""

def save_prev_hash(hash_str):
    PREV_HASH_PATH.write_text(hash_str)

def main_loop(interval_minutes=10):
    OUTPUT_DIR.mkdir(exist_ok=True)

    while True:
        print("🔄 嘗試擷取最新 Threads 貼文截圖...")
        success = capture_latest_thread_post(output_path=str(TEMP_IMAGE))

        if success and TEMP_IMAGE.exists():
            new_hash = image_hash(TEMP_IMAGE)
            prev_hash = load_prev_hash()

            if new_hash == prev_hash:
                print("⚠️ 這次的截圖與上次相同，已略過儲存。")
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = OUTPUT_DIR / f"thread_{timestamp}.png"
                TEMP_IMAGE.rename(filename)
                print(f"✅ 新截圖儲存為 {filename}")
                save_prev_hash(new_hash)
        else:
            print("❌ 無法擷取貼文，請檢查登入狀態或選擇器。")

        print(f"⏳ 等待 {interval_minutes} 分鐘...\n")
        time.sleep(interval_minutes * 60)

if __name__ == "__main__":
    main_loop(interval_minutes=10)
