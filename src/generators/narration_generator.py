"""音声ナレーション生成モジュール - ElevenLabs API v1.0+ 統合（クォータトラッキング付き）"""

import os
import time
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings

from ..config import config, OUTPUT_DIR
from ..logger import setup_logger

logger = setup_logger("narration_generator")

# クォータ管理用ディレクトリ
DATA_DIR = Path(__file__).parent.parent.parent / "data"


@dataclass
class NarrationResult:
    """ナレーション生成結果"""
    success: bool
    file_path: Optional[str] = None
    duration_seconds: float = 0.0
    character_count: int = 0
    error_message: Optional[str] = None


class QuotaTracker:
    """ElevenLabs月間クォータトラッキング"""

    QUOTA_FILE = DATA_DIR / "elevenlabs_usage.json"
    MONTHLY_LIMIT = 10000  # フリープラン上限

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.usage = self._load_usage()

    def _load_usage(self) -> dict:
        """使用量読み込み"""
        if self.QUOTA_FILE.exists():
            try:
                with open(self.QUOTA_FILE, "r", encoding="utf-8") as f:
                    usage = json.load(f)

                # 月が変わったらリセット
                current_month = datetime.now().strftime("%Y-%m")
                if usage.get("month") != current_month:
                    logger.info(f"New month detected, resetting usage (was {usage.get('month')})")
                    usage = {
                        "month": current_month,
                        "current_month_usage": 0,
                        "history": [],
                    }
                    self._save_usage(usage)

                return usage
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load usage file: {e}")

        return {
            "month": datetime.now().strftime("%Y-%m"),
            "current_month_usage": 0,
            "history": [],
        }

    def _save_usage(self, usage: dict):
        """使用量保存"""
        with open(self.QUOTA_FILE, "w", encoding="utf-8") as f:
            json.dump(usage, f, indent=2, ensure_ascii=False)

    def can_generate(self, char_count: int) -> bool:
        """生成可能かチェック"""
        current = self.usage.get("current_month_usage", 0)
        return (current + char_count) <= self.MONTHLY_LIMIT

    def get_remaining_quota(self) -> int:
        """残りクォータ取得"""
        current = self.usage.get("current_month_usage", 0)
        return max(0, self.MONTHLY_LIMIT - current)

    def get_usage_percentage(self) -> float:
        """使用率を取得（パーセント）"""
        current = self.usage.get("current_month_usage", 0)
        return (current / self.MONTHLY_LIMIT) * 100

    def record_usage(self, char_count: int, title: str = ""):
        """使用量を記録"""
        self.usage["current_month_usage"] += char_count
        self.usage["history"].append({
            "timestamp": datetime.now().isoformat(),
            "characters": char_count,
            "title": title[:50] if title else "",
        })

        # 履歴は直近100件まで
        if len(self.usage["history"]) > 100:
            self.usage["history"] = self.usage["history"][-100:]

        self._save_usage(self.usage)

        remaining = self.get_remaining_quota()
        logger.info(f"Quota updated: +{char_count} chars, remaining: {remaining}/{self.MONTHLY_LIMIT}")

    def get_status(self) -> dict:
        """ステータス取得"""
        return {
            "month": self.usage.get("month"),
            "used": self.usage.get("current_month_usage", 0),
            "limit": self.MONTHLY_LIMIT,
            "remaining": self.get_remaining_quota(),
            "usage_percentage": self.get_usage_percentage(),
        }


