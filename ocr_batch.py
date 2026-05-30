import os
import io
import json
import csv
import time
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List

# --- 設定 ---
def load_api_keys():
    """.envファイルからAPIキーを取得する"""
    keys = []
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        name, val = line.split("=", 1)
                        if name.strip() == "GEMINI_API_KEYS":
                            keys = [k.strip() for k in val.split(",") if k.strip()]
                            break
    return keys

API_KEYS = load_api_keys()
OUTPUT_DIR = "card_images"
JSON_OUTPUT = "card_database.json"
CSV_OUTPUT = "card_database.csv"
BATCH_SIZE = 10  # 1回のリクエストで処理するカード枚数
TOTAL_CARDS = 737
RATE_LIMIT_DELAY = 12.0  # リクエスト間のディレイ（秒）
MAX_RETRIES = 5  # エラー発生時の最大リトライ回数
RETRY_DELAY = 15.0  # リトライ時の待機時間（秒）

class CardInfo(BaseModel):
    card_id: int
    name: str = Field(description="カードの名前")
    cost: str = Field(description="コスト")
    effect: str = Field(description="効果テキスト")
    power: str = Field(description="パワー。数値がない場合は空文字")
    type: str = Field(description="種別。例: モンスター, 魔法, 罠など")
    set: str = Field(description="収録セット名")
    tag: str = Field(description="タグ")
    yomi: str = Field(description="カード名の読み仮名（カタカナなど）")
    lore: str = Field(description="フレーバーテキストやストーリー。ない場合は空文字")

class CardBatchResult(BaseModel):
    cards: List[CardInfo]

def load_existing_results():
    """既存の保存データから、既に処理されたカードIDのリストとデータを取得する"""
    if os.path.exists(JSON_OUTPUT):
        try:
            with open(JSON_OUTPUT, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "cards" in data:
                    return data["cards"]
                elif isinstance(data, list):
                    return data
        except Exception as e:
            print(f"[WARN] Failed to load {JSON_OUTPUT}: {e}. Creating new database.")
    return []

def save_results(cards):
    """JSONおよびCSVに解析結果を保存する"""
    # 昇順でソート
    cards = sorted(cards, key=lambda x: x["card_id"])
    
    # JSON保存
    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"cards": cards}, f, ensure_ascii=False, indent=2)
        
    # CSV保存
    if cards:
        fieldnames = ["card_id", "name", "yomi", "cost", "type", "power", "effect", "lore", "set", "tag"]
        with open(CSV_OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for card in cards:
                # Pydanticモデル由来、または辞書型のデータをCSV行に変換
                row = {field: card.get(field, "") for field in fieldnames}
                writer.writerow(row)

def make_card_collage(card_id):
    """1枚のカードの各項目画像を縦に連結したコラージュ画像を作成する"""
    fields = ["name", "cost", "effect", "power", "type", "set", "tag", "yomi", "lore"]
    images = []
    
    for f in fields:
        path = os.path.join(OUTPUT_DIR, f, f"{card_id}.png")
        if os.path.exists(path):
            images.append((f, Image.open(path)))
            
    if not images:
        return None
        
    # 全体のサイズ計算
    max_w = max(img.width for name, img in images)
    label_height = 20
    total_h = sum(img.height + label_height for name, img in images)
    
    # 結合画像の作成
    collage = Image.new("RGB", (max_w, total_h), color=(255, 255, 255))
    draw = ImageDraw.Draw(collage)
    
    try:
        font = ImageFont.truetype("msgothic.ttc", 14)
    except IOError:
        font = ImageFont.load_default()
        
    current_y = 0
    for name, img in images:
        # ラベル描画（黒背景に白文字）
        draw.rectangle([0, current_y, max_w, current_y + label_height], fill=(0, 0, 0))
        draw.text((10, current_y + 2), f"[{name.upper()}]", fill=(255, 255, 255), font=font)
        current_y += label_height
        
        # 貼り付け
        collage.paste(img, (0, current_y))
        current_y += img.height
        
    return collage

def process_batch(client, batch_cards):
    """バッチ処理を1回実行する"""
    contents = []
    prompt = (
        "添付された画像は、複数のカードそれぞれの各項目（NAME, COST, EFFECT, POWER, TYPE, SET, TAG, YOMI, LORE）を縦に結合したものです。\n"
        "各画像の上部には [項目名] の黒いラベルがあります。\n"
        "これらの画像を1枚ずつ解析し、文字起こしを行って、指定されたJSONフォーマットで出力してください。\n"
    )
    
    for card_id, img in batch_cards:
        prompt += f"- 画像 {card_id} は、カードID {card_id} の情報です。\n"
        contents.append(img)
        
    contents.append(prompt)
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=CardBatchResult,
            temperature=0.1
        )
    )
    data = json.loads(response.text)
    return data.get("cards", [])

