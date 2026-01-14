#!/usr/bin/env python3
"""AI Video Automation - CLIエントリーポイント"""

import sys
import argparse
from pathlib import Path

# srcをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from src.config import config
from src.logger import print_header, print_success, print_error, print_info, console
from src.pipeline import VideoPipeline
from src.generators import ContentPlanner, create_sample_project
from src.monetization import YouTubeUploader

# ニュース自動化
from src.pipeline.news_automation import NewsAutomationPipeline
from src.utils.trend_detector import TrendDetector


def cmd_run(args):
    """フルパイプラインを実行"""
    pipeline = VideoPipeline()

    final_video = pipeline.run(
        theme=args.theme,
        style=args.style,
        scene_count=args.scenes,
        audio_path=args.audio,
        skip_images=args.skip_images,
        skip_videos=args.skip_videos,
    )

    # YouTube投稿
    if args.upload and final_video:
        upload_to_youtube(final_video, pipeline.current_project)


def cmd_concept(args):
    """コンセプトのみ生成"""
    try:
        planner = ContentPlanner()
        project = planner.generate_project(
            theme=args.theme,
            style=args.style,
            scene_count=args.scenes,
        )
    except Exception as e:
        print_error(f"API error: {e}")
        print_info("Using sample project")
        project = create_sample_project()

    # 表示
    import json
    console.print_json(json.dumps(project.to_dict(), ensure_ascii=False))

    # 保存
    if args.output:
        project.save(args.output)
        print_success(f"Saved: {args.output}")


def cmd_upload(args):
    """動画をYouTubeにアップロード"""
    uploader = YouTubeUploader()

    result = uploader.upload(
        video_path=args.video,
        title=args.title,
        description=args.description or "",
        tags=args.tags.split(",") if args.tags else [],
        privacy_status=args.privacy,
    )

    if result.success:
        print_success(f"Uploaded: {result.video_url}")
    else:
        print_error(f"Upload failed: {result.error_message}")


def cmd_config(args):
    """設定状態を表示"""
    config.print_status()


def cmd_daily(args):
    """1日分のニュース動画を自動生成"""
    print_header(f"Daily News Video Generation - {args.count}本")

    pipeline = NewsAutomationPipeline()

    if args.auto:
        # 自動選択モード
        results = pipeline.run_daily(count=args.count)
    else:
        # 手動選択モード
        try:
            detector = TrendDetector()
            news_list = detector.get_best_news(count=args.count * 3)

            if not news_list:
                print_error("トレンドニュースが見つかりませんでした")
                return

            print_info("ニュース候補を選択してください:")
            for i, news in enumerate(news_list, 1):
                print(f"  {i}. [{news.source}] {news.title[:50]}...")
                print(f"     Score: {news.score:.1f} | {news.url[:50]}...")

            selected = input(f"\n番号を選択 (1-{len(news_list)}, カンマ区切りで複数可): ")
            indices = [int(x.strip()) - 1 for x in selected.split(",")]

            results = []
            for idx in indices[:args.count]:
                if 0 <= idx < len(news_list):
                    result = pipeline.run(
                        news=news_list[idx],
                        difficulty=args.difficulty,
                        target_duration=args.duration,
                        voice=args.voice,
                    )
                    results.append(result)

        except Exception as e:
            print_error(f"手動選択エラー: {e}")
            return

    # 結果サマリー
    print_header("Generation Summary")
    success_count = sum(1 for r in results if r.success)
    print_success(f"成功: {success_count}/{len(results)}")

    for result in results:
        if result.success:
            print_info(f"  ✓ {result.title[:40]}... → {result.video_path}")
        else:
            print_error(f"  ✗ {result.error_message}")

    # YouTube自動アップロード
    if args.upload:
        uploader = YouTubeUploader()
        for result in results:
            if result.success and result.video_path:
                upload_result = uploader.upload(
                    video_path=result.video_path,
                    title=result.title,
                    description=f"ソース: {result.source_url}",
                    tags=["ニュース", "AI", "自動生成"],
                    privacy_status="private",
                )
                if upload_result.success:
                    print_success(f"Uploaded: {upload_result.video_url}")


def cmd_news(args):
    """単一ニュースから動画生成"""
    from src.utils.trend_detector import TrendingNews

    print_header("News Video Generation")

    pipeline = NewsAutomationPipeline()

    # URLからニュース情報を作成
    news = TrendingNews(
        title=args.title or "ニュース動画",
        url=args.url,
        source="manual",
        published_at=None,
    )

    result = pipeline.run(
        news=news,
        difficulty=args.difficulty,
        target_duration=args.duration,
        voice=args.voice,
        add_bgm=args.bgm is not None,
        bgm_path=args.bgm,
    )

    if result.success:
        print_success(f"動画生成完了: {result.video_path}")
        print_info(f"タイトル: {result.title}")
        print_info(f"長さ: {result.duration:.1f}秒")
    else:
        print_error(f"生成失敗: {result.error_message}")


