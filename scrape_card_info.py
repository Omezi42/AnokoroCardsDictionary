import os
import time
import pyautogui
from PIL import ImageGrab
import keyboard

# --- 座標設定 ---
# [基本画面]
REGIONS = {
    "name": (1030, 190, 1540, 250),
    "cost": (875, 187, 937, 259),
    "effect": (875, 342, 1610, 678),
    "power": (1050, 700, 1150, 740),
    "type": (1358, 693, 1578, 733),
    "set": (980, 777, 1360, 836),
    "tag": (366, 854, 684, 881)
}

# [詳細画面]
DETAIL_REGIONS = {
    "yomi": (878, 345, 1590, 378),
    "lore": (873, 379, 1610, 663)
}

# [ボタン座標]
NEXT_BUTTON_POS = (1730, 1010)
DETAIL_BUTTON_POS = (1498, 795)

# --- その他の設定 ---
OUTPUT_DIR = "card_images"
CAPTURE_LIMIT = 737 # 必要に応じて収集枚数を調整してください
WAIT_TIME_SHORT = 1.5
WAIT_TIME_LONG = 3.0

def setup_directories():
    """保存用フォルダの作成"""
    all_fields = list(REGIONS.keys()) + list(DETAIL_REGIONS.keys())
    for field in all_fields:
        dir_path = os.path.join(OUTPUT_DIR, field)
        os.makedirs(dir_path, exist_ok=True)
    print(f"📁 保存先フォルダを準備しました: {OUTPUT_DIR}/")

def capture_field(card_id, field_name, region):
    """指定の領域をキャプチャし、項目フォルダ内に {card_id}.png として保存"""
    try:
        img = ImageGrab.grab(bbox=region)
        save_path = os.path.join(OUTPUT_DIR, field_name, f"{card_id}.png")
        img.save(save_path)
        return True
    except Exception as e:
        print(f"❌ キャプチャエラー ({field_name}): {e}")
        return False

def safe_click(pos, sleep_after=0.5):
    """マウスを目標座標に滑らかに移動させ、少し待ってからクリックする安全なクリック関数"""
    pyautogui.moveTo(pos[0], pos[1], duration=0.2)
    time.sleep(0.1)
    pyautogui.click()
    time.sleep(sleep_after)

def get_card_info(card_id):
    print(f"  カード {card_id}: 基本情報をキャプチャ中...")
    # 1. 基本画面のキャプチャ
    for field_name, region in REGIONS.items():
        capture_field(card_id, field_name, region)
    
    # 2. 詳細画面へ移動 (View 1 -> View 2 -> View 3)
    safe_click(DETAIL_BUTTON_POS, sleep_after=0.6)  # View 1 -> View 2
    safe_click(DETAIL_BUTTON_POS, sleep_after=WAIT_TIME_SHORT)  # View 2 -> View 3

    print(f"  カード {card_id}: 詳細情報をキャプチャ中...")
    # 3. 詳細画面のキャプチャ
    for field_name, region in DETAIL_REGIONS.items():
        capture_field(card_id, field_name, region)

    # 4. 元の画面へ戻る (View 3 -> View 1)
    safe_click(DETAIL_BUTTON_POS, sleep_after=WAIT_TIME_SHORT)

def main_loop():
    setup_directories()
    print("🚀 自動収集を開始します。[Esc]で中断")
    
    for i in range(CAPTURE_LIMIT):
        card_id = i + 1
        if keyboard.is_pressed('esc'):
            print("\n🛑 中断しました")
            break
            
        print(f"\n--- カード {card_id}/{CAPTURE_LIMIT} ---")
        try:
            get_card_info(card_id)
            print(f"✅ カード {card_id} のキャプチャ完了")
        except Exception as e:
            print(f"❌ エラー: {e}")
        
        # 次のカードへ
        safe_click(NEXT_BUTTON_POS, sleep_after=WAIT_TIME_LONG)

if __name__ == "__main__":
    print("--- カード画像切り出し収集ツール ---")
    print(" [F7] : 自動収集を開始")
    while True:
        if keyboard.is_pressed('f7'):
            print("\n3秒後に開始します。ゲーム画面をアクティブにしてください...")
            time.sleep(3)
            main_loop()
            break
        time.sleep(0.1)