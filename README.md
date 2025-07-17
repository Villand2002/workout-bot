

# Discord Workout & Diary Bot

このプロジェクトは、**筋トレ記録管理**および**英語日記フィードバック**を行うDiscordボットです。
Firestore（Firebase）に記録を保存し、OpenAI APIを活用して筋トレのおすすめメニュー提案や英語日記のフィードバックを行います。



## ✅ 主な機能

### 1. 筋トレ記録・履歴表示

* `!workout_log`：筋トレ記録を登録
* `!workout_history`：最近5件の筋トレ履歴を表示
* `!workout_recommend`：過去のトレーニング履歴に基づきAIがおすすめメニューを提案

### 2. 英語日記フィードバック

* `!diary`：書いた英語日記に対して、文法チェックや自然な言い換え、便利な表現をAIがフィードバック
* フィードバック結果と日記はFirestoreに保存されます

---

## 🛠️ 使用技術

* **言語**: Python 3.12
* **フレームワーク/ライブラリ**:

  * [discord.py](https://discordpy.readthedocs.io/en/stable/) (v2.x, `discord.ext.commands` & スラッシュコマンド対応)
  * [Firebase Admin SDK](https://firebase.google.com/docs/admin/setup)
  * [OpenAI Python SDK](https://pypi.org/project/openai/)
  * [python-dotenv](https://pypi.org/project/python-dotenv/)
* **データベース**: Firestore (Firebase)


## 📦 セットアップ手順

### 1. リポジトリのクローン & 仮想環境

```bash
git clone <このリポジトリのURL>
cd <リポジトリ名>
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 2. 依存ライブラリのインストール

```bash
pip install -r requirements.txt
```

`requirements.txt` の例：

```
discord.py
firebase-admin
openai
python-dotenv
```

### 3. 環境変数ファイル `.env` の作成

ルートディレクトリに `.env` ファイルを作成し、以下を設定してください。

```env
DISCORD_BOT_TOKEN=チャンネルのDiscordBotトークン
SERVER_ID=DiscordサーバーID
CHANNEL_ID=筋トレ記録用チャンネルID
DIARY_CHANNEL_ID=日記用チャンネルID
OPENAI_API_KEY=あなたのOpenAI APIキー
FIREBASE_CREDENTIAL_JSON=Firebaseサービスアカウント鍵(JSONをbase64エンコードした文字列)
```

#### 🔹 Firebaseサービスアカウント鍵のBase64化例

```bash
base64 -i serviceAccountKey.json
```

この出力文字列をそのまま `FIREBASE_CREDENTIAL_JSON` にセットしてください。

---

## ▶️ 実行方法

```bash
python mainfunc.py
```

起動すると以下のようなメッセージがコンソールに表示されます：

```
BotName でログインしました！
ギルド同期完了: X個のコマンド
```

---

## 💬 利用方法（スラッシュコマンド）

### 1. 筋トレ関連

| コマンド                 | 説明                | 例                                                           |
| -------------------- | ----------------- | ----------------------------------------------------------- |
| `/workout_log`       | 筋トレ記録を登録          | `/workout_log category:胸 exercise:ベンチプレス weight:60 reps:10` |
| `/workout_history`   | 最近5件の筋トレ履歴を表示     | `/workout_history`                                          |
| `/workout_recommend` | AIが今日のおすすめメニューを提案 | `/workout_recommend`                                        |

### 2. 英語日記

| コマンド     | 説明                              | 例                                                               |
| -------- | ------------------------------- | --------------------------------------------------------------- |
| `/diary` | 英語日記を送信し、AIが文法チェックや表現改善をフィードバック | `/diary diary_text:"Today I went to the gym and trained hard."` |

---

## 🔖 Firestoreのデータ構造

```
training_logs (collection)
 └─ {user_id} (document)
     └─ logs (collection)
         └─ {auto_id} (document)
             ├─ category: "Chest"
             ├─ exercise: "Bench Press"
             ├─ weight: 60
             ├─ reps: 10
             └─ timestamp: 2025-07-17T10:00:00Z

diary_logs (collection)
 └─ {user_id} (document)
     └─ logs (collection)
         └─ {date_str} (document)
             ├─ date: "2025-07-17"
             ├─ diary_text: "Today I went to the gym and trained hard."
             ├─ ai_feedback: {grammar, rephrase, useful_phrases, advice}
             └─ timestamp: 2025-07-17T10:00:00Z
```

