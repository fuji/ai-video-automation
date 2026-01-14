# AI Video Automation - 詳細セットアップガイド

## 目次

1. [システム要件](#システム要件)
2. [APIキー取得手順](#apiキー取得手順)
3. [インストール手順](#インストール手順)
4. [設定ファイル](#設定ファイル)
5. [動作確認](#動作確認)
6. [トラブルシューティング](#トラブルシューティング)

---

## システム要件

### 必須

- Python 3.10以上
- FFmpeg
- 10GB以上の空きディスク容量
- インターネット接続

### 推奨

- メモリ: 16GB以上
- GPU: CUDA対応（動画エンコード高速化）

### OS別インストール

#### macOS

```bash
# Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python
brew install python@3.11

# FFmpeg
brew install ffmpeg
```

#### Ubuntu/Debian

```bash
sudo apt update
sudo apt install python3.11 python3.11-venv ffmpeg
```

#### Windows

1. [Python公式サイト](https://www.python.org/downloads/)からインストール
2. [FFmpeg公式サイト](https://ffmpeg.org/download.html)からダウンロード
3. FFmpegをPATHに追加

---

## APIキー取得手順

### 1. Gemini API（必須）

**URL**: https://aistudio.google.com/

#### 手順

1. Google AI Studioにアクセス
2. Googleアカウントでログイン
3. 左メニューの「Get API Key」をクリック
4. 「Create API Key」をクリック
5. プロジェクトを選択（または新規作成）
6. 表示されたAPIキーをコピー

#### 注意事項

- 無料枠: 15 RPM（リクエスト/分）、1,500 RPD（リクエスト/日）
- 画像生成は `gemini-2.0-flash-exp-image-generation` モデルを使用
- APIキーは公開しないこと

### 2. KLING AI（動画生成に必須）

**URL**: https://klingai.com/global/

#### 手順

1. KLINGにアクセス
2. アカウント作成（メール or Google/Apple ID）
3. ログイン後、DevToolsを開く（F12）
4. Application タブ → Cookies → klingai.com
5. すべてのCookie値をコピー

#### Cookie取得の詳細

```
# DevToolsで確認するCookie例
_ga=GA1.1.123456789.1234567890
_ga_XXXXXXXXXX=GS1.1.123456789.1.1.1234567890.0.0.0
_token=eyJhbGciOiJSUzI1NiIs...
```

すべてのCookieを `;` で連結して `.env` に設定:

```
KLING_COOKIE=_ga=GA1.1.123456789.1234567890; _token=eyJhbGci...
```

#### 注意事項

- Cookieは定期的に更新が必要（有効期限あり）
- std モード: 低クレジット消費、高速
- pro モード: 高クレジット消費、高品質

### 3. YouTube Data API（オプション）

**URL**: https://console.cloud.google.com/

#### 手順

1. Google Cloud Consoleにアクセス
2. 新規プロジェクトを作成
3. 「APIとサービス」→「ライブラリ」
4. 「YouTube Data API v3」を検索して有効化
5. 「認証情報」→「認証情報を作成」→「OAuth クライアント ID」
6. アプリケーションの種類: デスクトップアプリ
7. JSONファイルをダウンロード
8. `client_secrets.json` としてプロジェクトルートに配置

#### OAuth同意画面の設定

1. 「OAuth同意画面」を選択
2. ユーザータイプ: 外部
3. アプリ名、メールアドレスを入力
4. スコープ: `youtube.upload` を追加
5. テストユーザーに自分のメールを追加

---

## インストール手順

### 1. プロジェクトセットアップ

```bash
# ディレクトリに移動
cd /Users/fuji/work/fuji/ai-video-automation

# 仮想環境作成
python3 -m venv venv

# 仮想環境有効化
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 依存パッケージインストール
pip install -r requirements.txt
```

### 2. 環境変数設定

```bash
# テンプレートをコピー
cp .env.example .env

# エディタで編集
vim .env  # or code .env, nano .env
```

#### 最小構成（画像生成のみ）

```env
GEMINI_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

#### フル構成

```env
# Gemini
GEMINI_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXX
GEMINI_MODEL_IMAGE=gemini-2.0-flash-exp-image-generation

# KLING
KLING_COOKIE=_ga=GA1.1.xxx; _token=eyJhbG...
KLING_MODE=std
KLING_DURATION=5

# YouTube (optional)
YOUTUBE_CLIENT_SECRETS=client_secrets.json
```

### 3. 設定確認

```bash
python main.py config
```

出力例:
```
==================================================
AI Video Automation - 設定状態
==================================================

[Gemini API]
  API Key: ✓ 設定済み
  Text Model: gemini-2.0-flash
  Image Model: gemini-2.0-flash-exp-image-generation

[KLING AI]
  Cookie: ✓ 設定済み
  Mode: std
  Duration: 5s

[YouTube API]
  Client Secrets: client_secrets.json

[Output]
  Resolution: 1920x1080
  FPS: 30
==================================================
```

---

## 設定ファイル

### .env 全設定一覧

| 変数名 | 説明 | 必須 | デフォルト |
|--------|------|------|-----------|
| `GEMINI_API_KEY` | Gemini APIキー | ✓ | - |
| `GEMINI_MODEL_TEXT` | テキストモデル | - | gemini-2.0-flash |
| `GEMINI_MODEL_IMAGE` | 画像モデル | - | gemini-2.0-flash-exp-image-generation |
| `GEMINI_TEMPERATURE` | 創造性パラメータ | - | 0.9 |
| `KLING_COOKIE` | KLING認証Cookie | △ | - |
| `KLING_MODE` | 品質モード (std/pro) | - | std |
| `KLING_DURATION` | 動画長さ (5/10) | - | 5 |
| `KLING_TIMEOUT` | タイムアウト秒 | - | 600 |
| `VIDEO_FPS` | フレームレート | - | 30 |
| `VIDEO_RESOLUTION` | 解像度 | - | 1920x1080 |
| `LOG_LEVEL` | ログレベル | - | INFO |

---

## 動作確認

### 1. コンセプト生成テスト

```bash
python main.py concept --theme "テスト" --scenes 1
```

### 2. 画像生成テスト

```bash
# Pythonで直接テスト
python -c "
from src.generators import ImageGenerator
gen = ImageGenerator()
result = gen.generate('A beautiful sunset', 'test')
print(result)
"
```

### 3. フルパイプラインテスト

```bash
python main.py run --theme "サイバーパンク" --scenes 1 --skip-videos
```

---

## トラブルシューティング

### エラー: "ModuleNotFoundError"

```bash
# 仮想環境が有効か確認
which python

# 再インストール
pip install -r requirements.txt
```

### エラー: "FFmpeg not found"

```bash
# macOS
brew install ffmpeg

# インストール確認
ffmpeg -version
```

### エラー: "KLING API error"

1. Cookieの有効期限切れ → 再取得
2. クレジット不足 → KLINGでクレジット追加
3. レート制限 → しばらく待って再試行

### エラー: "YouTube upload failed"

1. `client_secrets.json` の存在確認
2. OAuth同意画面でテストユーザー追加確認
3. `youtube_credentials.json` を削除して再認証

### ログの確認

```bash
# 最新ログ
tail -f logs/ai_video_*.log

# エラーのみ
grep ERROR logs/ai_video_*.log
```

---

## 次のステップ

1. [README.md](./README.md) - 基本的な使い方
2. APIドキュメント
   - [Gemini API](https://ai.google.dev/docs)
   - [YouTube API](https://developers.google.com/youtube/v3)

---

*問題が解決しない場合は、ログファイルを確認してください。*
