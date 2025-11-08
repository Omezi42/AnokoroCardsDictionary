import os
import time
import csv
import pyautogui
import easyocr
from PIL import ImageGrab, Image, ImageOps, ImageEnhance
import keyboard
import numpy as np
import cv2

# --- 座標設定 ---
# [基本画面]
NAME_REGION = (1030, 190, 1540, 250)
COST_REGION = (875, 187, 937, 259)
EFFECT_REGION = (875, 342, 1610, 678)
POWER_REGION = (1050, 700, 1150, 740)
TYPE_REGION = (1358, 693, 1578, 733)
SET_REGION = (990, 777, 1327, 836)
TAG_REGION = (366, 854, 684, 881)
ORICA_REGION = (366, 854, 684, 881)

# [詳細画面]
YOMI_REGION = (878, 345, 1590, 378)
LORE_REGION = (873, 379, 1610, 663)

# [ボタン座標]
NEXT_BUTTON_POS = (1730, 1010)
DETAIL_BUTTON_POS = (1498, 795)

# --- その他の設定 ---
OUTPUT_FILE = "card_list_v2.csv"
CAPTURE_LIMIT = 3
WAIT_TIME_SHORT = 1.5
WAIT_TIME_LONG = 3.0

# --- OCR初期化 ---
print("OCRモデルを読み込んでいます...")
reader = easyocr.Reader(['ja', 'en'], gpu=False)
print("完了")

def preprocess_image(pil_img, scale=2.0):
    """OCR精度向上のための画像前処理"""
    img_np = np.array(pil_img)
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape[:2]
    gray = cv2.resize(gray, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_LINEAR)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )
    return binary

def ocr_region_high_acc(region, is_text_block=False, allowlist=None, join_sep=""):
    """
    高精度OCR処理
    - is_text_block: Trueなら文章として認識（段落結合）
    - allowlist: 認識を許可する文字セット（例: '0123456789'）
    - join_sep: 複数行認識された場合の結合文字（種別なら','、名前なら''など）
    """
    try:
        img = ImageGrab.grab(bbox=region)
        processed_img = preprocess_image(img, scale=3.0)

        # OCR実行
        # allowlistを設定することで、数字のみ読み取りなどを強制できる
        result = reader.readtext(
            processed_img, 
            detail=0, 
            paragraph=is_text_block,
            allowlist=allowlist
        )
        
        # 指定された区切り文字で結合
        text = join_sep.join(result).strip()
        return text
    except Exception as e:
        print(f"OCR Error: {e}")
        return ""

def extract_yomi(yomi_text, card_name):
    """読み仮名の抽出（ノイズ除去強化版）"""
    # カード名そのものが含まれていたら除去
    if card_name in yomi_text:
        yomi_text = yomi_text.replace(card_name, "").strip()

    separators = ['/', '／', ' ', '　', 'ノ', '-', ':']
    for sep in separators:
        # 区切り文字で分割してみる
        parts = yomi_text.split(sep)
        for part in parts:
            cleaned = part.strip()
            # カード名と異なり、かつ1文字以上ある部分を「読み」と推定
            if cleaned and cleaned != card_name and len(cleaned) > 1:
                 return cleaned
            
    return yomi_text.strip()

def determine_tag(tag_text):
    keywords = ["モンスター", "魔法", "罠", "フィールド", "エネルギー"]
    found_tags = []
    for keyword in keywords:
        if keyword in tag_text:
            found_tags.append(keyword)
    
    if found_tags:
        return ",".join(found_tags) # 複数ヒットしたらカンマ区切りで返す
    return "その他"

def get_card_info():
    info = {}
    print("  基本情報を取得中...")
    
    # 名前: スペースなしで結合
    info['name'] = ocr_region_high_acc(NAME_REGION, join_sep="")
    
    # コスト・パワー: 数字のみ許可
    info['cost'] = ocr_region_high_acc(COST_REGION, allowlist='0123456789')
    info['power'] = ocr_region_high_acc(POWER_REGION, allowlist='0123456789')
    
    # 種別・セット: カンマ区切りで結合
    info['type'] = ocr_region_high_acc(TYPE_REGION, join_sep=",")
    info['set'] = ocr_region_high_acc(SET_REGION, join_sep=",")
    
    # 効果: 文章ブロックとして認識
    info['effect'] = ocr_region_high_acc(EFFECT_REGION, is_text_block=True)
    
    # タグ・オリカ判定
    tag_region_text = ocr_region_high_acc(TAG_REGION)
    info['tag'] = determine_tag(tag_region_text)
    info['is_orica'] = "Yes" if "オリカ" in tag_region_text else "No"

    # 詳細画面へ移動
    pyautogui.click(DETAIL_BUTTON_POS)
    time.sleep(0.5)
    pyautogui.click(DETAIL_BUTTON_POS)
    time.sleep(WAIT_TIME_SHORT)

    print("  詳細情報を取得中...")
    raw_yomi = ocr_region_high_acc(YOMI_REGION, join_sep=" ")
    info['yomi'] = extract_yomi(raw_yomi, info['name'])
    info['lore'] = ocr_region_high_acc(LORE_REGION, is_text_block=True)

    # 元の画面へ戻る
    pyautogui.click(DETAIL_BUTTON_POS)
    time.sleep(WAIT_TIME_SHORT)

    return info

def save_to_csv(data_list):
    file_exists = os.path.isfile(OUTPUT_FILE)
    with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        fieldnames = ['name', 'yomi', 'cost', 'tag', 'type', 'power', 'effect', 'lore', 'set', 'is_orica']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(data_list)
    print(f"💾 保存完了: {OUTPUT_FILE}")

def warmup_ocr():
    """OCRエンジンの初回動作を安定させるためのウォームアップ"""
    print("OCRエンジンをウォームアップ中...")
    try:
        # 適当な小さな黒い画像を読ませる
        dummy = np.zeros((50, 50), dtype=np.uint8)
        reader.readtext(dummy, detail=0)
        print("ウォームアップ完了。")
    except Exception as e:
        print(f"ウォームアップ警告: {e}")

def main_loop():
    warmup_ocr()
    print("🚀 自動収集を開始します。[Esc]で中断")
    for i in range(CAPTURE_LIMIT):
        if keyboard.is_pressed('esc'):
            print("\n🛑 中断しました")
            break
        print(f"\n--- カード {i+1}/{CAPTURE_LIMIT} ---")
        try:
            card_info = get_card_info()
            print(f"✅ 取得: {card_info.get('name', 'Unknown')}")
            save_to_csv([card_info])
        except Exception as e:
            print(f"❌ エラー: {e}")
            # エラー時も一応次へ進むか、ここでリトライするか要検討
        
        pyautogui.click(NEXT_BUTTON_POS)
        time.sleep(WAIT_TIME_LONG)

if __name__ == "__main__":
    print("--- 高精度カード情報収集ツール v2 ---")
    print(" [F7] : 自動収集を開始")
    while True:
        if keyboard.is_pressed('f7'):
            print("\n3秒後に開始します。ゲーム画面をアクティブにしてください...")
            time.sleep(3)
            main_loop()
            break
        time.sleep(0.1)