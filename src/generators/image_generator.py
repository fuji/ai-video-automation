"""画像生成モジュール - Flux Pro via fal.ai"""

import os
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import httpx

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
    image_url: Optional[str] = None
    error_message: Optional[str] = None
    generation_time: float = 0.0


class FluxImageGenerator:
    """Flux Pro (fal.ai) を使用した高品質画像生成"""

    def __init__(self):
        self.api_key = config.fal.api_key
        if not self.api_key:
            raise ValueError("FAL_KEY is not set")

        self.model = config.fal.model
        self.image_size = config.fal.image_size

        # fal_client の環境変数を設定
        os.environ["FAL_KEY"] = self.api_key

        logger.info(f"FluxImageGenerator initialized with {self.model}")

    def generate(
        self,
        prompt: str,
        output_name: str,
        image_size: Optional[str] = None,
        retry_count: int = None,
        output_dir: Optional[Path] = None,
    ) -> ImageResult:
        """画像を生成

        Args:
            prompt: 画像生成プロンプト
            output_name: 出力ファイル名（拡張子なし）
            image_size: 画像サイズ（landscape_16_9, portrait_16_9, square, etc）
            retry_count: リトライ回数
            output_dir: 出力ディレクトリ（Noneの場合はデフォルト）

        Returns:
            ImageResult
        """
        import fal_client

        start_time = time.time()
        retries = retry_count or config.retry_count
        size = image_size or self.image_size

        logger.info(f"Generating image: {output_name}")
        logger.debug(f"Prompt: {prompt[:100]}...")

        for attempt in range(retries):
            try:
                # Flux Pro API 呼び出し
                result = fal_client.subscribe(
                    self.model,
                    arguments={
                        "prompt": prompt,
                        "image_size": size,
                        "num_images": 1,
                        "enable_safety_checker": False,
                    },
                )

                if result and "images" in result and len(result["images"]) > 0:
                    image_url = result["images"][0]["url"]
                    logger.info(f"Image generated: {image_url}")

                    # 画像をダウンロードして保存
                    save_dir = output_dir or IMAGES_DIR
                    save_dir.mkdir(parents=True, exist_ok=True)
                    output_path = save_dir / f"{output_name}.png"
                    if self._download_image(image_url, str(output_path)):
                        return ImageResult(
                            success=True,
                            file_path=str(output_path),
                            image_url=image_url,
                            generation_time=time.time() - start_time,
                        )

            except Exception as e:
                error_str = str(e).lower()
                logger.warning(f"Attempt {attempt + 1}/{retries} failed: {e}")

                if attempt < retries - 1:
                    time.sleep(config.retry_delay)

        return ImageResult(
            success=False,
            error_message="All attempts failed",
            generation_time=time.time() - start_time,
        )

    def _download_image(self, url: str, output_path: str) -> bool:
        """画像をダウンロードして保存"""
        try:
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                response = client.get(url)

                if response.status_code == 200:
                    # PIL で開いて PNG として保存
                    image = Image.open(io.BytesIO(response.content))
                    image.save(output_path, "PNG")
                    logger.info(f"Image saved: {output_path}")
                    return True
                else:
                    logger.error(f"Download failed: {response.status_code}")
                    return False

        except Exception as e:
            logger.error(f"Download error: {e}")
            return False

    def generate_batch(
        self,
        prompts: list[tuple[str, str]],  # [(prompt, output_name), ...]
        image_size: Optional[str] = None,
    ) -> list[ImageResult]:
        """複数画像をバッチ生成"""
        results = []

        for i, (prompt, name) in enumerate(prompts):
            logger.info(f"Batch progress: {i + 1}/{len(prompts)}")
            result = self.generate(prompt, name, image_size)
            results.append(result)

            # API負荷軽減のため少し待機
            if i < len(prompts) - 1:
                time.sleep(1)

        return results

    def generate_news_image(
        self,
        news_title: str,
        news_summary: str,
        style: str = "photorealistic",
        output_name: str = "news_image",
    ) -> ImageResult:
        """ニュース用の画像を生成

        Args:
            news_title: ニュースタイトル
            news_summary: ニュース概要
            style: 画像スタイル（photorealistic, cinematic, etc）
            output_name: 出力ファイル名

        Returns:
            ImageResult
        """
        # ニュース向けプロンプトを構築
        prompt = self._build_news_prompt(news_title, news_summary, style)
        return self.generate(prompt, output_name)

    def _build_news_prompt(
        self,
        title: str,
        summary: str,
        style: str,
    ) -> str:
        """ニュース画像用のプロンプトを構築"""
        # スタイル別のプレフィックス
        style_prefixes = {
            "photorealistic": "Photorealistic news photography style,",
            "cinematic": "Cinematic news broadcast style, dramatic lighting,",
            "documentary": "Documentary photography style, natural lighting,",
            "infographic": "Clean infographic style, data visualization,",
        }

        prefix = style_prefixes.get(style, style_prefixes["photorealistic"])

        # 品質タグ
        quality_tags = (
            "8K resolution, professional news photography, "
            "sharp focus, high detail, broadcast quality"
        )

        # 最終プロンプト
        prompt = f"{prefix} {title}. {summary}. {quality_tags}"

        return prompt


# 後方互換性のためのエイリアス
class ImageGenerator(FluxImageGenerator):
    """ImageGenerator のエイリアス（後方互換性）"""
    pass


def create_image_generator(provider: str = "flux") -> FluxImageGenerator:
    """画像生成器のファクトリー関数

    Args:
        provider: プロバイダー名（"flux" のみサポート）

    Returns:
        FluxImageGenerator
    """
    if provider == "flux":
        return FluxImageGenerator()
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'flux'.")


if __name__ == "__main__":
    # テスト実行
    try:
        generator = FluxImageGenerator()
        result = generator.generate(
            prompt="Breaking news broadcast scene, Tokyo Shibuya crossing at night, "
                   "rainy weather, neon lights reflecting on wet pavement, "
                   "cinematic news camera angle, photorealistic, 8K quality",
            output_name="test_flux_image",
        )
        print(f"Result: {result}")
        if result.success:
            print(f"Image saved to: {result.file_path}")
            print(f"Image URL: {result.image_url}")
    except Exception as e:
        print(f"Error: {e}")
