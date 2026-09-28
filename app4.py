import os
import asyncio
from dotenv import load_dotenv
from nio import AsyncClient, RoomMessageText, ReceiptEvent
from aiohttp import web

# .env ファイルから環境変数を読み込み
load_dotenv()

HOMESERVER = os.getenv("MATRIX_HOMESERVER")
USER_ID = os.getenv("MATRIX_USER_ID")
ACCESS_TOKEN = os.getenv("MATRIX_ACCESS_TOKEN")
# ★追加: 通知先のルームIDを環境変数から読み込む
TARGET_ROOM_ID = os.getenv("MATRIX_ROOM_ID")

# 各部屋の未返信ステート管理
room_states = {}
REMIND_DELAY_SECONDS = 10  # リマインドまでの待機時間（秒）

# --- 1. Webサーバー用の処理 ---
async def handle_request(request):
    return web.Response(text="Bot is successfully running as a Web Server!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_request)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"[🌐 Webサーバー] ポート{port}で待機を開始しました。")
# -------------------------------------

async def remind_task(room_id, event_id, message_body):
    print(f"\n[⏱️ タイマー開始] 閲覧（既読）を検知しました。{REMIND_DELAY_SECONDS}秒後に返信がないか確認します...")
    await asyncio.sleep(REMIND_DELAY_SECONDS)
    state = room_states.get(room_id)
    
    if state and state.get("unread_event_id") == event_id and not state.get("replied"):
        print(f"\n[⚠️ リマインド] 既読から{REMIND_DELAY_SECONDS}秒経過しましたが、まだ返信が行われていません！")
        
        # ★追加: 実際のMatrixルームに通知メッセージを送信する処理
        if TARGET_ROOM_ID:
            await client.room_send(
                room_id=TARGET_ROOM_ID,
                message_type="m.room.message",
                content={
                    "msgtype": "m.text",
                    "body": f"🔔 【未返信リマインド】\n以下のメッセージにまだ返信していません！\n「{message_body}」"
                }
            )
            print("通知をElementに送信しました。")
        else:
            print("※エラー: MATRIX_ROOM_IDが設定されていないため、通知を送信できません。")

async def on_message(room, event):
    if event.sender != USER_ID:
        print(f"\n[受信] [{room.display_name}] {event.sender}: {event.body}")
        room_states[room.room_id] = {
            "unread_event_id": event.event_id,
            "message_body": event.body,
            "replied": False,
            "timer_started": False
        }
    elif event.sender == USER_ID:
        if room.room_id in room_states:
            room_states[room.room_id]["replied"] = True
            print(f"[{room.display_name}] 自分の返信を検知しました。リマインドをキャンセルします。")

async def on_receipt(room, event):
    for receipt in event.receipts:
        if receipt.receipt_type == "m.read" and receipt.user_id == USER_ID:
            event_id = receipt.event_id
            state = room_states.get(room.room_id)
            if state and state.get("unread_event_id") == event_id and not state.get("timer_started"):
                state["timer_started"] = True
                asyncio.create_task(
                    remind_task(room.room_id, event_id, state["message_body"])
                )

async def main():
    global client
    client = AsyncClient(HOMESERVER)
    client.user_id = USER_ID
    client.access_token = ACCESS_TOKEN
    client.device_id = "VSCODE_BOT"

    client.add_event_callback(on_message, RoomMessageText)
    client.add_ephemeral_callback(on_receipt, ReceiptEvent)

    # --- 2. botの待機と一緒にWebサーバーも起動させる ---
    await start_web_server()

    print("Matrix手動閲覧検知リマインドアプリを起動中... (待機中)")
    
    try:
        await client.sync_forever(timeout=30000)
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())