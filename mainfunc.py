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
import re

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

# Discord Bot設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# JSON抽出関数
def extract_json(content):
    """AIの返答からJSON部分だけ抽出"""
    try:
        match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            match = re.search(r"(\{.*\})", content, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                raise ValueError("JSON部分が抽出できませんでした")
        return json.loads(json_str)
    except Exception as e:
        print(f"JSON抽出エラー: {e}")
        raise

# -------------------------------------
# 筋トレ用モーダル
# -------------------------------------

class WorkoutLogModal(discord.ui.Modal, title="筋トレ記録入力"):
    category_choices = [
        discord.SelectOption(label="胸", value="Chest"),
        discord.SelectOption(label="背中", value="Back"),
        discord.SelectOption(label="脚", value="Legs"),
        discord.SelectOption(label="肩", value="Shoulders"),
        discord.SelectOption(label="腕", value="Arms"),
        discord.SelectOption(label="腹筋", value="Abs"),
    ]
    category_select = discord.ui.Select(
        placeholder="部位を選択してください",
        options=category_choices
    )
    exercise = discord.ui.TextInput(label="種目名", required=True)
    weight = discord.ui.TextInput(label="重量(kg)", required=True)
    reps = discord.ui.TextInput(label="回数", required=True)

    def __init__(self):
        super().__init__()
        self.add_item(self.category_select)
        self.add_item(self.exercise)
        self.add_item(self.weight)
        self.add_item(self.reps)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.channel.id != WORKOUT_CHANNEL_ID:
            await interaction.response.send_message("このコマンドは指定の筋トレチャンネルでのみ利用できます。", ephemeral=True)
            return

        try:
            category = self.category_select.values[0]
            exercise = self.exercise.value
            weight = int(self.weight.value)
            reps = int(self.reps.value)

            user_id = str(interaction.user.id)
            data = {
                'category': category,
                'exercise': exercise,
                'weight': weight,
                'reps': reps,
                'timestamp': firestore.SERVER_TIMESTAMP
            }
            db.collection('training_logs').document(user_id).collection('logs').add(data)
            await interaction.response.send_message(f"{category} - {exercise} {weight}kg x {reps}回 記録しました！")

        except Exception as e:
            print(f"Error in workout log modal: {e}")
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)

# 筋トレおすすめ
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
            ts = entry.get('timestamp')
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


class DiaryModal(discord.ui.Modal, title="英語日記入力"):
    diary_entry = discord.ui.TextInput(label="日記本文", style=discord.TextStyle.paragraph, required=True, max_length=2000)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.channel.id != DIARY_CHANNEL_ID:
            await interaction.response.send_message("このコマンドは指定の日記チャンネルでのみ利用できます。", ephemeral=True)
            return

        diary_text = self.diary_entry.value
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

        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "あなたはプロの英語学習AIコーチです。"},
                    {"role": "user", "content": feedback_prompt}
                ],
                temperature=0.5
            )
            reply = response.choices[0].message.content
            feedback_json = extract_json(reply)

            feedback_message = f"""📝 フィードバック:
【文法や表現の誤り】\n{feedback_json['grammar']}

【より自然な言い換え】\n{feedback_json['rephrase']}

【便利な表現やフレーズ】\n{feedback_json['useful_phrases']}

【アドバイス】\n{feedback_json['advice']}
"""
            await interaction.followup.send(feedback_message)

            user_id = str(interaction.user.id)
            date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")

            db.collection('diary_logs').document(user_id).collection('logs').document(date_str).set({
                'date': date_str,
                'diary_text': diary_text,
                'ai_feedback': feedback_json,
                'timestamp': firestore.SERVER_TIMESTAMP
            })

        except Exception as e:
            print(f"Error in diary modal: {e}")
            await interaction.followup.send("エラーが発生しました。")

# -------------------------------------
# スラッシュコマンド登録
# -------------------------------------

@bot.event
async def on_ready():
    print(f'{bot.user} でログインしました！')
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=SERVER_ID))
        print(f'ギルド同期完了: {len(synced)}個のコマンド')
    except Exception as e:
        print(f'同期エラー: {e}')

@bot.tree.command(name="workout_log", description="筋トレ記録を登録します", guild=discord.Object(id=SERVER_ID))
async def workout_log(interaction: discord.Interaction):
    await interaction.response.send_modal(WorkoutLogModal())



@bot.tree.command(name="diary", description="英語日記を書いてAIにフィードバックしてもらいます", guild=discord.Object(id=SERVER_ID))
async def diary(interaction: discord.Interaction):
    await interaction.response.send_modal(DiaryModal())

# -------------------------------------
# (オプション) 以前の workout_history や recommend もそのまま使える
# -------------------------------------

bot.run(DISCORD_BOT_TOKEN)