def upload_to_youtube(video_path: str, project):
    """動画をYouTubeにアップロード"""
    if not project:
        print_error("No project data for upload")
        return

    uploader = YouTubeUploader()

    result = uploader.upload(
        video_path=video_path,
        title=project.title,
        description=project.description,
        tags=project.tags,
        privacy_status="private",
    )

    if result.success:
        print_success(f"Uploaded: {result.video_url}")
    else:
        print_error(f"Upload failed: {result.error_message}")


def main():
    parser = argparse.ArgumentParser(
        description="AI Video Automation - SDK-based video production pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # フルパイプライン実行
  python main.py run --theme "サイバーパンク都市" --style cinematic

  # コンセプトのみ生成
  python main.py concept --theme "未来宇宙" --output project.json

  # 動画をYouTubeにアップロード
  python main.py upload --video output/final/video.mp4 --title "AI Generated"

  # 1日分のニュース動画を自動生成（2本）
  python main.py daily --count 2

  # ニュースを手動選択して生成
  python main.py daily --count 2 --manual

  # 単一ニュースURLから動画生成
  python main.py news --url "https://example.com/news/article" --duration 60

  # 設定確認
  python main.py config
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # run コマンド
    run_parser = subparsers.add_parser("run", help="Run full pipeline")
    run_parser.add_argument("--theme", "-t", required=True, help="Video theme")
    run_parser.add_argument("--style", "-s", default="cinematic", help="Video style")
    run_parser.add_argument("--scenes", "-n", type=int, default=3, help="Number of scenes")
    run_parser.add_argument("--audio", "-a", help="Background audio file")
    run_parser.add_argument("--skip-images", action="store_true", help="Skip image generation")
    run_parser.add_argument("--skip-videos", action="store_true", help="Skip video generation")
    run_parser.add_argument("--upload", "-u", action="store_true", help="Upload to YouTube")
    run_parser.set_defaults(func=cmd_run)

    # concept コマンド
    concept_parser = subparsers.add_parser("concept", help="Generate concept only")
    concept_parser.add_argument("--theme", "-t", required=True, help="Video theme")
    concept_parser.add_argument("--style", "-s", default="cinematic", help="Video style")
    concept_parser.add_argument("--scenes", "-n", type=int, default=3, help="Number of scenes")
    concept_parser.add_argument("--output", "-o", help="Output JSON file")
    concept_parser.set_defaults(func=cmd_concept)

    # upload コマンド
    upload_parser = subparsers.add_parser("upload", help="Upload video to YouTube")
    upload_parser.add_argument("--video", "-v", required=True, help="Video file path")
    upload_parser.add_argument("--title", "-t", required=True, help="Video title")
    upload_parser.add_argument("--description", "-d", help="Video description")
    upload_parser.add_argument("--tags", help="Comma-separated tags")
    upload_parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    upload_parser.set_defaults(func=cmd_upload)

    # config コマンド
    config_parser = subparsers.add_parser("config", help="Show configuration")
    config_parser.set_defaults(func=cmd_config)

    # daily コマンド（ニュース自動生成）
    daily_parser = subparsers.add_parser("daily", help="Generate daily news videos automatically")
    daily_parser.add_argument("--count", "-c", type=int, default=2, help="Number of videos to generate")
    daily_parser.add_argument("--auto/--manual", dest="auto", action="store_true", default=True, help="Auto-select news")
    daily_parser.add_argument("--manual", dest="auto", action="store_false", help="Manual news selection")
    daily_parser.add_argument("--difficulty", "-d", default="中学生", choices=["小学生", "中学生", "高校生", "一般"], help="Explanation difficulty")
    daily_parser.add_argument("--duration", type=int, default=60, help="Target duration in seconds")
    daily_parser.add_argument("--voice", default="Rachel", help="ElevenLabs voice name")
    daily_parser.add_argument("--upload", "-u", action="store_true", help="Auto-upload to YouTube")
    daily_parser.set_defaults(func=cmd_daily)

    # news コマンド（単一ニュース動画生成）
    news_parser = subparsers.add_parser("news", help="Generate video from a single news URL")
    news_parser.add_argument("--url", "-u", required=True, help="News article URL")
    news_parser.add_argument("--title", "-t", help="Override title")
    news_parser.add_argument("--difficulty", "-d", default="中学生", choices=["小学生", "中学生", "高校生", "一般"], help="Explanation difficulty")
    news_parser.add_argument("--duration", type=int, default=60, help="Target duration in seconds")
    news_parser.add_argument("--voice", default="Rachel", help="ElevenLabs voice name")
    news_parser.add_argument("--bgm", help="Background music file path")
    news_parser.set_defaults(func=cmd_news)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
