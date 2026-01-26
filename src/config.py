"""設定管理モジュール - 環境変数とアプリケーション設定"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# パス設定
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"
IMAGES_DIR = OUTPUT_DIR / "images"
VIDEOS_DIR = OUTPUT_DIR / "videos"
FINAL_DIR = OUTPUT_DIR / "final"
LOGS_DIR = BASE_DIR / "logs"

# ディレクトリ作成
for d in [OUTPUT_DIR, IMAGES_DIR, VIDEOS_DIR, FINAL_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


@dataclass
class GeminiConfig:
    """Gemini API設定"""
    api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    model_text: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL_TEXT", "gemini-2.0-flash"))
    model_image: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL_IMAGE", "gemini-2.0-flash-exp-image-generation"))
    temperature: float = field(default_factory=lambda: float(os.getenv("GEMINI_TEMPERATURE", "0.9")))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("GEMINI_MAX_TOKENS", "4096")))


@dataclass
class FalConfig:
    """fal.ai API設定（Flux Pro）"""
    api_key: str = field(default_factory=lambda: os.getenv("FAL_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("FAL_MODEL", "fal-ai/flux-pro/v1.1"))
    image_size: str = field(default_factory=lambda: os.getenv("FAL_IMAGE_SIZE", "landscape_16_9"))


@dataclass
class KlingConfig:
    """KLING AI SDK設定"""
    cookie: str = field(default_factory=lambda: os.getenv("KLING_COOKIE", ""))
    mode: str = field(default_factory=lambda: os.getenv("KLING_MODE", "std"))  # std or pro
    duration: int = field(default_factory=lambda: int(os.getenv("KLING_DURATION", "5")))
    aspect_ratio: str = field(default_factory=lambda: os.getenv("KLING_ASPECT_RATIO", "16:9"))
    timeout: int = field(default_factory=lambda: int(os.getenv("KLING_TIMEOUT", "600")))
    poll_interval: int = field(default_factory=lambda: int(os.getenv("KLING_POLL_INTERVAL", "30")))


@dataclass
class YouTubeConfig:
    """YouTube API設定"""
    client_secrets_file: str = field(default_factory=lambda: os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json"))
    credentials_file: str = field(default_factory=lambda: os.getenv("YOUTUBE_CREDENTIALS", "youtube_credentials.json"))
    scopes: list = field(default_factory=lambda: ["https://www.googleapis.com/auth/youtube.upload"])


@dataclass
class NewsConfig:
    """ニュース取得設定"""
    source: str = field(default_factory=lambda: os.getenv("NEWS_SOURCE", "yahoo"))
    category: str = field(default_factory=lambda: os.getenv("NEWS_CATEGORY", "entertainment"))
    channel_name: str = field(default_factory=lambda: os.getenv("NEWS_CHANNEL_NAME", "FJ News 24"))
    limit: int = field(default_factory=lambda: int(os.getenv("NEWS_LIMIT", "10")))


@dataclass
class VideoConfig:
    """動画編集設定"""
    fps: int = field(default_factory=lambda: int(os.getenv("VIDEO_FPS", "30")))
    resolution: str = field(default_factory=lambda: os.getenv("VIDEO_RESOLUTION", "1920x1080"))
    codec: str = field(default_factory=lambda: os.getenv("VIDEO_CODEC", "libx264"))
    bitrate: str = field(default_factory=lambda: os.getenv("VIDEO_BITRATE", "5M"))
    audio_codec: str = field(default_factory=lambda: os.getenv("AUDIO_CODEC", "aac"))
    transition_duration: float = field(default_factory=lambda: float(os.getenv("TRANSITION_DURATION", "0.5")))


@dataclass
class AppConfig:
    """アプリケーション全体設定"""
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    fal: FalConfig = field(default_factory=FalConfig)
    kling: KlingConfig = field(default_factory=KlingConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    news: NewsConfig = field(default_factory=NewsConfig)

    retry_count: int = field(default_factory=lambda: int(os.getenv("RETRY_COUNT", "3")))
    retry_delay: int = field(default_factory=lambda: int(os.getenv("RETRY_DELAY", "5")))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    def validate(self) -> dict:
        """設定の検証"""
        errors, warnings = [], []

        if not self.gemini.api_key:
            warnings.append("GEMINI_API_KEY が未設定（テキスト生成に必要）")
        if not self.fal.api_key:
            errors.append("FAL_KEY が未設定（画像生成不可）")
        if not self.kling.cookie:
            warnings.append("KLING_COOKIE が未設定（動画生成不可）")

        return {"errors": errors, "warnings": warnings}

    def print_status(self):
        """設定状態を表示"""
        print("\n" + "=" * 50)
        print("AI Video Automation - 設定状態")
        print("=" * 50)
        print(f"\n[Gemini API]")
        print(f"  API Key: {'✓ 設定済み' if self.gemini.api_key else '✗ 未設定'}")
        print(f"  Text Model: {self.gemini.model_text}")
        print(f"\n[fal.ai (Flux Pro)]")
        print(f"  API Key: {'✓ 設定済み' if self.fal.api_key else '✗ 未設定'}")
        print(f"  Model: {self.fal.model}")
        print(f"  Image Size: {self.fal.image_size}")
        print(f"\n[KLING AI]")
        print(f"  Cookie: {'✓ 設定済み' if self.kling.cookie else '✗ 未設定'}")
        print(f"  Mode: {self.kling.mode}")
        print(f"  Duration: {self.kling.duration}s")
        print(f"\n[YouTube API]")
        print(f"  Client Secrets: {self.youtube.client_secrets_file}")
        print(f"\n[News]")
        print(f"  Source: {self.news.source}")
        print(f"  Category: {self.news.category}")
        print(f"  Channel: {self.news.channel_name}")
        print(f"\n[Output]")
        print(f"  Resolution: {self.video.resolution}")
        print(f"  FPS: {self.video.fps}")

        result = self.validate()
        if result["errors"]:
            print(f"\n[Errors]")
            for e in result["errors"]:
                print(f"  ✗ {e}")
        if result["warnings"]:
            print(f"\n[Warnings]")
            for w in result["warnings"]:
                print(f"  ! {w}")
        print("=" * 50 + "\n")


# グローバル設定インスタンス
config = AppConfig()


if __name__ == "__main__":
    config.print_status()
