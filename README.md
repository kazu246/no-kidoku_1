# Matrix 未返信リマインド

Matrix（Element）で、自分が**メッセージを既読にしたのに返信していない**場合に、一定時間後に通知ルームへリマインドを送るbotです。状況を確認できる簡易Web画面も付いています。

## 機能

- 自分が既読にした相手のメッセージを検知する
- 既読から一定時間（初期値10秒）返信がなければ、指定のルームに通知を送る
- 自分が返信すると、その部屋の返信待ちメッセージは「返信済み」になる
- ブラウザで件数（未返信 / リマインド済み / 返信完了）とメッセージ一覧を確認できる
- 「既読検知をシミュレート」ボタンで、Matrixを使わずに動作確認ができる

相手のメッセージは、既読になるまで保存しません。既読を検知した時点で、サーバーから本文を取得して登録します。

## ファイル構成

```
.
├── app5.py            # 本体（bot + Webサーバー + API）
├── app4.py            # 旧版（通知のみ・画面なし）
├── static/
│   └── index.html     # 画面
├── requirements.txt
└── .env               # 環境変数（Gitに含めない）
```

## 必要なもの

- Python 3.10 以上
- ライブラリ：`matrix-nio`（0.19 以上）、`aiohttp`、`python-dotenv`

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` の例：

```
matrix-nio
aiohttp
python-dotenv
```

## 環境変数（`.env`）

```
MATRIX_HOMESERVER=https://matrix.example.org
MATRIX_USER_ID=@yourname:example.org
MATRIX_ACCESS_TOKEN=xxxxxxxx
MATRIX_ROOM_ID=!xxxxxxxx:example.org
REMIND_DELAY_SECONDS=10
```

| 変数 | 内容 |
|---|---|
| `MATRIX_HOMESERVER` | Matrixサーバーの URL |
| `MATRIX_USER_ID` | 監視する自分のユーザーID |
| `MATRIX_ACCESS_TOKEN` | 自分のアクセストークン |
| `MATRIX_ROOM_ID` | リマインドを送る通知先のルームID |
| `REMIND_DELAY_SECONDS` | 既読からリマインドまでの秒数（省略時 10） |
| `PORT` | Webサーバーのポート（省略時 8080。Renderが自動で設定） |

`.env` にはトークンが含まれるので、**GitHubにpushしないでください**（`.gitignore` に追加）。

## 起動

```bash
python app5.py
```

仮想環境に入らずに起動する場合：

```bash
.venv/bin/python app5.py
```

起動後、ブラウザで `http://localhost:8080` を開きます。

## 動作確認

1. 画面の「既読検知をシミュレート」を押す
2. 「未返信」が1になり、設定した秒数後に「リマインド済み」へ変わる（通知ルームにもメッセージが届く）
3. 「デモに返信する」を押すと「返信完了」に変わる

実際に試す場合は、他の人からのメッセージをElementで開いて既読にします。

## 画面の状態

| 表示 | 意味 |
|---|---|
| 未返信（橙） | 既読済みで、まだ返信しておらず、リマインド前 |
| リマインド済み（青） | 通知を送信済みで、まだ返信がない |
| 返信完了（緑） | 自分が返信した |

## API

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/` | 画面 |
| GET | `/api/status` | 件数（未返信・リマインド済み・返信完了） |
| GET | `/api/messages` | メッセージ一覧（新しい順） |
| POST | `/api/simulate-read` | 既読検知のシミュレート（動作確認用） |
| POST | `/api/simulate-reply` | デモメッセージへの返信のシミュレート（動作確認用） |

## Render にデプロイ

1. `app5.py`、`static/`、`requirements.txt` をGitHubにpushする
2. Renderで Web Service を作成する
3. Build Command：`pip install -r requirements.txt`
4. Start Command：`python app5.py`
5. 環境変数（`.env` の内容）をRenderの Environment に登録する

## 注意点

- 状態はメモリ上にだけあるため、再起動やスリープで一覧は消える（最大200件）
- 画面とAPIには認証がないため、URLを知っている人は誰でも見られる
- 暗号化されたルームのメッセージは本文を読めないため、対象外
- 「既読」は、Matrixの既読通知（read receipt）を元に判定している

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `ModuleNotFoundError: No module named 'dotenv'` | 仮想環境に入り、`pip install -r requirements.txt` を実行する |
| `Address already in use`（Errno 98） | 8080番を使っているプログラムを止める：`ss -ltnp \| grep 8080` でPIDを調べ、`kill <PID>` |
| 画面が `ERR_INVALID_RESPONSE` になる | `static/index.html` の場所と名前を確認する（`index (1).html` になっていないか） |
| 通知が届かない | `MATRIX_ROOM_ID` が設定されているか、ターミナルのログを確認する |

## app4.py との違い

`app4.py` は通知だけの旧版です。`app5.py` は通知の動きはそのままに、既読メッセージの一覧保存、画面、APIを追加した版です。問題があれば、Start Command を `python app4.py` に戻せます。
