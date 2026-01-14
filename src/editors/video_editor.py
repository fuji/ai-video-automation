"""動画編集モジュール - FFmpeg + MoviePy 2.x"""

import os
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from moviepy import (
    VideoFileClip,
    ImageClip,
    concatenate_videoclips,
    CompositeVideoClip,
    AudioFileClip,
    TextClip,
)
from moviepy.video.fx import FadeIn, FadeOut, Loop

from ..config import config, FINAL_DIR
from ..logger import setup_logger

logger = setup_logger("video_editor")


@dataclass
class EditResult:
    """編集結果"""
    success: bool
    output_path: Optional[str] = None
    duration: float = 0.0
    error_message: Optional[str] = None


class VideoEditor:
    """FFmpeg + MoviePyを使用した動画編集"""

    def __init__(self):
        self._check_ffmpeg()
        self.fps = config.video.fps
        self.resolution = tuple(map(int, config.video.resolution.split("x")))
        self.transition_duration = config.video.transition_duration
        logger.info(f"VideoEditor initialized ({config.video.resolution} @ {self.fps}fps)")

    def _check_ffmpeg(self):
        """FFmpegの存在確認"""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            logger.debug("FFmpeg available")
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("FFmpeg not found. Install with: brew install ffmpeg")

    def get_video_info(self, video_path: str) -> dict:
        """動画情報を取得"""
        try:
            clip = VideoFileClip(video_path)
            info = {
                "duration": clip.duration,
                "fps": clip.fps,
                "size": clip.size,
                "has_audio": clip.audio is not None,
            }
            clip.close()
            return info
        except Exception as e:
            logger.error(f"Failed to get video info: {e}")
            return {}

    def concatenate(
        self,
        video_paths: list[str],
        output_name: str,
        transitions: list[str] = None,
    ) -> EditResult:
        """複数の動画を結合"""
        logger.info(f"Concatenating {len(video_paths)} videos")

        valid_paths = [p for p in video_paths if Path(p).exists()]
        if not valid_paths:
            return EditResult(success=False, error_message="No valid video files")

        if len(valid_paths) == 1:
            # 1つだけの場合はコピー
            output_path = FINAL_DIR / f"{output_name}.mp4"
            import shutil
            shutil.copy(valid_paths[0], output_path)
            return EditResult(
                success=True,
                output_path=str(output_path),
                duration=self.get_video_info(str(output_path)).get("duration", 0),
            )

        try:
            clips = []
            for i, path in enumerate(valid_paths):
                clip = VideoFileClip(path)

                # トランジション適用
                if transitions and i > 0 and i - 1 < len(transitions):
                    transition = transitions[i - 1]
                    clip = self._apply_transition_in(clip, transition)

                if transitions and i < len(transitions):
                    clip = self._apply_transition_out(clip, transitions[i])

                clips.append(clip)

            # 結合
            final_clip = concatenate_videoclips(clips, method="compose")

            # 出力
            output_path = FINAL_DIR / f"{output_name}.mp4"
            final_clip.write_videofile(
                str(output_path),
                fps=self.fps,
                codec=config.video.codec,
                audio_codec=config.video.audio_codec,
                bitrate=config.video.bitrate,
                logger=None,
            )

            duration = final_clip.duration

            # クリーンアップ
            for clip in clips:
                clip.close()
            final_clip.close()

            logger.info(f"Concatenated video saved: {output_path}")
            return EditResult(
                success=True,
                output_path=str(output_path),
                duration=duration,
            )

        except Exception as e:
            logger.error(f"Concatenation failed: {e}")
            return EditResult(success=False, error_message=str(e))

    def _apply_transition_in(self, clip: VideoFileClip, transition: str) -> VideoFileClip:
        """トランジションイン効果を適用"""
        duration = self.transition_duration

        if transition == "fade":
            return clip.with_effects([FadeIn(duration)])
        elif transition == "dissolve":
            return clip.with_effects([FadeIn(duration)])

        return clip

    def _apply_transition_out(self, clip: VideoFileClip, transition: str) -> VideoFileClip:
        """トランジションアウト効果を適用"""
        duration = self.transition_duration

        if transition == "fade":
            return clip.with_effects([FadeOut(duration)])
        elif transition == "dissolve":
            return clip.with_effects([FadeOut(duration)])

        return clip

    def add_audio(
        self,
        video_path: str,
        audio_path: str,
        output_name: str,
        volume: float = 1.0,
    ) -> EditResult:
        """動画に音声を追加"""
        logger.info(f"Adding audio to video")

        if not Path(video_path).exists():
            return EditResult(success=False, error_message=f"Video not found: {video_path}")
        if not Path(audio_path).exists():
            return EditResult(success=False, error_message=f"Audio not found: {audio_path}")

        try:
            video = VideoFileClip(video_path)
            audio = AudioFileClip(audio_path)

            # 音声の長さを動画に合わせる
            if audio.duration > video.duration:
                audio = audio.subclipped(0, video.duration)
            elif audio.duration < video.duration:
                # 音声をループ
                audio = audio.with_effects([Loop(duration=video.duration)])

            # ボリューム調整
            audio = audio.with_volume_scaled(volume)

            # 音声を設定
            final_video = video.set_audio(audio)

            output_path = FINAL_DIR / f"{output_name}.mp4"
            final_video.write_videofile(
                str(output_path),
                fps=self.fps,
                codec=config.video.codec,
                audio_codec=config.video.audio_codec,
                logger=None,
            )

            duration = final_video.duration

            video.close()
            audio.close()
            final_video.close()

            logger.info(f"Audio added: {output_path}")
            return EditResult(
                success=True,
                output_path=str(output_path),
                duration=duration,
            )

        except Exception as e:
            logger.error(f"Add audio failed: {e}")
            return EditResult(success=False, error_message=str(e))

    def add_text_overlay(
        self,
        video_path: str,
        output_name: str,
        text: str,
        position: str = "bottom",
        fontsize: int = 48,
        color: str = "white",
        start: float = 0,
        duration: float = None,
    ) -> EditResult:
        """テキストオーバーレイを追加"""
        logger.info(f"Adding text overlay: {text[:30]}...")

        if not Path(video_path).exists():
            return EditResult(success=False, error_message=f"Video not found: {video_path}")

        try:
            video = VideoFileClip(video_path)

            # テキストクリップ作成
            txt_duration = duration or video.duration - start
            txt_clip = TextClip(
                text=text,
                font_size=fontsize,
                color=color,
                font="Arial",
            ).with_position(position).with_start(start).with_duration(txt_duration)

            # 合成
            final = CompositeVideoClip([video, txt_clip])

            output_path = FINAL_DIR / f"{output_name}.mp4"
            final.write_videofile(
                str(output_path),
                fps=self.fps,
                codec=config.video.codec,
                logger=None,
            )

            result_duration = final.duration

            video.close()
            final.close()

            return EditResult(
                success=True,
                output_path=str(output_path),
                duration=result_duration,
            )

        except Exception as e:
            logger.error(f"Text overlay failed: {e}")
            return EditResult(success=False, error_message=str(e))

    def create_from_image(
        self,
        image_path: str,
        output_name: str,
        duration: float = 5.0,
        zoom: bool = True,
    ) -> EditResult:
        """画像から動画を作成（Ken Burns効果）"""
        logger.info(f"Creating video from image: {image_path}")

        if not Path(image_path).exists():
            return EditResult(success=False, error_message=f"Image not found: {image_path}")

        try:
            # 画像クリップ作成
            img_clip = ImageClip(image_path).with_duration(duration)

            # ズーム効果
            if zoom:
                def zoom_effect(t):
                    return 1 + 0.1 * (t / duration)  # 10%ズーム

                img_clip = img_clip.resized(zoom_effect)

            # リサイズ
            img_clip = img_clip.resized(self.resolution)

            output_path = FINAL_DIR / f"{output_name}.mp4"
            img_clip.write_videofile(
                str(output_path),
                fps=self.fps,
                codec=config.video.codec,
                logger=None,
            )

            img_clip.close()

            return EditResult(
                success=True,
                output_path=str(output_path),
                duration=duration,
            )

        except Exception as e:
            logger.error(f"Create from image failed: {e}")
            return EditResult(success=False, error_message=str(e))

    def resize(
        self,
        video_path: str,
        output_name: str,
        resolution: str = None,
    ) -> EditResult:
        """動画をリサイズ"""
        target_res = resolution or config.video.resolution
        width, height = map(int, target_res.split("x"))

        logger.info(f"Resizing video to {target_res}")

        if not Path(video_path).exists():
            return EditResult(success=False, error_message=f"Video not found: {video_path}")

        try:
            video = VideoFileClip(video_path)
            resized = video.resized((width, height))

            output_path = FINAL_DIR / f"{output_name}.mp4"
            resized.write_videofile(
                str(output_path),
                fps=self.fps,
                codec=config.video.codec,
                logger=None,
            )

            duration = resized.duration
            video.close()
            resized.close()

            return EditResult(
                success=True,
                output_path=str(output_path),
                duration=duration,
            )

        except Exception as e:
            logger.error(f"Resize failed: {e}")
            return EditResult(success=False, error_message=str(e))

    def add_fade(
        self,
        video_path: str,
        output_name: str,
        fade_in: float = 1.0,
        fade_out: float = 1.0,
    ) -> EditResult:
        """フェードイン/アウト効果を追加"""
        logger.info(f"Adding fade effects")

        if not Path(video_path).exists():
            return EditResult(success=False, error_message=f"Video not found: {video_path}")

        try:
            video = VideoFileClip(video_path)
            video = video.with_effects([FadeIn(fade_in), FadeOut(fade_out)])

            output_path = FINAL_DIR / f"{output_name}.mp4"
            video.write_videofile(
                str(output_path),
                fps=self.fps,
                codec=config.video.codec,
                logger=None,
            )

            duration = video.duration
            video.close()

            return EditResult(
                success=True,
                output_path=str(output_path),
                duration=duration,
            )

        except Exception as e:
            logger.error(f"Fade effect failed: {e}")
            return EditResult(success=False, error_message=str(e))


if __name__ == "__main__":
    editor = VideoEditor()
    print("VideoEditor initialized successfully")
