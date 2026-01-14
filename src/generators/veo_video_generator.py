"""Veo 3.1 動画生成モジュール - 画像から動画を生成"""

import os
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import types

from ..config import config, VIDEOS_DIR
from ..logger import setup_logger

logger = setup_logger("veo_video_generator")


@dataclass
class VeoVideoResult:
    """Veo動画生成結果"""
    success: bool
    output_path: Optional[str] = None
    duration: float = 0.0
    error_message: Optional[str] = None
    generation_time: float = 0.0


class VeoVideoGenerator:
    """Veo 3.1 で画像から動画を生成"""

    # カメラワークプリセット
    CAMERA_PRESETS = {
        "政治": "Slow dramatic zoom in, cinematic lighting, professional broadcast quality, serious atmosphere",
        "経済": "Dynamic camera movement, urban cityscape, stock market visualization, modern corporate style",
        "テクノロジー": "Futuristic camera pan, holographic elements, digital effects, cyber aesthetic",
        "国際": "Epic aerial view, world map visualization, global network, international scope",
        "科学": "Microscopic zoom, laboratory setting, scientific visualization, discovery moment",
        "スポーツ": "Dynamic action shot, stadium atmosphere, energetic movement, competitive spirit",
        "default": "Smooth camera movement, cinematic quality, dramatic atmosphere, professional look",
    }

    # シーンタイプ別の追加要素
    SCENE_MODIFIERS = {
        "intro": "establishing shot, wide angle, dramatic entrance",
        "detail": "close-up details, shallow depth of field, focused attention",
        "outro": "pull back slowly, fade to ambient, concluding atmosphere",
    }

    def __init__(self, model: str = "veo-3.1"):
        """Veo動画生成クライアント初期化

        Args:
            model: 使用するモデル ("veo-3.1" または "veo-3-fast")
        """
        if not config.gemini.api_key:
            raise ValueError("GEMINI_API_KEY is not set")

        self.client = genai.Client(api_key=config.gemini.api_key)
        self.model = model  # Veo 3.1 (Image-to-Video対応)
        self.output_dir = VIDEOS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # レート制限対策
        self.last_request_time = 0
        self.min_request_interval = 60  # 1分間隔（Veo 3.1は課金プランでも制限あり）

        logger.info(f"VeoVideoGenerator initialized with {self.model}")

    def _wait_for_rate_limit(self):
        """レート制限を回避するため待機"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            wait_time = self.min_request_interval - elapsed
            logger.info(f"Rate limit: waiting {wait_time:.1f}s")
            time.sleep(wait_time)
        self.last_request_time = time.time()

    def generate_from_image(
        self,
        image_path: str,
        output_path: str = None,
        prompt: str = "",
        duration: int = 5,
        aspect_ratio: str = "16:9",
        resolution: str = "1080p",
        include_audio: bool = True,
    ) -> VeoVideoResult:
        """画像から動画を生成（Veo 3.1 Image-to-Video API）

        Args:
            image_path: 入力画像のパス
            output_path: 出力動画のパス
            prompt: 動画生成のプロンプト（カメラワークなど）
            duration: 動画の長さ（秒）5-8秒推奨
            aspect_ratio: アスペクト比 ("16:9", "9:16", "1:1")
            resolution: 解像度 ("720p", "1080p")
            include_audio: 音響効果を自動追加するか

        Returns:
            VeoVideoResult
        """
        start_time = time.time()

        if not Path(image_path).exists():
            return VeoVideoResult(
                success=False,
                error_message=f"Image not found: {image_path}",
            )

        if output_path is None:
            stem = Path(image_path).stem
            output_path = str(self.output_dir / f"{stem}_veo.mp4")

        self._wait_for_rate_limit()

        try:
            logger.info(f"Generating video from image: {Path(image_path).name}")
            logger.info(f"Prompt: {prompt[:100]}...")
            logger.info(f"Duration: {duration}s, Resolution: {resolution}")

            # 画像ファイルを読み込み
            with open(image_path, "rb") as f:
                image_data = f.read()

            # MIMEタイプを判定
            image_suffix = Path(image_path).suffix.lower()
            mime_type = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }.get(image_suffix, "image/png")

            # Veo 3.1 Image-to-Video API（非同期操作）
            operation = self.client.models.generate_video(
                model=self.model,
                prompt=prompt,
                config=types.GenerateVideoConfig(
                    image=types.Image(
                        image_bytes=image_data,
                        mime_type=mime_type,
                    ),
                    aspect_ratio=aspect_ratio,
                    # Note: duration, resolution は Veo 3.1 API のパラメータに依存
                    # ドキュメントに応じて調整が必要
                ),
            )

            logger.info("Waiting for video generation to complete...")

            # 操作の完了を待機（ポーリング）
            while not operation.done:
                logger.debug("Still processing...")
                time.sleep(10)
                operation = self.client.operations.get(operation)

            # 結果を取得
            if operation.error:
                raise ValueError(f"Generation failed: {operation.error}")

            response = operation.response

            # 動画データを取得
            video_data = None
            if hasattr(response, 'generated_videos') and response.generated_videos:
                video = response.generated_videos[0]
                if hasattr(video, 'video'):
                    video_data = video.video
                elif hasattr(video, 'video_bytes'):
                    video_data = video.video_bytes

            if not video_data:
                logger.warning("No video in response, checking alternative format...")
                # 代替フォーマットを確認
                if hasattr(response, 'video'):
                    video_data = response.video
                elif hasattr(response, 'candidates') and response.candidates:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'inline_data') and part.inline_data:
                            if 'video' in getattr(part.inline_data, 'mime_type', ''):
                                video_data = part.inline_data.data
                                break

            if not video_data:
                logger.warning("No video generated - use fallback")
                return VeoVideoResult(
                    success=False,
                    error_message="No video generated - use fallback",
                    generation_time=time.time() - start_time,
                )

            # 動画を保存
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            if isinstance(video_data, bytes):
                with open(output_path, "wb") as f:
                    f.write(video_data)
            else:
                # base64の場合
                import base64
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(video_data))

            generation_time = time.time() - start_time
            logger.info(f"Video saved: {output_path} ({generation_time:.1f}s)")

            return VeoVideoResult(
                success=True,
                output_path=output_path,
                duration=duration,
                generation_time=generation_time,
            )

        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())

            return VeoVideoResult(
                success=False,
                error_message=str(e),
                generation_time=time.time() - start_time,
            )

    def generate_from_prompt(
        self,
        prompt: str,
        output_path: str = None,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        resolution: str = "1080p",
    ) -> VeoVideoResult:
        """プロンプトのみから動画を生成（Text-to-Video）

        Args:
            prompt: 動画生成のプロンプト
            output_path: 出力動画のパス
            duration: 動画の長さ（秒）
            aspect_ratio: アスペクト比
            resolution: 解像度

        Returns:
            VeoVideoResult
        """
        start_time = time.time()

        if output_path is None:
            timestamp = int(time.time())
            output_path = str(self.output_dir / f"veo_{timestamp}.mp4")

        self._wait_for_rate_limit()

        try:
            logger.info(f"Generating video from prompt: {prompt[:100]}...")

            # Veo 3.1 Text-to-Video API（非同期操作）
            operation = self.client.models.generate_video(
                model=self.model,
                prompt=prompt,
                config=types.GenerateVideoConfig(
                    aspect_ratio=aspect_ratio,
                ),
            )

            logger.info("Waiting for video generation to complete...")

            # 操作の完了を待機
            while not operation.done:
                logger.debug("Still processing...")
                time.sleep(10)
                operation = self.client.operations.get(operation)

            if operation.error:
                raise ValueError(f"Generation failed: {operation.error}")

            response = operation.response

            # 動画データを取得
            video_data = None
            if hasattr(response, 'generated_videos') and response.generated_videos:
                video = response.generated_videos[0]
                if hasattr(video, 'video'):
                    video_data = video.video
                elif hasattr(video, 'video_bytes'):
                    video_data = video.video_bytes

            if not video_data:
                if hasattr(response, 'video'):
                    video_data = response.video

            if not video_data:
                return VeoVideoResult(
                    success=False,
                    error_message="No video generated",
                    generation_time=time.time() - start_time,
                )

            # 動画を保存
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            if isinstance(video_data, bytes):
                with open(output_path, "wb") as f:
                    f.write(video_data)
            else:
                import base64
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(video_data))

            generation_time = time.time() - start_time
            logger.info(f"Video saved: {output_path} ({generation_time:.1f}s)")

            return VeoVideoResult(
                success=True,
                output_path=output_path,
                duration=duration,
                generation_time=generation_time,
            )

        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            return VeoVideoResult(
                success=False,
                error_message=str(e),
                generation_time=time.time() - start_time,
            )

    def create_dynamic_prompt(
        self,
        news_category: str,
        scene_type: str = "default",
        additional_context: str = "",
    ) -> str:
        """ニュースカテゴリに応じたダイナミックなプロンプトを生成

        Args:
            news_category: ニュースカテゴリ
            scene_type: シーンタイプ（intro, detail, outro）
            additional_context: 追加コンテキスト

        Returns:
            動画生成用プロンプト
        """
        # カテゴリに応じたベースプロンプト
        base_prompt = self.CAMERA_PRESETS.get(news_category, self.CAMERA_PRESETS["default"])

        # シーンタイプに応じた修飾
        scene_modifier = self.SCENE_MODIFIERS.get(scene_type, "")

        # プロンプト構築
        parts = [base_prompt]
        if scene_modifier:
            parts.append(scene_modifier)
        if additional_context:
            parts.append(additional_context)

        prompt = ", ".join(parts)
        logger.debug(f"Generated prompt: {prompt}")

        return prompt

    def detect_category(self, title: str) -> str:
        """ニュースタイトルからカテゴリを判定

        Args:
            title: ニュースタイトル

        Returns:
            カテゴリ名
        """
        category_keywords = {
            "政治": ["政治", "選挙", "国会", "首相", "政府", "法案", "与党", "野党"],
            "経済": ["経済", "株", "円", "企業", "市場", "金融", "投資", "景気"],
            "テクノロジー": ["AI", "テクノロジー", "IT", "デジタル", "ロボット", "技術", "開発"],
            "国際": ["国際", "世界", "海外", "外交", "米国", "中国", "EU"],
            "科学": ["科学", "研究", "発見", "宇宙", "医療", "実験"],
            "スポーツ": ["スポーツ", "五輪", "サッカー", "野球", "優勝", "試合"],
        }

        for category, keywords in category_keywords.items():
            if any(kw in title for kw in keywords):
                return category

        return "default"


if __name__ == "__main__":
    # テスト実行
    try:
        generator = VeoVideoGenerator()
        print("VeoVideoGenerator initialized successfully")

        # プロンプトテスト
        test_title = "AI技術が変える未来の働き方"
        category = generator.detect_category(test_title)
        print(f"Category: {category}")

        prompt = generator.create_dynamic_prompt(category, "intro")
        print(f"Prompt: {prompt}")

    except Exception as e:
        print(f"Error: {e}")
