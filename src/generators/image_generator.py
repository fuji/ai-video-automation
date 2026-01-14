"""画像生成モジュール - Gemini 2.5 Flash Image Generation"""

import base64
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import httpx

from google import genai
from google.genai import types
from PIL import Image
import io

from ..config import config, IMAGES_DIR
from ..logger import setup_logger

logger = setup_logger("image_generator")


@dataclass
class ImageResult:
    """画像生成結果"""
    success: bool
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    generation_time: float = 0.0


class ImageGenerator:
    """Gemini APIを使用した画像生成"""

    def __init__(self):
        if not config.gemini.api_key:
            raise ValueError("GEMINI_API_KEY is not set")

        # Google Genai クライアント (新API)
        self.client = genai.Client(api_key=config.gemini.api_key)
        self.model_name = config.gemini.model_image

        # レート制限対策（無料プラン: 2リクエスト/分）
        self.last_request_time = 0
        self.min_request_interval = 30  # 30秒間隔

        logger.info(f"ImageGenerator initialized with {self.model_name}")

    def _wait_for_rate_limit(self):
        """レート制限を回避するため待機"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            wait_time = self.min_request_interval - elapsed
            logger.info(f"Rate limit: waiting {wait_time:.1f}s")
            time.sleep(wait_time)
        self.last_request_time = time.time()

    def generate(
        self,
        prompt: str,
        output_name: str,
        reference_image: Optional[str] = None,
        retry_count: int = None,
    ) -> ImageResult:
        """画像を生成"""
        start_time = time.time()
        retries = retry_count or config.retry_count

        logger.info(f"Generating image: {output_name}")
        logger.debug(f"Prompt: {prompt[:100]}...")

        for attempt in range(retries):
            try:
                # レート制限対策
                self._wait_for_rate_limit()

                # リファレンス画像がある場合
                if reference_image and Path(reference_image).exists():
                    result = self._generate_with_reference(prompt, reference_image)
                else:
                    result = self._generate_image(prompt)

                if result:
                    # 画像を保存
                    output_path = IMAGES_DIR / f"{output_name}.png"
                    result.save(str(output_path))
                    logger.info(f"Image saved: {output_path}")

                    return ImageResult(
                        success=True,
                        file_path=str(output_path),
                        generation_time=time.time() - start_time,
                    )

            except Exception as e:
                error_str = str(e).lower()
                # レート制限エラーの場合は長めに待機
                if "429" in error_str or "resource_exhausted" in error_str or "quota" in error_str:
                    if attempt < retries - 1:
                        wait_time = 60 * (attempt + 1)  # 60秒, 120秒と増加
                        logger.warning(f"Rate limit hit, waiting {wait_time}s (attempt {attempt+1}/{retries})")
                        time.sleep(wait_time)
                        self.last_request_time = time.time()
                        continue

                logger.warning(f"Attempt {attempt + 1}/{retries} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(config.retry_delay)

        return ImageResult(
            success=False,
            error_message="All attempts failed",
            generation_time=time.time() - start_time,
        )

    def _generate_image(self, prompt: str) -> Optional[Image.Image]:
        """Geminiで画像生成"""
        try:
            # 画像生成用のプロンプト強化
            enhanced_prompt = f"Generate a high-quality image: {prompt}"

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=enhanced_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.9,
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )

            # デバッグ: レスポンス構造を確認
            logger.debug(f"Response type: {type(response)}")

            # レスポンスから画像を抽出
            if response.candidates:
                for part in response.candidates[0].content.parts:
                    logger.debug(f"Part type: {type(part)}, attrs: {dir(part)[:5]}...")

                    # inline_data がある場合（base64エンコード）
                    if hasattr(part, 'inline_data') and part.inline_data:
                        inline_data = part.inline_data
                        logger.debug(f"inline_data type: {type(inline_data)}")

                        # data属性がbytesの場合
                        if hasattr(inline_data, 'data'):
                            if isinstance(inline_data.data, bytes):
                                image_bytes = inline_data.data
                            else:
                                # base64文字列の場合
                                image_bytes = base64.b64decode(inline_data.data)

                            logger.debug(f"Image bytes length: {len(image_bytes)}")
                            return Image.open(io.BytesIO(image_bytes))

                    # image属性がある場合（PIL Image）
                    if hasattr(part, 'image') and part.image:
                        logger.debug("Found PIL Image in part.image")
                        return part.image

            logger.warning("No image in response")
            logger.debug(f"Full response: {response}")
            return None

        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            raise

    def _generate_with_reference(
        self,
        prompt: str,
        reference_path: str,
    ) -> Optional[Image.Image]:
        """リファレンス画像を使用して生成"""
        try:
            # リファレンス画像を読み込み
            ref_image = Image.open(reference_path)

            # 画像をバイト列に変換
            img_byte_arr = io.BytesIO()
            ref_image.save(img_byte_arr, format='PNG')
            img_bytes = img_byte_arr.getvalue()

            # マルチモーダルプロンプト
            enhanced_prompt = f"Based on the style and composition of this reference image, generate: {prompt}"

            # 画像パーツを作成
            image_part = types.Part.from_bytes(
                data=img_bytes,
                mime_type="image/png",
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[enhanced_prompt, image_part],
                config=types.GenerateContentConfig(
                    temperature=0.9,
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )

            if response.candidates:
                for part in response.candidates[0].content.parts:
                    # inline_data がある場合
                    if hasattr(part, 'inline_data') and part.inline_data:
                        inline_data = part.inline_data
                        if hasattr(inline_data, 'data'):
                            if isinstance(inline_data.data, bytes):
                                image_bytes = inline_data.data
                            else:
                                image_bytes = base64.b64decode(inline_data.data)
                            return Image.open(io.BytesIO(image_bytes))

                    # image属性がある場合
                    if hasattr(part, 'image') and part.image:
                        return part.image

            return None

        except Exception as e:
            logger.error(f"Reference generation failed: {e}")
            raise

    def generate_batch(
        self,
        prompts: list[tuple[str, str]],  # [(prompt, output_name), ...]
        reference_image: Optional[str] = None,
    ) -> list[ImageResult]:
        """複数画像をバッチ生成"""
        results = []

        for i, (prompt, name) in enumerate(prompts):
            logger.info(f"Batch progress: {i + 1}/{len(prompts)}")
            result = self.generate(prompt, name, reference_image)
            results.append(result)

            # レート制限対策
            if i < len(prompts) - 1:
                time.sleep(2)

        return results


class NanoBananaGenerator:
    """Nano Banana APIを使用した画像生成（代替）"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.base_url = "https://api.nano-ai.io/v1"  # 仮のURL
        logger.info("NanoBananaGenerator initialized")

    def generate(
        self,
        prompt: str,
        output_name: str,
        model: str = "flux-1.1-pro-ultra",
        aspect_ratio: str = "16:9",
    ) -> ImageResult:
        """Nano Banana APIで画像生成"""
        start_time = time.time()

        # 注: 実際のNano Banana APIエンドポイントに合わせて実装
        # 現在はプレースホルダー

        logger.warning("NanoBanana API not configured - using placeholder")

        return ImageResult(
            success=False,
            error_message="NanoBanana API not configured",
            generation_time=time.time() - start_time,
        )


def create_image_generator(use_nano_banana: bool = False) -> ImageGenerator:
    """画像生成器のファクトリー関数"""
    if use_nano_banana:
        return NanoBananaGenerator()
    return ImageGenerator()


if __name__ == "__main__":
    # テスト実行
    try:
        generator = ImageGenerator()
        result = generator.generate(
            prompt="A beautiful cyberpunk city at night with neon lights, 8K quality",
            output_name="test_image",
        )
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")
