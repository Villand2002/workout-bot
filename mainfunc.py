import os
import base64
import json
import discord
from discord.ext import commands
import firebase_admin
from firebase_admin import credentials, firestore
import datetime
from openai import OpenAI
from collections import defaultdict
from dotenv import load_dotenv

# .env 読み込み
load_dotenv()

# 環境変数取得
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
SERVER_ID = int(os.environ.get("SERVER_ID"))
WORKOUT_CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))
DIARY_CHANNEL_ID = int(os.environ.get("DIARY_CHANNEL_ID"))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
FIREBASE_CREDENTIAL_JSON = os.environ.get("FIREBASE_CREDENTIAL_JSON")

# Firebase初期化
decoded_credential = base64.b64decode(FIREBASE_CREDENTIAL_JSON).decode("utf-8")
cred_dict = json.loads(decoded_credential)
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

# OpenAI初期化
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# commands.Botを使用（推奨方法）
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'{bot.user} でログインしました！')
    try:
        # ギルド同期
        synced = await bot.tree.sync(guild=discord.Object(id=SERVER_ID))
        print(f'ギルド同期完了: {len(synced)}個のコマンド')
        
        # もしギルド同期が失敗したらグローバル同期
        if len(synced) == 0:
            print("ギルド同期失敗、グローバル同期を試行...")
            global_synced = await bot.tree.sync()
            print(f'グローバル同期完了: {len(global_synced)}個のコマンド')
            
    except Exception as e:
        print(f'同期エラー: {e}')

