FROM python:3.11

# Upgrade pip and system packages to reduce vulnerabilities
RUN apt-get update && apt-get upgrade -y && apt-get clean && rm -rf /var/lib/apt/lists/* \
	&& pip install --upgrade pip

# 作業ディレクトリを/appに設定
WORKDIR /app

# ローカルの全ファイルをコンテナの /app にコピー
COPY . .

# 依存ライブラリをインストール
RUN pip install --no-cache-dir -r requirements.txt

# 実行
CMD ["python", "mainfunc.py"]
