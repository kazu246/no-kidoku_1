import os
import time
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from nio import AsyncClient, RoomMessageText, ReceiptEvent, RoomGetEventResponse
from aiohttp import web

# .env ファイルから環境変数を読み込み
load_dotenv()

HOMESERVER = os.getenv("MATRIX_HOMESERVER")
USER_ID = os.getenv("MATRIX_USER_ID")
ACCESS_TOKEN = os.getenv("MATRIX_ACCESS_TOKEN")
TARGET_ROOM_ID = os.getenv("MATRIX_ROOM_ID")  # 通知先のルームID

REMIND_DELAY_SECONDS = int(os.getenv("REMIND_DELAY_SECONDS", "10"))
MAX_MESSAGES = 200  # 画面用に保持する件数の上限（古いものから削除）
STATIC_DIR = Path(__file__).parent / "static"

# 既読を検知したメッセージだけを保存する（event_id -> 情報）
#   status: waiting（既読済み・返信待ち） / reminded（通知送信済み） / replied（返信済み）
messages = {}

client = None  # main() で作成


# ---------- メッセージ管理 ----------
def trim_messages():
    """上限を超えた分を古い順に削除する"""
    if len(messages) <= MAX_MESSAGES:
        return
    ordered = sorted(messages.items(), key=lambda kv: kv[1]["read_at"])
    for event_id, _ in ordered[: len(messages) - MAX_MESSAGES]:
        del messages[event_id]


def register_read_message(event_id, room_id, room_name, sender, body):
    """既読を検知したメッセージを登録し、リマインドタイマーを開始する"""
    if event_id in messages:
        return
    messages[event_id] = {
        "event_id": event_id,
        "room_id": room_id,
        "room_name": room_name,
        "sender": sender,
        "body": body,
        "read_at": time.time(),
        "status": "waiting",
    }
    trim_messages()
    print(f"\n[⏱️ タイマー開始] 既読を検知: [{room_name}] {sender}: {body}")
    asyncio.create_task(remind_task(event_id))


async def remind_task(event_id):
    await asyncio.sleep(REMIND_DELAY_SECONDS)
    msg = messages.get(event_id)

    # 待機中に返信された、または削除された場合は何もしない
    if not msg or msg["status"] != "waiting":
        return

    msg["status"] = "reminded"
    msg["reminded_at"] = time.time()
    print(f"\n[⚠️ リマインド] 既読から{REMIND_DELAY_SECONDS}秒経過しましたが、まだ返信がありません。")

    if not TARGET_ROOM_ID:
        print("※エラー: MATRIX_ROOM_IDが設定されていないため、通知を送信できません。")
        return
    if client is None:
        return

    try:
        await client.room_send(
            room_id=TARGET_ROOM_ID,
            message_type="m.room.message",
            content={
                "msgtype": "m.text",
                "body": f"🔔 【未返信リマインド】\n以下のメッセージにまだ返信していません！\n「{msg['body']}」",
            },
        )
        print("通知をElementに送信しました。")
    except Exception as e:
        print(f"※通知の送信に失敗しました: {e}")


# ---------- Matrix イベント ----------
async def on_message(room, event):
    # 相手のメッセージ（未読状態）は保存しない。自分の返信だけを検知する。
    if event.sender != USER_ID:
        return

    replied = 0
    for msg in messages.values():
        if msg["room_id"] == room.room_id and msg["status"] in ("waiting", "reminded"):
            msg["status"] = "replied"
            msg["replied_at"] = time.time()
            replied += 1
    if replied:
        print(f"[{room.display_name}] 自分の返信を検知しました。{replied}件を返信済みにしました。")


async def on_receipt(room, event):
    for receipt in event.receipts:
        if receipt.receipt_type != "m.read" or receipt.user_id != USER_ID:
            continue
        if receipt.event_id in messages:
            continue

        # 既読になったメッセージの本文をサーバーから取得する
        resp = await client.room_get_event(room.room_id, receipt.event_id)
        if not isinstance(resp, RoomGetEventResponse):
            continue
        ev = resp.event
        if not isinstance(ev, RoomMessageText) or ev.sender == USER_ID:
            continue  # 自分のメッセージや、テキスト以外は対象外

        register_read_message(
            event_id=ev.event_id,
            room_id=room.room_id,
            room_name=room.display_name,
            sender=ev.sender,
            body=ev.body,
        )


# ---------- API ----------
async def api_status(request):
    counts = {"unreplied": 0, "reminded": 0, "replied": 0}
    for msg in messages.values():
        if msg["status"] == "waiting":
            counts["unreplied"] += 1
        elif msg["status"] == "reminded":
            counts["reminded"] += 1
        else:
            counts["replied"] += 1
    counts["remind_delay_seconds"] = REMIND_DELAY_SECONDS
    return web.json_response(counts)


async def api_messages(request):
    now = time.time()
    items = []
    for msg in sorted(messages.values(), key=lambda m: m["read_at"], reverse=True):
        item = dict(msg)
        item["seconds_since_read"] = int(now - msg["read_at"])
        if msg["status"] == "waiting":
            item["seconds_until_remind"] = max(0, int(msg["read_at"] + REMIND_DELAY_SECONDS - now))
        items.append(item)
    return web.json_response(items)


async def api_simulate_read(request):
    """Matrixを使わずに『既読を検知した』状態を再現する（動作確認用）"""
    event_id = f"$demo-{int(time.time() * 1000)}"
    register_read_message(
        event_id=event_id,
        room_id="!demo:local",
        room_name="デモ",
        sender="@demo:local",
        body="これは動作確認用のメッセージです",
    )
    return web.json_response({"ok": True, "event_id": event_id})


async def api_simulate_reply(request):
    """デモ用：デモ部屋の待機中メッセージを返信済みにする"""
    for msg in messages.values():
        if msg["room_id"] == "!demo:local" and msg["status"] in ("waiting", "reminded"):
            msg["status"] = "replied"
            msg["replied_at"] = time.time()
    return web.json_response({"ok": True})


async def handle_index(request):
    return web.FileResponse(STATIC_DIR / "index.html")


# ---------- Webサーバー ----------
async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/messages", api_messages)
    app.router.add_post("/api/simulate-read", api_simulate_read)
    app.router.add_post("/api/simulate-reply", api_simulate_reply)
    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"[🌐 Webサーバー] ポート{port}で待機を開始しました。")


async def main():
    global client
    client = AsyncClient(HOMESERVER)
    client.user_id = USER_ID
    client.access_token = ACCESS_TOKEN
    client.device_id = "VSCODE_BOT"

    client.add_event_callback(on_message, RoomMessageText)
    client.add_ephemeral_callback(on_receipt, ReceiptEvent)

    await start_web_server()

    print("Matrix手動閲覧検知リマインドアプリを起動中... (待機中)")

    try:
        await client.sync_forever(timeout=30000)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