@bot.tree.command(name="workout_log", description="筋トレ記録を登録します", guild=discord.Object(id=SERVER_ID))
@discord.app_commands.describe(
    category="部位カテゴリーを選択してください",
    exercise="種目名",
    weight="重量 (kg)",
    reps="回数"
)
@discord.app_commands.choices(
    category=[
        discord.app_commands.Choice(name="胸", value="Chest"),
        discord.app_commands.Choice(name="背中", value="Back"),
        discord.app_commands.Choice(name="脚", value="Legs"),
        discord.app_commands.Choice(name="肩", value="Shoulders"),
        discord.app_commands.Choice(name="腕", value="Arms"),
        discord.app_commands.Choice(name="腹筋", value="Abs"),
    ]
)
async def workout_log(interaction: discord.Interaction, category: discord.app_commands.Choice[str], exercise: str, weight: int, reps: int):
    try:
        if interaction.channel.id != WORKOUT_CHANNEL_ID:
            await interaction.response.send_message("このコマンドは指定の筋トレチャンネルでのみ利用できます。", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        data = {
            'category': category.value,  # ここ注意：choiceのvalueを取る
            'exercise': exercise,
            'weight': weight,
            'reps': reps,
            'timestamp': firestore.SERVER_TIMESTAMP
        }
        db.collection('training_logs').document(user_id).collection('logs').add(data)
        await interaction.response.send_message(f"{category.name} - {exercise} {weight}kg x {reps}回 記録しました！")
    except Exception as e:
        print(f"Error in workout_log: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)


@bot.tree.command(name="workout_history", description="最近の筋トレ履歴を表示します", guild=discord.Object(id=SERVER_ID))
async def workout_history(interaction: discord.Interaction):
    try:
        if interaction.channel.id != WORKOUT_CHANNEL_ID:
            await interaction.response.send_message("このコマンドは指定の筋トレチャンネルでのみ利用できます。", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        logs_ref = db.collection('training_logs').document(user_id).collection('logs')
        docs = logs_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(5).stream()

        logs = [doc.to_dict() for doc in docs]
        if not logs:
            await interaction.response.send_message("まだ記録がありません。")
            return

        message = "最近の記録:\n"
        for entry in logs:
            ts = entry['timestamp'].strftime("%Y-%m-%d") if entry['timestamp'] else "日付不明"
            message += f"{ts}: {entry['category']} - {entry['exercise']} {entry['weight']}kg x {entry['reps']}回\n"
        await interaction.response.send_message(message)
    except Exception as e:
        print(f"Error in workout_history: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)

@bot.tree.command(name="workout_recommend", description="筋トレメニューをAIが提案します", guild=discord.Object(id=SERVER_ID))
async def workout_recommend(interaction: discord.Interaction):
    try:
        if interaction.channel.id != WORKOUT_CHANNEL_ID:
            await interaction.response.send_message("このコマンドは指定の筋トレチャンネルでのみ利用できます。", ephemeral=True)
            return

        await interaction.response.defer()

        user_id = str(interaction.user.id)
        logs_ref = db.collection('training_logs').document(user_id).collection('logs')
        docs = logs_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(100).stream()

        category_dates = defaultdict(lambda: datetime.datetime(2000, 1, 1))
        recent_logs = []

        for doc in docs:
            entry = doc.to_dict()
            category = entry['category']
            ts = entry['timestamp']
            if ts:
                if ts > category_dates[category]:
                    category_dates[category] = ts
                if ts >= datetime.datetime.utcnow() - datetime.timedelta(days=3):
                    ts_str = ts.strftime("%Y-%m-%d")
                    recent_logs.append(f"{ts_str}: {category} - {entry['exercise']} {entry['weight']}kg x {entry['reps']}回")

        if not category_dates:
            await interaction.followup.send("まだ記録がないので、まずは記録してください！")
            return

        sorted_categories = sorted(category_dates.items(), key=lambda x: x[1])
        target_category = sorted_categories[0][0]
        recent_summary = "\n".join(recent_logs) if recent_logs else "直近3日間にトレーニング記録はありません。"

        prompt = f"""
以下は直近3日間のトレーニング記録です：
{recent_summary}

筋肉のバランス、疲労を考慮して今日のダンベルトレーニングメニューを提案してください。
"""

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたは筋トレ専門のAIトレーナーです。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        reply = response.choices[0].message.content
        await interaction.followup.send(f"💡 今日のおすすめメニュー:\n{reply}")
    
    except Exception as e:
        print(f"Error in workout_recommend: {e}")
        if interaction.response.is_done():
            await interaction.followup.send("エラーが発生しました。")
        else:
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)

@bot.tree.command(name="diary", description="英語日記を書いてAIにフィードバックしてもらいます", guild=discord.Object(id=SERVER_ID))
async def diary(interaction: discord.Interaction, diary_text: str):
    try:
        if interaction.channel.id != DIARY_CHANNEL_ID:
            await interaction.response.send_message("このコマンドは指定の日記チャンネルでのみ利用できます。", ephemeral=True)
            return

        await interaction.response.defer()

        feedback_prompt = f"""
以下はユーザーが書いた英語日記です：

"{diary_text}"

あなたは英語学習のAIコーチです。
以下のJSON形式で出力してください。

{{
  "grammar": "...文法ミスや不自然な表現...",
  "rephrase": "...より自然な言い換え...",
  "useful_phrases": "...便利な表現やフレーズ...",
  "advice": "...簡単なアドバイス..."
}}

すべて日本語で出力してください。
余計な説明や前置きは不要です。JSONのみ返答してください。
"""

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたはプロの英語学習AIコーチです。"},
                {"role": "user", "content": feedback_prompt}
            ],
            temperature=0.5
        )

        reply = response.choices[0].message.content

        # JSONパース
        feedback_json = json.loads(reply)

        # フィードバックを整形して表示用にまとめる
        feedback_message = f"""📝 フィードバック:
【文法や表現の誤り】\n{feedback_json['grammar']}

【より自然な言い換え】\n{feedback_json['rephrase']}

【便利な表現やフレーズ】\n{feedback_json['useful_phrases']}

【アドバイス】\n{feedback_json['advice']}
"""
        await interaction.followup.send(feedback_message)

        # Firestoreに保存
        user_id = str(interaction.user.id)
        date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")

        db.collection('diary_logs').document(user_id).collection('logs').document(date_str).set({
            'date': date_str,
            'diary_text': diary_text,
            'ai_feedback': feedback_json,
            'timestamp': firestore.SERVER_TIMESTAMP
        })

    except Exception as e:
        print(f"Error in diary: {e}")
        if interaction.response.is_done():
            await interaction.followup.send("エラーが発生しました。")
        else:
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)


bot.run(DISCORD_BOT_TOKEN)