class NarrationGenerator:
    """ElevenLabs APIで音声ナレーション生成（クォータトラッキング付き）"""

    # 日本語対応ボイス（multilingual_v2モデル）
    RECOMMENDED_VOICES = {
        "rachel": "Rachel",  # 女性、落ち着いた声
        "domi": "Domi",  # 女性、明るい声
        "bella": "Bella",  # 女性、やわらかい声
        "antoni": "Antoni",  # 男性、落ち着いた声
        "josh": "Josh",  # 男性、ニュースキャスター風
        "arnold": "Arnold",  # 男性、力強い声
        "adam": "Adam",  # 男性、ナレーター風
        "sam": "Sam",  # 男性、若い声
    }

    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")

        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY が設定されていません")

        # ElevenLabs クライアント (v1.0+ API)
        self.client = ElevenLabs(api_key=self.api_key)

        self.audio_dir = OUTPUT_DIR / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        # クォータトラッカー
        self.quota_tracker = QuotaTracker()

        remaining = self.quota_tracker.get_remaining_quota()
        logger.info(f"NarrationGenerator initialized (remaining quota: {remaining} chars)")

    def list_voices(self) -> list[dict]:
        """利用可能なボイス一覧を取得"""
        try:
            response = self.client.voices.get_all()
            voice_list = []

            for v in response.voices:
                voice_list.append({
                    "voice_id": v.voice_id,
                    "name": v.name,
                    "category": getattr(v, "category", "unknown"),
                })

            return voice_list

        except Exception as e:
            logger.error(f"Failed to list voices: {e}")
            return []

    def can_generate(self, char_count: int) -> bool:
        """生成可能かチェック（クォータ確認）"""
        return self.quota_tracker.can_generate(char_count)

    def get_remaining_quota(self) -> int:
        """残りクォータ取得"""
        return self.quota_tracker.get_remaining_quota()

    def get_quota_status(self) -> dict:
        """クォータステータス取得"""
        return self.quota_tracker.get_status()

    def generate(
        self,
        text: str,
        output_path: str = None,
        voice: str = "Rachel",
        speed: float = 1.1,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        use_speaker_boost: bool = True,
        check_quota: bool = True,
        title: str = "",
    ) -> NarrationResult:
        """音声ナレーションを生成

        Args:
            text: ナレーションテキスト
            output_path: 出力ファイルパス
            voice: ボイス名またはID
            speed: 再生速度 (0.7-1.5)
            stability: 安定性 (0.0-1.0)
            similarity_boost: 類似度ブースト (0.0-1.0)
            style: スタイル強度 (0.0-1.0)
            use_speaker_boost: スピーカーブースト使用
            check_quota: クォータチェックを行うか
            title: 使用履歴用のタイトル

        Returns:
            NarrationResult
        """
        if not text or not text.strip():
            return NarrationResult(
                success=False,
                error_message="Empty text provided",
            )

        char_count = len(text)

        # クォータチェック
        if check_quota:
            if not self.can_generate(char_count):
                status = self.quota_tracker.get_status()
                return NarrationResult(
                    success=False,
                    error_message=f"月間クォータ超過: {status['used']}/{status['limit']}文字 (残り: {status['remaining']}文字)",
                    character_count=char_count,
                )

        # 出力パス設定
        if output_path is None:
            timestamp = int(time.time())
            output_path = str(self.audio_dir / f"narration_{timestamp}.mp3")

        logger.info(f"Generating narration: {char_count} chars, voice={voice}")

        try:
            # ボイス設定 (v1.0+ API)
            voice_settings = VoiceSettings(
                stability=stability,
                similarity_boost=similarity_boost,
                style=style,
                use_speaker_boost=use_speaker_boost,
            )

            # 音声生成 (v1.0+ API - text_to_speech.convert を使用)
            audio_generator = self.client.text_to_speech.convert(
                text=text,
                voice_id=voice,  # voice_id パラメータを使用
                model_id="eleven_multilingual_v2",
                voice_settings=voice_settings,
            )

            # ジェネレータからバイト列を取得
            audio_bytes = b"".join(audio_generator)

            # ファイル保存
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "wb") as f:
                f.write(audio_bytes)

            # 音声の長さを推定（日本語: 約5文字/秒）
            estimated_duration = len(text) / 5 / speed

            # クォータ記録
            self.quota_tracker.record_usage(char_count, title)

            logger.info(f"Narration saved: {output_path} (~{estimated_duration:.1f}s)")

            return NarrationResult(
                success=True,
                file_path=output_path,
                duration_seconds=estimated_duration,
                character_count=char_count,
            )

        except Exception as e:
            logger.error(f"Narration generation failed: {e}")
            return NarrationResult(
                success=False,
                error_message=str(e),
                character_count=len(text),
            )

    def generate_from_script(
        self,
        script: list[str],
        output_dir: str = None,
        voice: str = "Rachel",
        speed: float = 1.1,
    ) -> list[NarrationResult]:
        """複数セグメントの音声を生成

        Args:
            script: テキストセグメントのリスト
            output_dir: 出力ディレクトリ
            voice: ボイス
            speed: 再生速度

        Returns:
            NarrationResultのリスト
        """
        if output_dir is None:
            output_dir = str(self.audio_dir)

        results = []

        for i, text in enumerate(script):
            output_path = str(Path(output_dir) / f"segment_{i:03d}.mp3")

            result = self.generate(
                text=text,
                output_path=output_path,
                voice=voice,
                speed=speed,
            )
            results.append(result)

            # レート制限対策
            time.sleep(0.5)

        success_count = sum(1 for r in results if r.success)
        logger.info(f"Generated {success_count}/{len(script)} segments")

        return results

    def estimate_duration(self, text: str, speed: float = 1.1) -> float:
        """音声の長さを推定（秒）

        Args:
            text: テキスト
            speed: 再生速度

        Returns:
            推定秒数
        """
        # 日本語: 約5文字/秒、速度で調整
        chars_per_second = 5 * speed
        return len(text) / chars_per_second

    def optimize_text_for_narration(self, text: str) -> str:
        """ナレーション用にテキストを最適化

        Args:
            text: 元のテキスト

        Returns:
            最適化されたテキスト
        """
        import re

        # 不要な記号を削除
        text = re.sub(r'[【】「」『』]', '', text)

        # 括弧内を読みやすく
        text = re.sub(r'\(([^)]+)\)', r'、\1、', text)

        # 数字を読みやすく
        text = re.sub(r'(\d+)年', r'\1年', text)
        text = re.sub(r'(\d+)月', r'\1月', text)
        text = re.sub(r'(\d+)日', r'\1日', text)

        # URLを削除
        text = re.sub(r'https?://\S+', '', text)

        # 連続する句読点を整理
        text = re.sub(r'[、。]+', '。', text)
        text = re.sub(r'。+', '。', text)

        # 改行を句点に
        text = re.sub(r'\n+', '。', text)

        # 前後の空白削除
        text = text.strip()

        return text


