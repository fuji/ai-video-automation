"""ニュース動画自動化パイプライン - トレンド検知から動画生成まで"""

import os
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from moviepy import (
    VideoFileClip,
    AudioFileClip,
    concatenate_videoclips,
    CompositeVideoClip,
)
from moviepy.video.fx import Loop

from ..config import config, FINAL_DIR, IMAGES_DIR, VIDEOS_DIR, OUTPUT_DIR
from ..logger import (
    setup_logger,
    ProgressManager,
    print_header,
    print_success,
    print_error,
    print_info,
)
from ..utils.trend_detector import TrendDetector, TrendingNews
from ..utils.news_scraper import NewsScraper
from ..generators.news_explainer import NewsExplainer, NewsExplanation
from ..generators.narration_generator import NarrationGenerator, NarrationConfig
from ..generators.image_generator import ImageGenerator
from ..generators.veo_video_generator import VeoVideoGenerator
from ..editors.video_animator import VideoAnimator
from ..editors.subtitle_renderer import SubtitleRenderer
from ..editors.video_editor import VideoEditor

logger = setup_logger("news_automation")


@dataclass
class NewsVideoResult:
    """ニュース動画生成結果"""
    success: bool
    video_path: Optional[str] = None
    title: str = ""
    duration: float = 0.0
    error_message: Optional[str] = None
    source_url: str = ""