def main():
    if not API_KEYS:
        print("[ERROR] No API keys found. Please define GEMINI_API_KEYS in your .env file.")
        return
        
    print("[INFO] Loading existing database...")
    existing_cards = load_existing_results()
    processed_ids = {c["card_id"] for c in existing_cards}
    print(f"[INFO] Found {len(processed_ids)} already processed cards.")
    
    # 未処理のカードIDリストを作成
    pending_ids = [card_id for card_id in range(1, TOTAL_CARDS + 1) if card_id not in processed_ids]
    if not pending_ids:
        print("[SUCCESS] All cards are already processed!")
        return
        
    print(f"[INFO] Pending cards to process: {len(pending_ids)} cards.")
    
    # APIキーの初期化
    current_key_idx = 0
    print(f"[INFO] Gemini Client initializing with key index {current_key_idx}...")
    client = genai.Client(api_key=API_KEYS[current_key_idx])
    
    # バッチ処理ループ
    all_results = list(existing_cards)
    
    # pending_ids を BATCH_SIZE ずつに分割
    for i in range(0, len(pending_ids), BATCH_SIZE):
        batch_ids = pending_ids[i:i + BATCH_SIZE]
        print(f"\n--- Processing Batch: Card {batch_ids[0]} to {batch_ids[-1]} ---")
        
        # コラージュ画像の準備
        batch_cards = []
        for card_id in batch_ids:
            img = make_card_collage(card_id)
            if img:
                batch_cards.append((card_id, img))
                
        if not batch_cards:
            print("[WARN] No images available in this batch. Skipping.")
            continue
            
        # リトライとキー切り替えの制御
        success = False
        batch_results = []
        
        for attempt in range(1, MAX_RETRIES + 1):
            print(f"[INFO] Sending batch to Gemini API (Attempt {attempt}/{MAX_RETRIES})...")
            try:
                batch_results = process_batch(client, batch_cards)
                success = True
                break
            except Exception as e:
                print(f"[WARN] Batch failed with current key (index {current_key_idx}): {e}")
                # 次のキーにローテーション
                current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                print(f"[INFO] Switching to API key index {current_key_idx}...")
                client = genai.Client(api_key=API_KEYS[current_key_idx])
                
                if attempt < MAX_RETRIES:
                    print(f"[INFO] Waiting {RETRY_DELAY} seconds before retrying...")
                    time.sleep(RETRY_DELAY)
        
        if success:
            # 結果の追加
            for r in batch_results:
                r_dict = r if isinstance(r, dict) else r.model_dump()
                if r_dict["card_id"] not in {c["card_id"] for c in all_results}:
                    all_results.append(r_dict)
                    
            # 保存
            save_results(all_results)
            print(f"[SUCCESS] Batch saved. Total processed: {len(all_results)}/{TOTAL_CARDS}")
        else:
            print("[ERROR] Batch failed completely after multiple retries on all keys.")
            print("[INFO] Saving current progress and exiting.")
            save_results(all_results)
            break
            
        # レートリミット回避のための待機
        if i + BATCH_SIZE < len(pending_ids):
            print(f"[INFO] Waiting {RATE_LIMIT_DELAY} seconds for rate limits...")
            time.sleep(RATE_LIMIT_DELAY)

if __name__ == "__main__":
    main()
