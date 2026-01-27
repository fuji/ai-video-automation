"""
ニュース動画パイプライン

記事から複数シーンのニュース動画を自動生成
"""

import os
import subprocess
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from rich.console import Console
import google.generativeai as genai

import fal_client
import httpx
import time

from src.generators.image_generator import FluxImageGenerator
from src.config import config
from src.generators.narration_generator import NarrationGenerator
from src.editors.news_graphics import NewsGraphicsCompositor
from src.config import IMAGES_DIR, VIDEOS_DIR, OUTPUT_DIR

# AUDIO_DIR がなければ作成
AUDIO_DIR = OUTPUT_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)

console = Console()


@dataclass
class Scene:
    """シーン情報"""
    index: int
    description: str  # シーンの説明
    image_prompt: str  # Flux用プロンプト
    video_prompt: str  # Luma用プロンプト
    subtitle: str  # このシーンの字幕
    image_path: Optional[str] = None
    video_path: Optional[str] = None


@dataclass
class NewsVideoResult:
    """パイプライン結果"""
    success: bool
    video_path: Optional[str] = None
    scenes: list[Scene] = field(default_factory=list)
    audio_path: Optional[str] = None
    duration_seconds: float = 0.0
    error_message: Optional[str] = None


class NewsVideoPipeline:
    """ニュース動画生成パイプライン"""
    
    def __init__(
        self,
        channel_name: str = "FJ News 24",
        num_scenes: int = 3,
        scene_duration: float = 5.0,
    ):
        self.channel_name = channel_name
        self.num_scenes = num_scenes
        self.scene_duration = scene_duration
        
        # ジェネレーター初期化
        self.image_gen = FluxImageGenerator()
        self.narration_gen = NarrationGenerator()
        self.compositor = NewsGraphicsCompositor(channel_name=channel_name)
        
        # Gemini for scene analysis
        genai.configure(api_key=config.gemini.api_key)
        self.gemini = genai.GenerativeModel("gemini-2.0-flash")
        
        # FAL API key for Luma
        os.environ["FAL_KEY"] = config.fal.api_key
        
        console.print(f"[green]NewsVideoPipeline initialized[/green]")
        console.print(f"  Channel: {channel_name}")
        console.print(f"  Scenes: {num_scenes} x {scene_duration}s = {num_scenes * scene_duration}s")
    
    def analyze_article(
        self,
        article_text: str,
        headline: str,
    ) -> list[Scene]:
        """記事を分析して複数シーンに分解"""
        
        prompt = f"""以下のニュース記事を{self.num_scenes}つのシーンに分解してください。

# 記事
タイトル: {headline}
本文: {article_text}

# 出力形式 (JSON)
各シーンについて以下を生成:
- description: シーンの説明（日本語、1文）
- image_prompt: Flux画像生成用プロンプト（英語、具体的で視覚的な描写、50語以内）
- video_prompt: Luma動画生成用プロンプト（英語、カメラワークや動きの指示、20語以内）
- subtitle: このシーンのナレーション字幕（日本語、15-25文字）

# 注意
- image_promptはフォトリアリスティックなスタイルで
- 各シーンが物語として繋がるように
- 最初のシーンは状況説明、中間は展開、最後は結末

```json
{{
  "scenes": [
    {{
      "description": "...",
      "image_prompt": "...",
      "video_prompt": "...",
      "subtitle": "..."
    }}
  ]
}}
```"""

        console.print("\n[cyan]📝 記事を分析中...[/cyan]")
        
        response = self.gemini.generate_content(prompt)
        
        # JSONを抽出
        content = response.text
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        json_str = content[json_start:json_end]
        
        data = json.loads(json_str)
        
        scenes = []
        for i, scene_data in enumerate(data["scenes"]):
            scene = Scene(
                index=i,
                description=scene_data["description"],
                image_prompt=scene_data["image_prompt"],
                video_prompt=scene_data["video_prompt"],
                subtitle=scene_data["subtitle"],
            )
            scenes.append(scene)
            console.print(f"  シーン{i+1}: {scene.description}")
        
        return scenes
    
    def generate_scene_images(
        self,
        scenes: list[Scene],
        output_prefix: str,
    ) -> list[Scene]:
        """各シーンの画像を生成"""
        
        console.print("\n[cyan]🖼️ シーン画像を生成中...[/cyan]")
        
        for scene in scenes:
            output_name = f"{output_prefix}_scene{scene.index + 1}"
            
            result = self.image_gen.generate(
                prompt=scene.image_prompt,
                output_name=output_name,
                image_size="portrait_16_9",  # 縦動画用
            )
            
            if result.success:
                scene.image_path = result.file_path
                console.print(f"  ✅ シーン{scene.index + 1}: {result.file_path}")
            else:
                console.print(f"  ❌ シーン{scene.index + 1}: {result.error_message}")
        
        return scenes
    
    def generate_scene_videos(
        self,
        scenes: list[Scene],
        output_prefix: str,
    ) -> list[Scene]:
        """各シーンの動画を生成（Luma Dream Machine via fal.ai）"""
        
        console.print("\n[cyan]🎬 シーン動画を生成中 (Luma)...[/cyan]")
        
        for scene in scenes:
            if not scene.image_path:
                console.print(f"  ⚠️ シーン{scene.index + 1}: 画像がありません")
                continue
            
            output_path = str(VIDEOS_DIR / f"{output_prefix}_scene{scene.index + 1}.mp4")
            
            try:
                # 画像をfal.aiにアップロード
                image_url = fal_client.upload_file(scene.image_path)
                console.print(f"  📤 シーン{scene.index + 1}: 画像アップロード完了")
                
                # Luma API呼び出し
                result = fal_client.subscribe(
                    "fal-ai/luma-dream-machine/image-to-video",
                    arguments={
                        "prompt": scene.video_prompt,
                        "image_url": image_url,
                        "aspect_ratio": "9:16",
                    },
                    with_logs=False,
                )
                
                # 動画をダウンロード
                video_url = result["video"]["url"]
                response = httpx.get(video_url)
                with open(output_path, "wb") as f:
                    f.write(response.content)
                
                scene.video_path = output_path
                console.print(f"  ✅ シーン{scene.index + 1}: {output_path}")
                
            except Exception as e:
                console.print(f"  ❌ シーン{scene.index + 1}: {str(e)}")
        
        return scenes
    
    def generate_narration(
        self,
        scenes: list[Scene],
        output_prefix: str,
    ) -> str:
        """シーンの字幕からナレーション音声を生成"""
        
        console.print("\n[cyan]🎤 ナレーション生成中...[/cyan]")
        
        # 全シーンの字幕を結合
        full_text = "。".join([scene.subtitle for scene in scenes]) + "。"
        
        output_path = str(AUDIO_DIR / f"{output_prefix}_narration.mp3")
        
        result = self.narration_gen.generate(
            text=full_text,
            output_path=output_path,
        )
        
        if result.success:
            console.print(f"  ✅ 音声: {result.file_path} ({result.duration_seconds:.1f}秒)")
            return result.file_path
        else:
            console.print(f"  ❌ 音声生成失敗: {result.error_message}")
            return None
    
    def compose_final_video(
        self,
        scenes: list[Scene],
        audio_path: str,
        headline: str,
        sub_headline: str,
        output_prefix: str,
        is_breaking: bool = True,
    ) -> str:
        """全シーンを結合して最終動画を作成"""
        
        console.print("\n[cyan]🎬 最終動画を合成中...[/cyan]")
        
        # 動画があるシーンだけ抽出
        valid_scenes = [s for s in scenes if s.video_path]
        if not valid_scenes:
            raise ValueError("有効な動画がありません")
        
        # 最初の動画からサイズを取得
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0",
             valid_scenes[0].video_path],
            capture_output=True, text=True
        )
        width, height = map(int, probe.stdout.strip().split(','))
        
        # 一時ファイル用ディレクトリ
        temp_dir = VIDEOS_DIR / "temp"
        temp_dir.mkdir(exist_ok=True)
        
        # 1. 各シーンにオーバーレイと字幕を追加
        overlaid_videos = []
        
        for scene in valid_scenes:
            # ニュースオーバーレイ作成
            overlay_path = str(temp_dir / f"overlay_{scene.index}.png")
            self.compositor.create_transparent_overlay(
                width=width, height=height,
                headline=headline,
                sub_headline=sub_headline,
                is_breaking=is_breaking,
                style="solid",
                output_path=overlay_path,
            )
            
            # 字幕を追加
            overlay_img = Image.open(overlay_path).convert("RGBA")
            draw = ImageDraw.Draw(overlay_img)
            
            font = ImageFont.truetype(
                "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
                int(height * 0.032)
            )
            
            # 字幕を複数行に分割（長い場合）
            subtitle = scene.subtitle
            if len(subtitle) > 15:
                mid = len(subtitle) // 2
                for i in range(mid, 0, -1):
                    if subtitle[i] in 'がのをにはでと、。':
                        mid = i + 1
                        break
                lines = [subtitle[:mid], subtitle[mid:]]
            else:
                lines = [subtitle]
            
            margin_x = int(width * 0.10)
            max_text_width = width - margin_x * 2
            line_height = int(height * 0.045)
            total_text_height = len(lines) * line_height
            start_y = (height - total_text_height) // 2
            
            for i, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                text_w = bbox[2] - bbox[0]
                text_x = margin_x + (max_text_width - text_w) // 2
                y = start_y + i * line_height
                draw.text(
                    (text_x, y), line, font=font,
                    fill=(255, 255, 255, 255),
                    stroke_width=3,
                    stroke_fill=(0, 0, 0, 255)
                )
            
            scene_overlay_path = str(temp_dir / f"scene_overlay_{scene.index}.png")
            overlay_img.save(scene_overlay_path, "PNG")
            
            # FFmpegでオーバーレイ合成
            overlaid_path = str(temp_dir / f"overlaid_{scene.index}.mp4")
            subprocess.run([
                "ffmpeg", "-y",
                "-i", scene.video_path,
                "-i", scene_overlay_path,
                "-filter_complex", "[0:v][1:v]overlay=0:0",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-an", overlaid_path
            ], capture_output=True)
            
            overlaid_videos.append(overlaid_path)
            console.print(f"  ✅ シーン{scene.index + 1} オーバーレイ適用")
        
        # 2. 動画を結合
        concat_list_path = str(temp_dir / "concat_list.txt")
        with open(concat_list_path, "w") as f:
            for video_path in overlaid_videos:
                f.write(f"file '{video_path}'\n")
        
        concat_video_path = str(temp_dir / "concat.mp4")
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            concat_video_path
        ], capture_output=True)
        console.print("  ✅ 動画結合完了")
        
        # 3. 音声を追加
        final_path = str(VIDEOS_DIR / f"{output_prefix}_final.mp4")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", concat_video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            final_path
        ], capture_output=True)
        
        console.print(f"\n[green]🎉 完成: {final_path}[/green]")
        
        return final_path
    
    def run(
        self,
        article_text: str,
        headline: str,
        sub_headline: str = "",
        output_prefix: Optional[str] = None,
        is_breaking: bool = True,
    ) -> NewsVideoResult:
        """パイプライン全体を実行"""
        
        if output_prefix is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_prefix = f"news_{timestamp}"
        
        console.print("\n" + "=" * 50)
        console.print(f"[bold]📰 ニュース動画生成: {headline[:30]}...[/bold]")
        console.print("=" * 50)
        
        try:
            # 1. 記事分析
            scenes = self.analyze_article(article_text, headline)
            
            # 2. 画像生成
            scenes = self.generate_scene_images(scenes, output_prefix)
            
            # 3. 動画生成
            scenes = self.generate_scene_videos(scenes, output_prefix)
            
            # 4. ナレーション生成
            audio_path = self.generate_narration(scenes, output_prefix)
            
            # 5. 最終合成
            final_path = self.compose_final_video(
                scenes=scenes,
                audio_path=audio_path,
                headline=headline,
                sub_headline=sub_headline,
                output_prefix=output_prefix,
                is_breaking=is_breaking,
            )
            
            # 動画の長さを取得
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", final_path],
                capture_output=True, text=True
            )
            duration = float(probe.stdout.strip())
            
            return NewsVideoResult(
                success=True,
                video_path=final_path,
                scenes=scenes,
                audio_path=audio_path,
                duration_seconds=duration,
            )
            
        except Exception as e:
            console.print(f"[red]❌ エラー: {e}[/red]")
            import traceback
            traceback.print_exc()
            return NewsVideoResult(
                success=False,
                error_message=str(e),
            )


# CLI用
if __name__ == "__main__":
    import sys
    
    pipeline = NewsVideoPipeline()
    
    # テスト用
    result = pipeline.run(
        article_text="""
        スペインで行方不明になった猫が、5ヶ月かけて250キロを歩き、
        フランスの自宅に帰還しました。飼い主のファビアンさんは、
        愛猫ミヌシュが戻ってきた時、信じられなかったと語っています。
        猫は少し痩せていましたが、元気な様子でした。
        """,
        headline="猫が250km歩いてスペインからフランスの自宅に帰還",
        sub_headline="5ヶ月かけて155マイルを踏破",
        output_prefix="cat_journey",
    )
    
    print(f"\n結果: {'成功' if result.success else '失敗'}")
    if result.success:
        print(f"動画: {result.video_path}")
        print(f"長さ: {result.duration_seconds:.1f}秒")