class NewsAutomationPipeline:
    """ニュース動画自動化パイプライン"""

    def __init__(self):
        self.trend_detector: Optional[TrendDetector] = None
        self.news_scraper: Optional[NewsScraper] = None
        self.news_explainer: Optional[NewsExplainer] = None
        self.narration_generator: Optional[NarrationGenerator] = None
        self.image_generator: Optional[ImageGenerator] = None
        self.veo_generator: Optional[VeoVideoGenerator] = None
        self.video_animator: Optional[VideoAnimator] = None
        self.subtitle_renderer: Optional[SubtitleRenderer] = None
        self.video_editor: Optional[VideoEditor] = None

        self._initialized = False
        self._use_veo = False  # Veo使用フラグ

    def initialize(self):
        """コンポーネント初期化"""
        if self._initialized:
            return

        print_header("News Automation Pipeline - 初期化")

        # トレンド検知
        try:
            self.trend_detector = TrendDetector()
            print_success("TrendDetector initialized")
        except Exception as e:
            logger.warning(f"TrendDetector init failed: {e}")

        # スクレイパー
        self.news_scraper = NewsScraper()
        print_success("NewsScraper initialized")

        # 解説生成
        try:
            self.news_explainer = NewsExplainer()
            print_success("NewsExplainer initialized")
        except Exception as e:
            logger.warning(f"NewsExplainer init failed: {e}")

        # ナレーション生成
        try:
            self.narration_generator = NarrationGenerator()
            print_success("NarrationGenerator initialized")
        except Exception as e:
            logger.warning(f"NarrationGenerator init failed: {e}")

        # 画像生成
        try:
            self.image_generator = ImageGenerator()
            print_success("ImageGenerator initialized")
        except Exception as e:
            logger.warning(f"ImageGenerator init failed: {e}")

        # Veo動画生成
        try:
            self.veo_generator = VeoVideoGenerator()
            self._use_veo = True
            print_success("VeoVideoGenerator initialized")
        except Exception as e:
            logger.warning(f"VeoVideoGenerator init failed: {e}")
            self._use_veo = False

        # アニメーター（Veoフォールバック用）
        self.video_animator = VideoAnimator()
        print_success("VideoAnimator initialized")

        # 字幕レンダラー
        self.subtitle_renderer = SubtitleRenderer()
        print_success("SubtitleRenderer initialized")

        # 動画エディター
        self.video_editor = VideoEditor()
        print_success("VideoEditor initialized")

        self._initialized = True
        print_info("Pipeline initialization complete")

    def run(
        self,
        news: TrendingNews,
        difficulty: str = "中学生",
        target_duration: int = 60,
        voice: str = "Rachel",
        add_bgm: bool = False,
        bgm_path: str = None,
    ) -> NewsVideoResult:
        """単一ニュースから動画を生成

        Args:
            news: ニュース情報
            difficulty: 解説の難易度
            target_duration: 目標秒数（30-90）
            voice: ナレーションボイス
            add_bgm: BGMを追加するか
            bgm_path: BGMファイルパス

        Returns:
            NewsVideoResult
        """
        if not self._initialized:
            self.initialize()

        start_time = time.time()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        logger.info(f"Processing: {news.title[:50]}...")

        try:
            with ProgressManager() as progress:
                task = progress.add_task("ニュース動画生成", total=6)

                # 1. 記事スクレイピング
                progress.update(task, description="記事取得中...")
                article = self.news_scraper.scrape(news.url)
                if not article.text:
                    raise ValueError("Failed to scrape article")
                progress.update(task, advance=1)

                # 2. 解説生成
                progress.update(task, description="解説生成中...")
                explanation = self.news_explainer.explain(
                    article,
                    difficulty=difficulty,
                    target_duration=target_duration,
                )
                progress.update(task, advance=1)

                # 3. ナレーション生成
                progress.update(task, description="ナレーション生成中...")
                narration_script = explanation.get_narration_script()
                # NarrationConfig.news_style() から voice を除外して渡す
                style_config = NarrationConfig.news_style()
                style_config.pop("voice", None)  # voice は引数で指定するので除外
                narration_result = self.narration_generator.generate(
                    text=narration_script,
                    output_path=str(OUTPUT_DIR / "audio" / f"narration_{timestamp}.mp3"),
                    voice=voice,
                    **style_config,
                )
                if not narration_result.success:
                    raise ValueError(f"Narration failed: {narration_result.error_message}")
                progress.update(task, advance=1)

                # 4. 背景画像生成
                progress.update(task, description="背景画像生成中...")
                image_paths = self._generate_background_images(
                    explanation, timestamp
                )
                progress.update(task, advance=1)

                # 5. 動画アニメーション作成
                progress.update(task, description="動画アニメーション中...")
                animated_videos = self._create_animated_videos(
                    image_paths, explanation, timestamp
                )
                progress.update(task, advance=1)

                # 6. 最終合成
                progress.update(task, description="最終合成中...")
                final_path = self._compose_final_video(
                    animated_videos,
                    narration_result.file_path,
                    explanation,
                    timestamp,
                    add_bgm,
                    bgm_path,
                )
                progress.update(task, advance=1)

            elapsed = time.time() - start_time
            print_success(f"完成: {final_path} ({elapsed:.1f}s)")

            return NewsVideoResult(
                success=True,
                video_path=final_path,
                title=explanation.title,
                duration=explanation.estimated_duration,
                source_url=news.url,
            )

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            return NewsVideoResult(
                success=False,
                error_message=str(e),
                source_url=news.url,
            )

    def _create_enhanced_image_prompt(self, title: str, base_prompt: str) -> str:
        """ニュースに合わせた視覚的にインパクトのある画像プロンプトを生成"""
        base_style = (
            "cinematic, dramatic lighting, vibrant colors, "
            "high contrast, professional news graphics style, "
            "modern, eye-catching, broadcast quality, "
            "depth of field, dynamic composition"
        )

        # ニュースカテゴリに応じたビジュアルスタイル
        if any(k in title for k in ["政治", "選挙", "国会", "首相", "政府"]):
            theme = "Japanese national diet building, political scene, dramatic sky, news broadcast style"
        elif any(k in title for k in ["経済", "株", "円", "金融", "市場"]):
            theme = "financial district, stock market charts, business scene, Tokyo cityscape at night with neon lights"
        elif any(k in title for k in ["テクノロジー", "AI", "IT", "デジタル", "ロボット"]):
            theme = "futuristic technology, digital world, cyber space, holographic displays, circuit patterns"
        elif any(k in title for k in ["国際", "世界", "外交", "海外"]):
            theme = "world map, global network, international flags, earth from space"
        elif any(k in title for k in ["科学", "研究", "発見", "宇宙"]):
            theme = "scientific laboratory, space exploration, microscopic view, DNA helix"
        elif any(k in title for k in ["スポーツ", "五輪", "サッカー", "野球"]):
            theme = "sports stadium, dynamic action, spotlights, athletic energy"
        else:
            theme = "abstract modern background, dynamic geometric shapes, energy waves, gradient colors"

        # base_promptがあれば組み合わせ
        if base_prompt:
            return f"{base_prompt}, {theme}, {base_style}, no text, no people's faces, 16:9 aspect ratio"
        return f"{theme}, {base_style}, no text, no people's faces, 16:9 aspect ratio"

    def _generate_background_images(
        self,
        explanation: NewsExplanation,
        timestamp: str,
    ) -> list[str]:
        """背景画像を生成"""
        image_paths = []

        if not self.image_generator:
            logger.warning("ImageGenerator not available")
            return []

        # 画像プロンプトを強化して生成
        prompts_to_use = []
        if explanation.image_prompts:
            for prompt in explanation.image_prompts[:3]:
                enhanced = self._create_enhanced_image_prompt(explanation.title, prompt)
                prompts_to_use.append(enhanced)
        else:
            # プロンプトがない場合はタイトルから生成
            for i in range(3):
                enhanced = self._create_enhanced_image_prompt(explanation.title, "")
                prompts_to_use.append(enhanced)

        for i, prompt in enumerate(prompts_to_use):
            output_name = f"bg_{timestamp}_{i:02d}"
            logger.info(f"Generating image {i+1}/3 with enhanced prompt")
            result = self.image_generator.generate(prompt, output_name)
            if result.success:
                image_paths.append(result.file_path)
            time.sleep(1)

        if not image_paths:
            logger.warning("No images generated, pipeline may fail")

        return image_paths

    def _create_animated_videos(
        self,
        image_paths: list[str],
        explanation: NewsExplanation,
        timestamp: str,
    ) -> list[str]:
        """画像をアニメーション化（Veo優先、フォールバックでFFmpeg）"""
        animated_paths = []

        if not image_paths:
            logger.warning("No images to animate")
            return []

        # 各セグメントの長さを計算
        segment_duration = max(5, explanation.estimated_duration // len(image_paths))
        scene_types = ["intro", "detail", "outro"]

        # ニュースカテゴリを判定
        news_category = "default"
        if self.veo_generator:
            news_category = self.veo_generator.detect_category(explanation.title)
            logger.info(f"Detected category: {news_category}")

        for i, image_path in enumerate(image_paths):
            scene_type = scene_types[i % len(scene_types)]
            output_path = str(VIDEOS_DIR / f"animated_{timestamp}_{i:02d}.mp4")

            # Veoで動画生成を試行
            if self._use_veo and self.veo_generator:
                logger.info(f"Generating video {i+1}/{len(image_paths)} with Veo...")

                # ダイナミックなプロンプト生成
                veo_prompt = self.veo_generator.create_dynamic_prompt(
                    news_category=news_category,
                    scene_type=scene_type,
                )

                result = self.veo_generator.generate_from_image(
                    image_path=image_path,
                    output_path=output_path,
                    prompt=veo_prompt,
                    duration=segment_duration,
                    resolution="1080p",
                    aspect_ratio="16:9",
                )

                if result.success:
                    animated_paths.append(result.output_path)
                    continue
                else:
                    logger.warning(f"Veo failed, falling back to FFmpeg: {result.error_message}")

            # フォールバック: FFmpegでKen Burns効果
            effects = ["dynamic", "ken_burns", "zoom_in"]
            effect = effects[i % len(effects)]

            result = self.video_animator.animate(
                image_path,
                duration=segment_duration,
                effect=effect,
                output_path=output_path,
            )
            if result.success:
                animated_paths.append(result.output_path)

        return animated_paths

    def _compose_final_video(
        self,
        video_paths: list[str],
        audio_path: str,
        explanation: NewsExplanation,
        timestamp: str,
        add_bgm: bool,
        bgm_path: str,
    ) -> str:
        """最終動画を合成"""
        output_path = str(FINAL_DIR / f"news_{timestamp}.mp4")

        try:
            # 動画クリップを読み込み
            video_clips = []
            for path in video_paths:
                if path and Path(path).exists():
                    clip = VideoFileClip(path)
                    video_clips.append(clip)

            if not video_clips:
                raise ValueError("No video clips available")

            # 動画を結合
            if len(video_clips) > 1:
                final_video = concatenate_videoclips(video_clips, method="compose")
            else:
                final_video = video_clips[0]

            # ナレーション音声を追加
            if audio_path and Path(audio_path).exists():
                narration = AudioFileClip(audio_path)

                # 動画の長さを音声に合わせる
                if final_video.duration < narration.duration:
                    # 動画を延長（最後のフレームを繰り返し）
                    final_video = final_video.with_effects([Loop(duration=narration.duration)])
                elif final_video.duration > narration.duration:
                    final_video = final_video.subclipped(0, narration.duration)

                final_video = final_video.with_audio(narration)

            # 字幕を追加
            subtitles = self.subtitle_renderer.create_subtitles_from_audio_timing(
                explanation.full_script,
                final_video.duration,
            )

            # 一時出力
            temp_path = str(FINAL_DIR / f"temp_{timestamp}.mp4")
            final_video.write_videofile(
                temp_path,
                fps=config.video.fps,
                codec="libx264",
                audio_codec="aac",
                logger=None,
            )

            # 字幕焼き込み
            if subtitles:
                subtitle_result = self.subtitle_renderer.add_subtitles(
                    temp_path,
                    subtitles,
                    output_path,
                )
                if subtitle_result.success:
                    Path(temp_path).unlink(missing_ok=True)
                else:
                    # 字幕失敗時は字幕なしで出力
                    os.rename(temp_path, output_path)
            else:
                os.rename(temp_path, output_path)

            # クリーンアップ
            for clip in video_clips:
                clip.close()
            final_video.close()

            return output_path

        except Exception as e:
            logger.error(f"Composition failed: {e}")
            raise

    def run_daily(self, count: int = 2) -> list[NewsVideoResult]:
        """1日分の動画を自動生成

        Args:
            count: 生成する動画数

        Returns:
            NewsVideoResultのリスト
        """
        if not self._initialized:
            self.initialize()

        print_header(f"Daily News Videos - {count}本生成")

        # トレンドニュース取得
        if not self.trend_detector:
            print_error("TrendDetector not available")
            return []

        news_list = self.trend_detector.get_best_news(count=count * 2)  # 予備含む

        if not news_list:
            print_error("No trending news found")
            return []

        print_info(f"Found {len(news_list)} candidate news")

        results = []
        success_count = 0

        for i, news in enumerate(news_list):
            if success_count >= count:
                break

            print_info(f"\n[{success_count + 1}/{count}] {news.title[:40]}...")

            result = self.run(news)

            if result.success:
                success_count += 1
                results.append(result)
                print_success(f"Video created: {result.video_path}")
            else:
                print_error(f"Failed: {result.error_message}")

            # レート制限対策
            if i < len(news_list) - 1:
                time.sleep(5)

        print_header("Daily Generation Complete")
        print_success(f"Generated {success_count}/{count} videos")

        return results


if __name__ == "__main__":
    # テスト実行
    pipeline = NewsAutomationPipeline()
    pipeline.initialize()