class NarrationConfig:
    """ナレーション設定プリセット"""

    @staticmethod
    def news_style() -> dict:
        """ニュース読み上げスタイル"""
        return {
            "voice": "Rachel",
            "speed": 1.15,
            "stability": 0.7,
            "similarity_boost": 0.8,
            "style": 0.0,
        }

    @staticmethod
    def casual_style() -> dict:
        """カジュアルスタイル"""
        return {
            "voice": "Domi",
            "speed": 1.1,
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.3,
        }

    @staticmethod
    def formal_style() -> dict:
        """フォーマルスタイル"""
        return {
            "voice": "Antoni",
            "speed": 1.0,
            "stability": 0.8,
            "similarity_boost": 0.9,
            "style": 0.0,
        }


if __name__ == "__main__":
    # テスト実行
    try:
        generator = NarrationGenerator()

        # クォータステータス表示
        print("=== Quota Status ===")
        status = generator.get_quota_status()
        print(f"  Month: {status['month']}")
        print(f"  Used: {status['used']:,}/{status['limit']:,} chars")
        print(f"  Remaining: {status['remaining']:,} chars")
        print(f"  Usage: {status['usage_percentage']:.1f}%")

        # ボイス一覧
        print("\n=== Available Voices ===")
        voice_list = generator.list_voices()
        for v in voice_list[:5]:
            print(f"  {v['name']} ({v['voice_id']})")

        # テスト生成
        print("\n=== Test Generation ===")
        test_text = "こんにちは。これはテスト音声です。ElevenLabsの日本語音声合成をテストしています。"

        # クォータチェック
        if not generator.can_generate(len(test_text)):
            print(f"Warning: Not enough quota for {len(test_text)} chars")
            print("Skipping generation")
        else:
            result = generator.generate(
                text=test_text,
                voice="Rachel",
                speed=1.1,
                title="テスト生成",
            )

            if result.success:
                print(f"Success: {result.file_path}")
                print(f"Duration: ~{result.duration_seconds:.1f}s")
                print(f"Characters used: {result.character_count}")

                # 更新後のクォータ
                print(f"\nRemaining quota: {generator.get_remaining_quota():,} chars")
            else:
                print(f"Failed: {result.error_message}")

    except ValueError as e:
        print(f"Error: {e}")
        print("Set ELEVENLABS_API_KEY in .env")
