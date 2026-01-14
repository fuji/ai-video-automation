"""自動化パイプライン - 統合制御モジュール"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import config, FINAL_DIR
from ..logger import setup_logger, ProgressManager, print_header, print_success, print_error, print_info
from ..generators import ContentPlanner, ImageGenerator, VideoGenerator, VideoProject, create_sample_project
from ..editors import VideoEditor

logger = setup_logger("pipeline")


class VideoPipeline:
    """AI動画制作自動化パイプライン"""

    def __init__(self):
        self.content_planner: Optional[ContentPlanner] = None
        self.image_generator: Optional[ImageGenerator] = None
        self.video_generator: Optional[VideoGenerator] = None
        self.video_editor: Optional[VideoEditor] = None

        self.current_project: Optional[VideoProject] = None

    def initialize(self):
        """コンポーネントを初期化"""
        print_header("AI Video Automation - 初期化")

        # 設定検証
        result = config.validate()
        if result["errors"]:
            for e in result["errors"]:
                print_error(e)
            raise RuntimeError("Configuration errors")

        for w in result["warnings"]:
            logger.warning(w)

        # コンテンツプランナー
        try:
            self.content_planner = ContentPlanner()
            print_success("ContentPlanner initialized")
        except Exception as e:
            logger.warning(f"ContentPlanner unavailable: {e}")

        # 画像生成
        try:
            self.image_generator = ImageGenerator()
            print_success("ImageGenerator initialized")
        except Exception as e:
            logger.warning(f"ImageGenerator unavailable: {e}")

        # 動画生成
        try:
            self.video_generator = VideoGenerator()
            print_success("VideoGenerator initialized")
        except Exception as e:
            logger.warning(f"VideoGenerator unavailable: {e}")

        # 動画編集
        try:
            self.video_editor = VideoEditor()
            print_success("VideoEditor initialized")
        except Exception as e:
            logger.error(f"VideoEditor failed: {e}")
            raise

        print_info("Pipeline initialization complete")

    def generate_project(
        self,
        theme: str,
        style: str = "cinematic",
        scene_count: int = 3,
    ) -> VideoProject:
        """動画プロジェクトを生成"""
        print_header(f"コンセプト生成: {theme}")

        if self.content_planner:
            try:
                project = self.content_planner.generate_project(theme, style, scene_count)
                self.current_project = project
                print_success(f"Project: {project.title}")
                return project
            except Exception as e:
                logger.error(f"Concept generation failed: {e}")

        # フォールバック
        print_info("Using sample project")
        self.current_project = create_sample_project()
        return self.current_project

    def generate_images(
        self,
        project: VideoProject = None,
        reference_image: Optional[str] = None,
    ) -> list[str]:
        """プロジェクトの画像を生成"""
        project = project or self.current_project
        if not project:
            raise ValueError("No project available")

        if not self.image_generator:
            raise RuntimeError("ImageGenerator not initialized")

        print_header(f"画像生成: {len(project.scenes)}枚")
        generated_paths = []

        with ProgressManager() as progress:
            task = progress.add_task("画像生成中", total=len(project.scenes))

            for scene in project.scenes:
                output_name = f"{self._sanitize_name(project.title)}_scene{scene.number}"

                result = self.image_generator.generate(
                    prompt=scene.image_prompt,
                    output_name=output_name,
                    reference_image=reference_image or scene.reference_image,
                )

                if result.success:
                    generated_paths.append(result.file_path)
                    scene.image_path = result.file_path
                    print_success(f"Scene {scene.number}: {result.file_path}")
                else:
                    print_error(f"Scene {scene.number}: {result.error_message}")

                progress.update(task, advance=1)
                time.sleep(2)  # レート制限

        logger.info(f"Generated {len(generated_paths)}/{len(project.scenes)} images")
        return generated_paths

    def generate_videos(
        self,
        project: VideoProject = None,
        use_first_frame: bool = True,
    ) -> list[str]:
        """プロジェクトの動画を生成"""
        project = project or self.current_project
        if not project:
            raise ValueError("No project available")

        if not self.video_generator:
            raise RuntimeError("VideoGenerator not initialized")

        print_header(f"動画生成: {len(project.scenes)}本")
        generated_paths = []

        with ProgressManager() as progress:
            task = progress.add_task("動画生成中", total=len(project.scenes))

            for scene in project.scenes:
                output_name = f"{self._sanitize_name(project.title)}_video{scene.number}"

                # ファーストフレームを使用
                first_frame = scene.image_path if use_first_frame else None

                result = self.video_generator.generate(
                    prompt=scene.video_prompt,
                    output_name=output_name,
                    first_frame=first_frame,
                    duration=scene.duration,
                )

                if result.success:
                    generated_paths.append(result.file_path)
                    scene.video_path = result.file_path
                    print_success(f"Scene {scene.number}: {result.file_path}")
                else:
                    print_error(f"Scene {scene.number}: {result.error_message}")

                progress.update(task, advance=1)
                time.sleep(5)  # レート制限

        logger.info(f"Generated {len(generated_paths)}/{len(project.scenes)} videos")
        return generated_paths

    def create_final_video(
        self,
        project: VideoProject = None,
        audio_path: Optional[str] = None,
    ) -> str:
        """最終動画を作成"""
        project = project or self.current_project
        if not project:
            raise ValueError("No project available")

        if not self.video_editor:
            raise RuntimeError("VideoEditor not initialized")

        print_header("最終動画作成")

        # 動画パスを収集
        video_paths = [s.video_path for s in project.scenes if s.video_path]
        if not video_paths:
            raise ValueError("No videos to concatenate")

        # トランジション
        transitions = [s.transition for s in project.scenes]

        # 出力名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_name = f"{self._sanitize_name(project.title)}_{timestamp}"

        with ProgressManager() as progress:
            # 結合
            task = progress.add_task("動画結合中", total=3)

            result = self.video_editor.concatenate(video_paths, output_name, transitions)
            if not result.success:
                raise RuntimeError(f"Concatenation failed: {result.error_message}")
            progress.update(task, advance=1)

            current_path = result.output_path

            # 音声追加
            if audio_path and Path(audio_path).exists():
                progress.update(task, description="音声追加中")
                result = self.video_editor.add_audio(
                    current_path,
                    audio_path,
                    f"{output_name}_audio",
                )
                if result.success:
                    current_path = result.output_path
            progress.update(task, advance=1)

            # フェード効果
            progress.update(task, description="フェード効果追加中")
            result = self.video_editor.add_fade(
                current_path,
                f"{output_name}_final",
            )
            if result.success:
                current_path = result.output_path
            progress.update(task, advance=1)

        print_success(f"Final video: {current_path}")

        # プロジェクト保存
        project_path = FINAL_DIR / f"{output_name}_project.json"
        project.save(str(project_path))

        return current_path

    def run(
        self,
        theme: str,
        style: str = "cinematic",
        scene_count: int = 3,
        audio_path: Optional[str] = None,
        skip_images: bool = False,
        skip_videos: bool = False,
    ) -> str:
        """フルパイプラインを実行"""
        start_time = time.time()
        print_header("AI Video Automation Pipeline")

        try:
            # 初期化
            self.initialize()

            # コンセプト生成
            project = self.generate_project(theme, style, scene_count)
            print_info(f"Project: {project.title} ({len(project.scenes)} scenes)")

            # 画像生成
            if not skip_images:
                images = self.generate_images(project)
                print_info(f"Generated {len(images)} images")

            # 動画生成
            if not skip_videos:
                videos = self.generate_videos(project)
                print_info(f"Generated {len(videos)} videos")

            # 最終編集
            final_path = self.create_final_video(project, audio_path)

            elapsed = time.time() - start_time
            print_header("Complete")
            print_success(f"Total time: {elapsed:.1f}s")
            print_success(f"Output: {final_path}")

            return final_path

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            raise

    def _sanitize_name(self, name: str) -> str:
        """ファイル名をサニタイズ"""
        return "".join(c for c in name if c.isalnum() or c in "._- ")[:50]


if __name__ == "__main__":
    pipeline = VideoPipeline()
    pipeline.initialize()
