"""Edge TTS ナレーション生成モジュール - 完全無料の音声合成"""

import asyncio
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import edge_tts

from ..config import OUTPUT_DIR
from ..logger import setup_logger

logger = setup_logger("edge_tts_generator")


@dataclass
class NarrationResult:
    """ナレーション生成結果"""
    success: bool
    file_path: Optional[str] = None
    duration_seconds: float = 0.0
    character_count: int = 0
    error_message: Optional[str] = None


class EdgeTTSGenerator:
    """Edge TTS (Microsoft) で音声ナレーション生成 - 完全無料"""

    # 日本語ボイス
    VOICE_MAP = {
        # 日本語
        "Nanami": "ja-JP-NanamiNeural",      # 女性、ニュースキャスター風
        "Keita": "ja-JP-KeitaNeural",        # 男性、落ち着いた声
        # 英語 (バックアップ)
        "Jenny": "en-US-JennyNeural",        # 女性、明るい
        "Guy": "en-US-GuyNeural",            # 男性、プロフェッショナル
        # 多言語
        "Aria": "en-US-AriaNeural",          # 女性、感情豊か
    }
    
    DEFAULT_VOICE = "Nanami"  # 日本語ニュースにはNanamiがベスト

    def __init__(self):
        self.audio_dir = OUTPUT_DIR / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        logger.info("EdgeTTSGenerator initialized (free, unlimited)")

    async def _generate_async(
        self,
        text: str,
        output_path: str,
        voice: str,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> NarrationResult:
        """非同期で音声生成"""
        try:
            # Voice名をVoice IDに変換
            voice_id = self.VOICE_MAP.get(voice, voice)
            
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice_id,
                rate=rate,
                pitch=pitch,
            )
            
            await communicate.save(output_path)
            
            # 音声の長さを推定（日本語: 約5文字/秒）
            estimated_duration = len(text) / 5
            
            logger.info(f"Edge TTS generated: {output_path} (~{estimated_duration:.1f}s)")
            
            return NarrationResult(
                success=True,
                file_path=output_path,
                duration_seconds=estimated_duration,
                character_count=len(text),
            )
            
        except Exception as e:
            logger.error(f"Edge TTS generation failed: {e}")
            return NarrationResult(
                success=False,
                error_message=str(e),
                character_count=len(text),
            )

    def generate(
        self,
        text: str,
        output_path: str = None,
        voice: str = None,
        speed: float = 1.0,
        pitch: float = 0.0,
        **kwargs,  # ElevenLabs互換のパラメータを無視
    ) -> NarrationResult:
        """音声ナレーションを生成（同期API）

        Args:
            text: ナレーションテキスト
            output_path: 出力ファイルパス
            voice: ボイス名 (Nanami, Keita など)
            speed: 再生速度 (0.5-2.0, 1.0が標準)
            pitch: ピッチ調整 (-50 to +50 Hz)

        Returns:
            NarrationResult
        """
        if not text or not text.strip():
            return NarrationResult(
                success=False,
                error_message="Empty text provided",
            )

        # 出力パス設定
        if output_path is None:
            timestamp = int(time.time())
            output_path = str(self.audio_dir / f"narration_{timestamp}.mp3")
        else:
            # 親ディレクトリを作成
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        voice = voice or self.DEFAULT_VOICE
        
        # speed を rate 文字列に変換 (1.0 -> "+0%", 1.2 -> "+20%")
        rate_percent = int((speed - 1.0) * 100)
        rate = f"+{rate_percent}%" if rate_percent >= 0 else f"{rate_percent}%"
        
        # pitch を Hz 文字列に変換
        pitch_hz = f"+{int(pitch)}Hz" if pitch >= 0 else f"{int(pitch)}Hz"
        
        logger.info(f"Generating Edge TTS: {len(text)} chars, voice={voice}, rate={rate}")

        # 非同期関数を同期的に実行
        return asyncio.run(self._generate_async(
            text=text,
            output_path=output_path,
            voice=voice,
            rate=rate,
            pitch=pitch_hz,
        ))

    def can_generate(self, char_count: int) -> bool:
        """生成可能かチェック（Edge TTSは無制限）"""
        return True

    def get_remaining_quota(self) -> int:
        """残りクォータ取得（Edge TTSは無制限）"""
        return 999999

    def get_quota_status(self) -> dict:
        """クォータステータス取得"""
        return {
            "month": "unlimited",
            "used": 0,
            "limit": 999999,
            "remaining": 999999,
            "usage_percentage": 0.0,
            "provider": "edge_tts",
        }

    def estimate_duration(self, text: str, speed: float = 1.0) -> float:
        """音声の長さを推定（秒）"""
        chars_per_second = 5 * speed
        return len(text) / chars_per_second


class EdgeTTSConfig:
    """Edge TTS 設定プリセット"""

    @staticmethod
    def news_style() -> dict:
        """ニュース読み上げスタイル"""
        return {
            "voice": "Nanami",
            "speed": 1.05,
            "pitch": 0,
        }

    @staticmethod
    def casual_style() -> dict:
        """カジュアルスタイル"""
        return {
            "voice": "Nanami",
            "speed": 1.1,
            "pitch": 5,
        }

    @staticmethod
    def formal_male() -> dict:
        """フォーマル男性スタイル"""
        return {
            "voice": "Keita",
            "speed": 0.95,
            "pitch": 0,
        }


if __name__ == "__main__":
    # テスト実行
    print("=== Edge TTS Test ===")
    
    generator = EdgeTTSGenerator()
    
    test_text = "こんにちは。これはEdge TTSのテスト音声です。完全無料で、クォータ制限もありません。"
    
    print(f"Text: {test_text}")
    print(f"Characters: {len(test_text)}")
    
    result = generator.generate(
        text=test_text,
        voice="Nanami",
        speed=1.0,
    )
    
    if result.success:
        print(f"✅ Success: {result.file_path}")
        print(f"   Duration: ~{result.duration_seconds:.1f}s")
    else:
        print(f"❌ Failed: {result.error_message}")
