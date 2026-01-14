"""字幕レンダリングモジュール - FFmpegで動画に字幕を追加"""

import subprocess
import re
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from ..config import config, FINAL_DIR
from ..logger import setup_logger

logger = setup_logger("subtitle_renderer")


@dataclass
class SubtitleSegment:
    """字幕セグメント"""
    text: str
    start_time: float  # 秒
    end_time: float  # 秒
    style: str = "default"

    def to_srt(self, index: int) -> str:
        """SRT形式に変換"""
        start = self._format_time(self.start_time)
        end = self._format_time(self.end_time)
        return f"{index}\n{start} --> {end}\n{self.text}\n"

    def _format_time(self, seconds: float) -> str:
        """秒をSRT時間形式に変換"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


@dataclass
class SubtitleResult:
    """字幕追加結果"""
    success: bool
    output_path: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class SubtitleStyle:
    """字幕スタイル設定"""
    font_name: str = "Hiragino Sans"  # macOS用日本語フォント
    font_size: int = 24
    font_color: str = "white"
    outline_color: str = "black"
    outline_width: int = 2
    shadow: bool = True
    position: str = "bottom"  # bottom, center, top
    margin_v: int = 30
    margin_h: int = 20


class SubtitleRenderer:
    """FFmpegで動画に字幕を追加"""

    # 日本語フォント（OS別）
    FONTS = {
        "darwin": "Hiragino Sans",  # macOS
        "linux": "Noto Sans CJK JP",
        "win32": "Yu Gothic",
    }

    def __init__(self):
        self._check_ffmpeg()
        self.output_dir = FINAL_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # OS別フォント設定
        import sys
        self.default_font = self.FONTS.get(sys.platform, "Arial")

        logger.info(f"SubtitleRenderer initialized (font: {self.default_font})")

    def _check_ffmpeg(self):
        """FFmpeg確認"""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("FFmpeg not found")

    def add_subtitles(
        self,
        video_path: str,
        subtitles: list[SubtitleSegment],
        output_path: str = None,
        style: SubtitleStyle = None,
    ) -> SubtitleResult:
        """動画に字幕を追加

        Args:
            video_path: 入力動画パス
            subtitles: 字幕セグメントリスト
            output_path: 出力パス
            style: 字幕スタイル

        Returns:
            SubtitleResult
        """
        if not Path(video_path).exists():
            return SubtitleResult(
                success=False,
                error_message=f"Video not found: {video_path}",
            )

        if not subtitles:
            return SubtitleResult(
                success=False,
                error_message="No subtitles provided",
            )

        if output_path is None:
            stem = Path(video_path).stem
            output_path = str(self.output_dir / f"{stem}_subtitled.mp4")

        style = style or SubtitleStyle(font_name=self.default_font)

        logger.info(f"Adding {len(subtitles)} subtitles to {video_path}")

        try:
            # SRTファイル作成
            srt_path = Path(video_path).with_suffix(".srt")
            self._create_srt(subtitles, str(srt_path))

            # FFmpegで字幕追加
            result = self._burn_subtitles(video_path, str(srt_path), output_path, style)

            # 一時SRTファイル削除
            srt_path.unlink(missing_ok=True)

            return result

        except Exception as e:
            logger.error(f"Subtitle rendering failed: {e}")
            return SubtitleResult(
                success=False,
                error_message=str(e),
            )

    def _create_srt(self, subtitles: list[SubtitleSegment], output_path: str):
        """SRTファイル作成"""
        with open(output_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(subtitles, 1):
                f.write(segment.to_srt(i) + "\n")

        logger.debug(f"Created SRT: {output_path}")

    def _burn_subtitles(
        self,
        video_path: str,
        srt_path: str,
        output_path: str,
        style: SubtitleStyle,
    ) -> SubtitleResult:
        """字幕を動画に焼き込む"""
        # 位置設定
        alignment = {"bottom": 2, "center": 10, "top": 6}.get(style.position, 2)

        # ASS形式のスタイル（FFmpeg subtitles filter用）
        force_style = (
            f"FontName={style.font_name},"
            f"FontSize={style.font_size},"
            f"PrimaryColour=&H00{self._color_to_bgr(style.font_color)},"
            f"OutlineColour=&H00{self._color_to_bgr(style.outline_color)},"
            f"Outline={style.outline_width},"
            f"Shadow={'1' if style.shadow else '0'},"
            f"Alignment={alignment},"
            f"MarginV={style.margin_v},"
            f"MarginL={style.margin_h},"
            f"MarginR={style.margin_h}"
        )

        # SRTパスをエスケープ（Windows対応）
        srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"subtitles={srt_escaped}:force_style='{force_style}'",
            "-c:v", "libx264",
            "-c:a", "copy",
            output_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )

            logger.info(f"Subtitles added: {output_path}")
            return SubtitleResult(
                success=True,
                output_path=output_path,
            )

        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr}")
            return SubtitleResult(
                success=False,
                error_message=e.stderr,
            )

    def _color_to_bgr(self, color: str) -> str:
        """色名をBGR16進数に変換（ASS形式用）"""
        colors = {
            "white": "FFFFFF",
            "black": "000000",
            "red": "0000FF",
            "green": "00FF00",
            "blue": "FF0000",
            "yellow": "00FFFF",
            "cyan": "FFFF00",
            "magenta": "FF00FF",
        }
        return colors.get(color.lower(), "FFFFFF")

    def create_subtitles_from_script(
        self,
        script: str,
        total_duration: float,
        chars_per_segment: int = 30,
    ) -> list[SubtitleSegment]:
        """スクリプトから字幕セグメントを自動生成

        Args:
            script: フルスクリプト
            total_duration: 動画の長さ（秒）
            chars_per_segment: セグメントあたりの最大文字数

        Returns:
            SubtitleSegmentのリスト
        """
        if not script:
            return []

        # 文に分割
        sentences = re.split(r'[。！？\n]+', script)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return []

        # 各文をセグメントに分割
        segments = []
        for sentence in sentences:
            if len(sentence) <= chars_per_segment:
                segments.append(sentence)
            else:
                # 長い文を分割
                for i in range(0, len(sentence), chars_per_segment):
                    segments.append(sentence[i:i + chars_per_segment])

        # 時間を均等に割り当て
        segment_duration = total_duration / len(segments)

        subtitles = []
        for i, text in enumerate(segments):
            start = i * segment_duration
            end = (i + 1) * segment_duration - 0.1  # 0.1秒の隙間
            subtitles.append(SubtitleSegment(
                text=text,
                start_time=start,
                end_time=end,
            ))

        logger.info(f"Created {len(subtitles)} subtitle segments")
        return subtitles

    def create_subtitles_from_audio_timing(
        self,
        script: str,
        audio_duration: float,
        speech_rate: float = 5.0,  # 文字/秒
    ) -> list[SubtitleSegment]:
        """音声タイミングに合わせた字幕生成

        Args:
            script: フルスクリプト
            audio_duration: 音声の長さ（秒）
            speech_rate: 読み上げ速度（文字/秒）

        Returns:
            SubtitleSegmentのリスト
        """
        # 文に分割
        sentences = re.split(r'[。！？]+', script)
        sentences = [s.strip() + "。" for s in sentences if s.strip()]

        subtitles = []
        current_time = 0.0

        for sentence in sentences:
            # 文字数から所要時間を計算
            char_count = len(sentence)
            duration = char_count / speech_rate

            # セグメント作成（30文字ずつ）
            for i in range(0, char_count, 30):
                chunk = sentence[i:i + 30]
                chunk_duration = len(chunk) / speech_rate

                subtitles.append(SubtitleSegment(
                    text=chunk,
                    start_time=current_time,
                    end_time=min(current_time + chunk_duration, audio_duration),
                ))
                current_time += chunk_duration

        # 時間調整（音声の長さに合わせる）
        if subtitles and current_time != audio_duration:
            ratio = audio_duration / current_time
            for subtitle in subtitles:
                subtitle.start_time *= ratio
                subtitle.end_time *= ratio

        logger.info(f"Created {len(subtitles)} timed subtitles")
        return subtitles


if __name__ == "__main__":
    # テスト
    renderer = SubtitleRenderer()
    print(f"SubtitleRenderer ready (font: {renderer.default_font})")

    # テスト字幕生成
    test_script = "こんにちは。今日のニュースをお伝えします。これはテストです。"
    subtitles = renderer.create_subtitles_from_script(test_script, 10.0)

    print(f"\n=== Generated {len(subtitles)} subtitles ===")
    for sub in subtitles:
        print(f"  {sub.start_time:.1f}s - {sub.end_time:.1f}s: {sub.text}")
