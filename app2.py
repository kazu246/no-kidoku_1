import os
import asyncio
from dotenv import load_dotenv
from nio import AsyncClient, RoomMessageText, ReceiptEvent

# .env ファイルから環境変数を読み込み
load_dotenv()

HOMESERVER = os.getenv("MATRIX_HOMESERVER")
USER_ID = os.getenv("MATRIX_USER_ID")
ACCESS_TOKEN = os.getenv("MATRIX_ACCESS_TOKEN")

print(f"Loaded USER_ID: {USER_ID}")
print(f"Loaded TOKEN exists: {bool(ACCESS_TOKEN)}")

# 各部屋の最新メッセージ情報を管理する辞書
room_states = {}

REMIND_DELAY_SECONDS = 10  # リマインドまでの待機時間（秒）


async def remind_task(room_id, event_id, sender_name, message_body):
    """
    指定時間待機したのち、自分が返信していなければリマインドを出力するタスク
    """
    await asyncio.sleep(REMIND_DELAY_SECONDS)

    # 待機後、該当の部屋でまだ返信がされていないかチェック
    state = room_states.get(room_id)
    if state and state.get("last_event_id") == event_id and not state.get("replied", False):
        print(f"\n[⚠️ リマインド] [{sender_name}] からのメッセージへの返信がまだ行われていません！")
        print(f"  メッセージ内容: {message_body}")


async def on_message(room, event):
    # 自分以外のユーザーからメッセージを受信した場合（データ保持のみ、自動既読は打たない）
    if event.sender != USER_ID:
        print(f"\n[受信] [{room.display_name}] {event.sender}: {event.body}")

        room_states[room.room_id] = {
            "last_event_id": event.event_id,
            "sender_name": room.display_name,
            "body": event.body,
            "read": False,
            "replied": False
        }

    # 自分がメッセージ（手動返信）を送信した場合
    elif event.sender == USER_ID:
        if room.room_id in room_states:
            room_states[room.room_id]["replied"] = True
            print(f"[{room.display_name}] 自分の返信を検知しました。リマインドをキャンセルします。")


async def on_receipt(room, event):
    """
    Element等の画面で実際に既読がついた（ReceiptEvent）時の処理
    """
    receipt_dict = getattr(event, "receipt_dict", {})
    if not isinstance(receipt_dict, dict):
        return

    for event_id, receipt_types in receipt_dict.items():
        if not isinstance(receipt_types, dict):
            continue

        m_read = receipt_types.get("m.read", {})

        # 自分の操作によって画面で既読がついた場合
        if USER_ID in m_read:
            state = room_states.get(room.room_id)
            if state and state.get("last_event_id") == event_id and not state.get("read", False):
                state["read"] = True
                print(f"[{room.display_name}] 画面での既読を検知しました。{REMIND_DELAY_SECONDS}秒タイマーを開始します。")

                asyncio.create_task(
                    remind_task(
                        room.room_id,
                        event_id,
                        state["sender_name"],
                        state["body"]
                    )
                )


async def main():
    global client
    client = AsyncClient(HOMESERVER)

    client.user_id = USER_ID
    client.access_token = ACCESS_TOKEN
    client.device_id = "VSCODE_BOT"

    # 通常メッセージと画面での既読（エフェメラルイベント）を監視
    client.add_event_callback(on_message, RoomMessageText)
    client.add_ephemeral_callback(on_receipt, ReceiptEvent)

    print("Matrix既読検知＆リマインド管理アプリを起動中... (待機中)")
    try:
        await client.sync_forever(timeout=30000)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())