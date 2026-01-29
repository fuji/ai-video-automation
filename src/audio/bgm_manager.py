"""BGM管理モジュール - トーンに合わせたBGM選択と音声ミックス"""

import os
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from enum import Enum

from ..logger import setup_logger

logger = setup_logger("bgm_manager")

# BGMアセットディレクトリ
ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
BGM_DIR = ASSETS_DIR / "bgm"
SFX_DIR = ASSETS_DIR / "sfx"


class MoodType(Enum):
    """ニュースのムード/トーン"""
    UPBEAT = "upbeat"          # 明るい・楽しいニュース
    EMOTIONAL = "emotional"    # 感動系・ほっこり
    QUIRKY = "quirky"          # おもしろ・奇妙なニュース
    DRAMATIC = "dramatic"      # 衝撃・驚きのニュース
    NEUTRAL = "neutral"        # 一般的なニュース


@dataclass
class BGMTrack:
    """BGMトラック情報"""
    name: str
    path: str
    mood: MoodType
    duration: float = 0.0
    
    def exists(self) -> bool:
        return Path(self.path).exists()


class BGMManager:
    """BGM管理クラス"""
    
    # BGMライブラリ定義
    BGM_LIBRARY = {
        MoodType.UPBEAT: "upbeat.mp3",
        MoodType.EMOTIONAL: "emotional.mp3",
        MoodType.QUIRKY: "quirky.mp3",
        MoodType.DRAMATIC: "dramatic.mp3",
        MoodType.NEUTRAL: "neutral.mp3",
    }
    
    # ムード検出用キーワード
    MOOD_KEYWORDS = {
        MoodType.UPBEAT: ["happy", "celebration", "win", "success", "joy", "楽しい", "嬉しい", "成功", "優勝"],
        MoodType.EMOTIONAL: ["reunite", "rescue", "save", "love", "family", "感動", "再会", "救出", "愛", "家族", "帰還"],
        MoodType.QUIRKY: ["weird", "strange", "bizarre", "funny", "odd", "おもしろ", "奇妙", "変", "珍しい", "ユニーク"],
        MoodType.DRAMATIC: ["shock", "amazing", "incredible", "record", "first", "驚き", "衝撃", "史上初", "記録"],
    }
    
    def __init__(self):
        BGM_DIR.mkdir(parents=True, exist_ok=True)
        SFX_DIR.mkdir(parents=True, exist_ok=True)
        
        self.available_bgm = self._scan_bgm_library()
        logger.info(f"BGMManager initialized ({len(self.available_bgm)} tracks available)")
    
    def _scan_bgm_library(self) -> dict[MoodType, BGMTrack]:
        """利用可能なBGMをスキャン"""
        available = {}
        
        for mood, filename in self.BGM_LIBRARY.items():
            path = BGM_DIR / filename
            if path.exists():
                duration = self._get_audio_duration(str(path))
                available[mood] = BGMTrack(
                    name=filename,
                    path=str(path),
                    mood=mood,
                    duration=duration,
                )
                logger.info(f"  Found BGM: {filename} ({mood.value}, {duration:.1f}s)")
        
        return available
    
    def _get_audio_duration(self, path: str) -> float:
        """音声ファイルの長さを取得"""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True
            )
            return float(result.stdout.strip())
        except:
            return 0.0
    
    def detect_mood(self, headline: str, article: str) -> MoodType:
        """記事からムードを検出"""
        text = (headline + " " + article).lower()
        
        scores = {mood: 0 for mood in MoodType}
        
        for mood, keywords in self.MOOD_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    scores[mood] += 1
        
        # 最高スコアのムードを返す（同点ならQUIRKY優先）
        max_score = max(scores.values())
        if max_score == 0:
            return MoodType.NEUTRAL
        
        for mood in [MoodType.QUIRKY, MoodType.EMOTIONAL, MoodType.UPBEAT, MoodType.DRAMATIC]:
            if scores[mood] == max_score:
                logger.info(f"Detected mood: {mood.value} (score: {max_score})")
                return mood
        
        return MoodType.NEUTRAL
    
    def get_bgm(self, mood: MoodType) -> Optional[BGMTrack]:
        """ムードに合ったBGMを取得"""
        # 指定ムードがあればそれを返す
        if mood in self.available_bgm:
            return self.available_bgm[mood]
        
        # なければNEUTRALを試す
        if MoodType.NEUTRAL in self.available_bgm:
            return self.available_bgm[MoodType.NEUTRAL]
        
        # どれもなければ最初に見つかったものを返す
        if self.available_bgm:
            return list(self.available_bgm.values())[0]
        
        return None
    
    def mix_audio(
        self,
        narration_path: str,
        bgm_path: str,
        output_path: str,
        narration_volume: float = 1.0,
        bgm_volume: float = 0.15,
        fade_in: float = 1.0,
        fade_out: float = 2.0,
    ) -> bool:
        """ナレーションとBGMをミックス
        
        Args:
            narration_path: ナレーション音声パス
            bgm_path: BGMパス
            output_path: 出力パス
            narration_volume: ナレーション音量 (0.0-1.0)
            bgm_volume: BGM音量 (0.0-1.0) デフォルト15%
            fade_in: フェードイン秒数
            fade_out: フェードアウト秒数
        
        Returns:
            成功したかどうか
        """
        try:
            # ナレーションの長さを取得
            narration_duration = self._get_audio_duration(narration_path)
            
            # BGMをループしてナレーション長に合わせる + フェード処理
            filter_complex = (
                f"[1:a]aloop=loop=-1:size=2e+09,atrim=0:{narration_duration + fade_out},"
                f"afade=t=in:st=0:d={fade_in},"
                f"afade=t=out:st={narration_duration - fade_out}:d={fade_out},"
                f"volume={bgm_volume}[bgm];"
                f"[0:a]volume={narration_volume}[narr];"
                f"[narr][bgm]amix=inputs=2:duration=first:dropout_transition=2[out]"
            )
            
            cmd = [
                "ffmpeg", "-y",
                "-i", narration_path,
                "-i", bgm_path,
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-c:a", "aac", "-b:a", "192k",
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Audio mixed: {output_path}")
                return True
            else:
                logger.error(f"Mix failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Mix error: {e}")
            return False
    
    def get_status(self) -> dict:
        """BGMライブラリの状態を取得"""
        return {
            "bgm_dir": str(BGM_DIR),
            "available": {mood.value: track.name for mood, track in self.available_bgm.items()},
            "missing": [mood.value for mood in MoodType if mood not in self.available_bgm],
        }


if __name__ == "__main__":
    manager = BGMManager()
    
    print("=== BGM Manager Status ===")
    status = manager.get_status()
    print(f"BGM Dir: {status['bgm_dir']}")
    print(f"Available: {status['available']}")
    print(f"Missing: {status['missing']}")
    
    # ムード検出テスト
    print("\n=== Mood Detection Test ===")
    test_cases = [
        ("猫が250km歩いて帰還", "5ヶ月ぶりに再会した飼い主は涙を流した"),
        ("世界一大きいピザ", "ギネス記録を更新！直径5メートルの巨大ピザ"),
        ("おじいちゃんがTikTokでバズる", "89歳のダンス動画が1億再生突破"),
    ]
    
    for headline, article in test_cases:
        mood = manager.detect_mood(headline, article)
        print(f"  '{headline}' → {mood.value}")
