"""動画アニメーションモジュール - Ken Burns効果とFFmpeg"""

import subprocess
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Literal, Optional

from ..config import config, VIDEOS_DIR
from ..logger import setup_logger

logger = setup_logger("video_animator")


@dataclass
class AnimationResult:
    """アニメーション結果"""
    success: bool
    output_path: Optional[str] = None
    duration: float = 0.0
    error_message: Optional[str] = None


EffectType = Literal["zoom_in", "zoom_out", "ken_burns", "pan_left", "pan_right", "pan_up", "pan_down", "dynamic"]


class VideoAnimator:
    """静止画像にアニメーション効果を適用"""

    def __init__(self):
        self._check_ffmpeg()
        self.output_dir = VIDEOS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # デフォルト設定
        self.default_fps = config.video.fps
        self.default_resolution = config.video.resolution

        logger.info("VideoAnimator initialized")

    def _check_ffmpeg(self):
        """FFmpeg確認"""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("FFmpeg not found. Install with: brew install ffmpeg")

    def animate(
        self,
        image_path: str,
        duration: int = 5,
        effect: EffectType = "ken_burns",
        output_path: str = None,
        fps: int = None,
        resolution: str = None,
    ) -> AnimationResult:
        """画像をアニメーション化

        Args:
            image_path: 入力画像パス
            duration: 長さ（秒）
            effect: エフェクトタイプ
            output_path: 出力パス
            fps: フレームレート
            resolution: 解像度

        Returns:
            AnimationResult
        """
        if not Path(image_path).exists():
            return AnimationResult(
                success=False,
                error_message=f"Image not found: {image_path}",
            )

        if output_path is None:
            stem = Path(image_path).stem
            output_path = str(self.output_dir / f"{stem}_animated.mp4")

        fps = fps or self.default_fps
        resolution = resolution or self.default_resolution
        width, height = map(int, resolution.split("x"))

        logger.info(f"Animating: {image_path} ({effect}, {duration}s)")

        try:
            # エフェクト別の処理
            effect_methods = {
                "zoom_in": self._zoom_in,
                "zoom_out": self._zoom_out,
                "ken_burns": self._ken_burns,
                "pan_left": self._pan_left,
                "pan_right": self._pan_right,
                "pan_up": self._pan_up,
                "pan_down": self._pan_down,
                "dynamic": self._dynamic_effect,
            }

            method = effect_methods.get(effect, self._ken_burns)
            result = method(image_path, duration, output_path, fps, width, height)

            return result

        except Exception as e:
            logger.error(f"Animation failed: {e}")
            return AnimationResult(
                success=False,
                error_message=str(e),
            )

    def _run_ffmpeg(self, cmd: list) -> bool:
        """FFmpegコマンド実行"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr}")
            return False

    def _zoom_in(
        self,
        image: str,
        duration: int,
        output: str,
        fps: int,
        width: int,
        height: int,
    ) -> AnimationResult:
        """ズームイン効果"""
        total_frames = duration * fps
        # 1.0 -> 1.3 にズーム
        zoom_filter = (
            f"zoompan=z='min(zoom+0.0010,1.3)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={width}x{height}:fps={fps}"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image,
            "-vf", zoom_filter,
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output,
        ]

        if self._run_ffmpeg(cmd):
            return AnimationResult(
                success=True,
                output_path=output,
                duration=duration,
            )

        return AnimationResult(success=False, error_message="FFmpeg failed")

    def _zoom_out(
        self,
        image: str,
        duration: int,
        output: str,
        fps: int,
        width: int,
        height: int,
    ) -> AnimationResult:
        """ズームアウト効果"""
        total_frames = duration * fps
        # 1.3 -> 1.0 にズーム
        zoom_filter = (
            f"zoompan=z='if(lte(zoom,1.0),1.3,max(1.001,zoom-0.0010))':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={width}x{height}:fps={fps}"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image,
            "-vf", zoom_filter,
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output,
        ]

        if self._run_ffmpeg(cmd):
            return AnimationResult(
                success=True,
                output_path=output,
                duration=duration,
            )

        return AnimationResult(success=False, error_message="FFmpeg failed")

    def _ken_burns(
        self,
        image: str,
        duration: int,
        output: str,
        fps: int,
        width: int,
        height: int,
    ) -> AnimationResult:
        """Ken Burns効果（ズーム + パン + 色彩強化）"""
        total_frames = duration * fps
        # ゆっくりズームしながら右にパン + 色彩強化
        video_filter = (
            f"zoompan=z='min(zoom+0.0015,1.3)':"
            f"x='if(gte(zoom,1.3),x,x+1)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={width}x{height}:fps={fps},"
            # 色彩強化: コントラスト1.1、彩度1.2
            "eq=contrast=1.1:saturation=1.2,"
            # シャープネス
            "unsharp=3:3:1.0:3:3:0.5"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image,
            "-vf", video_filter,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            output,
        ]

        if self._run_ffmpeg(cmd):
            return AnimationResult(
                success=True,
                output_path=output,
                duration=duration,
            )

        return AnimationResult(success=False, error_message="FFmpeg failed")

    def _dynamic_effect(
        self,
        image: str,
        duration: int,
        output: str,
        fps: int,
        width: int,
        height: int,
    ) -> AnimationResult:
        """ダイナミック効果（強めのズーム + 色彩バイブレーション）"""
        total_frames = duration * fps
        # 強めのズーム + 色彩強調
        video_filter = (
            f"zoompan=z='min(zoom+0.002,1.5)':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={width}x{height}:fps={fps},"
            # 強めの色彩強化
            "eq=contrast=1.2:saturation=1.3:brightness=0.02,"
            # シャープネス強化
            "unsharp=5:5:1.5:5:5:0.5"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image,
            "-vf", video_filter,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            output,
        ]

        if self._run_ffmpeg(cmd):
            return AnimationResult(
                success=True,
                output_path=output,
                duration=duration,
            )

        return AnimationResult(success=False, error_message="FFmpeg failed")

    def _pan_left(
        self,
        image: str,
        duration: int,
        output: str,
        fps: int,
        width: int,
        height: int,
    ) -> AnimationResult:
        """左パン"""
        total_frames = duration * fps
        pan_filter = (
            f"zoompan=z='1.1':"
            f"x='if(gte(on,1),x-1,iw/2-iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={width}x{height}:fps={fps}"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image,
            "-vf", pan_filter,
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output,
        ]

        if self._run_ffmpeg(cmd):
            return AnimationResult(
                success=True,
                output_path=output,
                duration=duration,
            )

        return AnimationResult(success=False, error_message="FFmpeg failed")

    def _pan_right(
        self,
        image: str,
        duration: int,
        output: str,
        fps: int,
        width: int,
        height: int,
    ) -> AnimationResult:
        """右パン"""
        total_frames = duration * fps
        pan_filter = (
            f"zoompan=z='1.1':"
            f"x='if(gte(on,1),x+1,0)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={width}x{height}:fps={fps}"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image,
            "-vf", pan_filter,
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output,
        ]

        if self._run_ffmpeg(cmd):
            return AnimationResult(
                success=True,
                output_path=output,
                duration=duration,
            )

        return AnimationResult(success=False, error_message="FFmpeg failed")

    def _pan_up(
        self,
        image: str,
        duration: int,
        output: str,
        fps: int,
        width: int,
        height: int,
    ) -> AnimationResult:
        """上パン"""
        total_frames = duration * fps
        pan_filter = (
            f"zoompan=z='1.1':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='if(gte(on,1),y-1,ih/2-ih/zoom/2)':"
            f"d={total_frames}:s={width}x{height}:fps={fps}"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image,
            "-vf", pan_filter,
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output,
        ]

        if self._run_ffmpeg(cmd):
            return AnimationResult(
                success=True,
                output_path=output,
                duration=duration,
            )

        return AnimationResult(success=False, error_message="FFmpeg failed")

    def _pan_down(
        self,
        image: str,
        duration: int,
        output: str,
        fps: int,
        width: int,
        height: int,
    ) -> AnimationResult:
        """下パン"""
        total_frames = duration * fps
        pan_filter = (
            f"zoompan=z='1.1':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='if(gte(on,1),y+1,0)':"
            f"d={total_frames}:s={width}x{height}:fps={fps}"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image,
            "-vf", pan_filter,
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output,
        ]

        if self._run_ffmpeg(cmd):
            return AnimationResult(
                success=True,
                output_path=output,
                duration=duration,
            )

        return AnimationResult(success=False, error_message="FFmpeg failed")

    def animate_sequence(
        self,
        images: list[str],
        durations: list[int],
        effects: list[EffectType] = None,
        output_prefix: str = "animated",
    ) -> list[AnimationResult]:
        """複数画像を順番にアニメーション化

        Args:
            images: 画像パスリスト
            durations: 各画像の長さリスト
            effects: エフェクトリスト（Noneの場合はランダム）
            output_prefix: 出力ファイル名のプレフィックス

        Returns:
            AnimationResultのリスト
        """
        if effects is None:
            # デフォルトエフェクトをローテーション
            default_effects: list[EffectType] = ["ken_burns", "zoom_in", "pan_right", "zoom_out"]
            effects = [default_effects[i % len(default_effects)] for i in range(len(images))]

        results = []

        for i, (image, duration, effect) in enumerate(zip(images, durations, effects)):
            output_path = str(self.output_dir / f"{output_prefix}_{i:03d}.mp4")
            result = self.animate(image, duration, effect, output_path)
            results.append(result)

        success_count = sum(1 for r in results if r.success)
        logger.info(f"Animated {success_count}/{len(images)} images")

        return results


if __name__ == "__main__":
    # テスト実行
    animator = VideoAnimator()
    print("VideoAnimator initialized")

    # テスト画像があれば実行
    test_image = "test.png"
    if Path(test_image).exists():
        result = animator.animate(test_image, duration=5, effect="ken_burns")
        print(f"Result: {result}")
