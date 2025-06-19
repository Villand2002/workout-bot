import os
import base64
import json
import discord
from discord.ext import commands, tasks
import firebase_admin
import asyncio
from firebase_admin import credentials, firestore
import datetime
import openai
from collections import defaultdict

# 環境変数取得
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
SERVER_ID = int(os.environ.get("SERVER_ID"))
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DIARY_CHANNEL_ID = int(os.environ.get("DIARY_CHANNEL_ID"))
FIREBASE_CREDENTIAL_JSON = os.environ.get("FIREBASE_CREDENTIAL_JSON")

# Firebase初期化
decoded_credential = base64.b64decode(FIREBASE_CREDENTIAL_JSON).decode("utf-8")
cred_dict = json.loads(decoded_credential)
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

# OpenAI初期化
openai.api_key = OPENAI_API_KEY

# Discord Bot設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# コマンド実行前にサーバー&チャンネル制限
@bot.check
async def only_in_target_guild_and_channel(ctx):
    return ctx.guild and ctx.guild.id == SERVER_ID and ctx.channel.id == CHANNEL_ID

# 筋トレ記録
@bot.command()
async def log(ctx, category, exercise, weight: int, reps: int):
    user_id = str(ctx.author.id)
    data = {
        'category': category,
        'exercise': exercise,
        'weight': weight,
        'reps': reps,
        'timestamp': firestore.SERVER_TIMESTAMP
    }
    db.collection('training_logs').document(user_id).collection('logs').add(data)
    await ctx.send(f"{category} - {exercise} {weight}kg x {reps}回 記録しました！")

# 履歴確認
@bot.command()
async def history(ctx):
    user_id = str(ctx.author.id)
    logs_ref = db.collection('training_logs').document(user_id).collection('logs')
    docs = logs_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(5).stream()

    logs = [doc.to_dict() for doc in docs]
    if not logs:
        await ctx.send("まだ記録がありません。")
        return

    message = "最近の記録:\n"
    for entry in logs:
        ts = entry['timestamp'].strftime("%Y-%m-%d") if entry['timestamp'] else "日付不明"
        message += f"{ts}: {entry['category']} - {entry['exercise']} {entry['weight']}kg x {entry['reps']}回\n"
    await ctx.send(message)


@bot.command()
async def recommend(ctx):
    user_id = str(ctx.author.id)
    logs_ref = db.collection('training_logs').document(user_id).collection('logs')
    docs = logs_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(100).stream()

    category_dates = defaultdict(lambda: datetime.datetime(2000, 1, 1))
    recent_logs = []

    for doc in docs:
        entry = doc.to_dict()
        category = entry['category']
        ts = entry['timestamp']
        if ts:
            # 各カテゴリの最新日更新
            if ts > category_dates[category]:
                category_dates[category] = ts

            # 直近3日分の記録を収集
            if ts >= datetime.datetime.utcnow() - datetime.timedelta(days=3):
                ts_str = ts.strftime("%Y-%m-%d")
                recent_logs.append(f"{ts_str}: {category} - {entry['exercise']} {entry['weight']}kg x {entry['reps']}回")

    if not category_dates:
        await ctx.send("まだ記録がないので、まずは記録してください！")
        return

    sorted_categories = sorted(category_dates.items(), key=lambda x: x[1])
    target_category = sorted_categories[0][0]

    # 直近3日分の履歴文作成
    if recent_logs:
        recent_summary = "\n".join(recent_logs)
    else:
        recent_summary = "直近3日間にトレーニング記録はありません。"

    # AIへのプロンプト
    prompt = f"""
あなたは優秀なパーソナルトレーナーです。
以下は直近3日間のトレーニング記録です：
{recent_summary}

今日の筋トレメニューを具体的に提案してください。
筋肉のバランス、疲労を考慮して提案してください。
種目名、セット数、回数、注意点なども具体的にお願いします。
"""

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "あなたは筋トレ専門のAIトレーナーです。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )

    reply = response['choices'][0]['message']['content']
    await ctx.send(f"💡 今日のおすすめメニュー（部位: {target_category}）：\n{reply}")
    
    
@bot.event
async def on_message(message):
    # Bot自身のメッセージは無視
    if message.author == bot.user:
        return

    # 日記チャンネルのみ反応
    if message.channel.id != DIARY_CHANNEL_ID:
        return

    # 英作文をAIにフィードバックさせる
    user_id = str(message.author.id)
    diary_text = message.content

    feedback_prompt = f"""
以下はユーザーが書いた英語日記です：

"{diary_text}"

あなたは英語学習のAIコーチです。この日記について以下のフィードバックをください：
1. 間違っている文法や表現
2. より自然な言い換え
3. 便利な表現やフレーズ
4. 簡単なアドバイス

日本語でわかりやすく解説してください。
"""

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "あなたはプロの英語学習AIコーチです。"},
            {"role": "user", "content": feedback_prompt}
        ],
        temperature=0.5
    )

    reply = response['choices'][0]['message']['content']

    await message.reply(f"📝 フィードバック:\n{reply}")

    # Firestoreに記録
    db.collection('diary_logs').document(user_id).collection('logs').add({
        'text': diary_text,
        'feedback': reply,
        'timestamp': firestore.SERVER_TIMESTAMP
    })



# 毎日12時リマインダー
@bot.event
async def on_ready():
    print(f'{bot.user} でログインしました！')
    reminder_loop.start()

@tasks.loop(minutes=1)
async def reminder_loop():
    now = datetime.datetime.now()
    if now.hour == 17 and now.minute == 0:
        guild = bot.get_guild(SERVER_ID)
        if guild:
            channel = guild.get_channel(CHANNEL_ID)
            if channel:
                await channel.send("💪 今日も筋トレ頑張りましょう！やる部位に困ったら `/recommend` を使ってね！")
        await asyncio.sleep(60)  # 重複送信防止
# 起動
bot.run(DISCORD_BOT_TOKEN)
