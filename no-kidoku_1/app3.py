import os
import asyncio
from dotenv import load_dotenv
from nio import AsyncClient, RoomMessageText, ReceiptEvent

# .env ファイルから環境変数を読み込み
load_dotenv()

HOMESERVER = os.getenv("MATRIX_HOMESERVER")
USER_ID = os.getenv("MATRIX_USER_ID")
ACCESS_TOKEN = os.getenv("MATRIX_ACCESS_TOKEN")

# 各部屋の未返信ステート管理
room_states = {}

REMIND_DELAY_SECONDS = 10  # リマインドまでの待機時間（秒）


async def remind_task(room_id, event_id, message_body):
    """
    既読（閲覧）検知後、指定時間待機して返信がなければアラートを出すタスク
    """
    print(f"\n[⏱️ タイマー開始] 閲覧（既読）を検知しました。{REMIND_DELAY_SECONDS}秒後に返信がないか確認します...")
    await asyncio.sleep(REMIND_DELAY_SECONDS)

    state = room_states.get(room_id)
    if state and state.get("unread_event_id") == event_id and not state.get("replied"):
        print(f"\n[⚠️ リマインド] 既読から{REMIND_DELAY_SECONDS}秒経過しましたが、まだ返信が行われていません！")
        print(f"   対象メッセージ: {message_body}")


async def on_message(room, event):
    """
    メッセージ受信および手動返信の検知
    """
    # 1. 相手からメッセージを受信した場合
    if event.sender != USER_ID:
        print(f"\n[受信] [{room.display_name}] {event.sender}: {event.body}")
        room_states[room.room_id] = {
            "unread_event_id": event.event_id,
            "message_body": event.body,
            "replied": False,
            "timer_started": False
        }

    # 2. 自分が返信メッセージを送った場合
    elif event.sender == USER_ID:
        if room.room_id in room_states:
            room_states[room.room_id]["replied"] = True
            print(f"[{room.display_name}] 自分の返信を検知しました。リマインドをキャンセルします。")


async def on_receipt(room, event):
    """
    ユーザーが画面上でメッセージを開いたことによる『既読イベント（m.receipt）』の検知
    """
    # matrix-nioのReceiptEventは event.receipts に既読情報が入ります
    for receipt in event.receipts:
        # 既読タイプが m.read かつ、ユーザーIDが自分（USER_ID）と一致するか確認
        if receipt.receipt_type == "m.read" and receipt.user_id == USER_ID:
            event_id = receipt.event_id
            state = room_states.get(room.room_id)
            
            # まだタイマーが始動しておらず、未返信メッセージの既読が確認された場合
            if state and state.get("unread_event_id") == event_id and not state.get("timer_started"):
                state["timer_started"] = True
                
                # 手動閲覧をトリガーにしてリマインドタイマーを起動
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

    print("Matrix手動閲覧検知リマインドアプリを起動中... (待機中)")
    
    try:
        await client.sync_forever(timeout=30000)
    finally:
        # ClientSessionの開いたまま（Unclosed）を防止
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())