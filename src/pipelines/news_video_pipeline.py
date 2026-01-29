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
from google import genai

import fal_client
import httpx
import time

from src.generators.image_generator import FluxImageGenerator
from src.generators.remotion_generator import RemotionGenerator, SceneConfig
from src.config import config, get_daily_output_dirs
from src.generators.edge_tts_generator import EdgeTTSGenerator  # 無料TTS
from src.editors.news_graphics import NewsGraphicsCompositor
from src.editors.intro_outro import IntroOutroGenerator, IntroOutroConfig
from src.audio.bgm_manager import BGMManager, MoodType

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
        num_scenes: int = 10,  # 10シーンで約60-90秒の動画
        scene_duration: float = 5.0,
        use_remotion: bool = True,  # Remotion を使う（無料）か Luma を使う（有料）
    ):
        self.channel_name = channel_name
        self.num_scenes = num_scenes
        self.scene_duration = scene_duration
        self.use_remotion = use_remotion
        
        # 日付ベースの出力ディレクトリ
        self.dirs = get_daily_output_dirs()
        
        # ジェネレーター初期化
        self.image_gen = FluxImageGenerator()
        self.narration_gen = EdgeTTSGenerator()  # 無料TTS (Edge TTS)
        self.compositor = NewsGraphicsCompositor(channel_name=channel_name)
        self.bgm_manager = BGMManager()  # BGM管理
        self.intro_outro_gen = IntroOutroGenerator(IntroOutroConfig(
            channel_name=channel_name,
            channel_tagline="世界のおもしろニュース",
        ))
        
        # Remotion ジェネレーター（無料モーショングラフィックス）
        if use_remotion:
            self.remotion_gen = RemotionGenerator()
            console.print(f"[cyan]🎬 Remotion モード（無料）[/cyan]")
        else:
            self.remotion_gen = None
        
        # Gemini for scene analysis
        self.gemini_client = genai.Client(api_key=config.gemini.api_key)
        
        # FAL API key for Luma (Remotion使わない場合)
        if not use_remotion:
            os.environ["FAL_KEY"] = config.fal.api_key
        
        console.print(f"[green]NewsVideoPipeline initialized[/green]")
        console.print(f"  Output: {self.dirs['root']}")
        console.print(f"  Channel: {channel_name}")
        console.print(f"  Scenes: {num_scenes} x {scene_duration}s = {num_scenes * scene_duration}s")
        console.print(f"  Mode: {'Remotion (無料)' if use_remotion else 'Luma (有料)'}")
    
    def generate_scenes_data(
        self,
        article_text: str,
        headline: str,
        num_scenes: int = 10,
    ) -> dict:
        """記事からシーン構成データを生成（ユーモア付き、長めナレーション）
        
        Returns:
            dict: run() に渡せる形式 {headline, sub_headline, scenes_data, closing_text, ...}
        """
        
        prompt = f"""あなたはニュース動画のスクリプトライターです。以下の記事を面白く、視聴者が最後まで見たくなるような動画に構成してください。

# 記事
タイトル: {headline}
本文: {article_text}

# 重要な指示
1. **ユーモアを入れる**: 真面目すぎず、軽いツッコミや面白い視点を入れる
2. **視聴者を引き込む**: 冒頭で「え、何それ？」と思わせるフック
3. **長めのナレーション**: 各シーン8-15秒程度のナレーション（30-60文字）
4. **感情を込める**: 驚き、感動、笑いなど感情が伝わるように
5. **締めの一言**: 印象に残る締めくくり

# ユーモアの例
❌ 猫が250km歩いて帰還しました。
✅ グーグルマップも、スマホも使わずに250km。猫ってすごいですね。

❌ 2歳の子供が世界記録を達成しました。
✅ まだオムツが取れてないのに世界記録。大人の面目丸つぶれです。

# シーン構成（4グループ × 3シーン = 12シーン固定）
記事を4つのパートに分割し、各パートに1つの画像（image_group）を割り当てる：
- グループ1: 導入・状況設定（3シーン）
- グループ2: 展開・出来事の詳細（3シーン）
- グループ3: クライマックス・最も印象的な部分（3シーン）
- グループ4: 結末・締めくくり（3シーン）

各グループ内の3シーンは同じ画像を使うので、ナレーションで変化をつける。

# 出力形式 (JSON)
```json
{{
  "headline": "短いタイトル（15文字以内）",
  "sub_headline": "サブタイトル（20文字以内）",
  "mood": "emotional|funny|dramatic|informative",
  "scenes": [
    {{"image_group": 1, "visual_description": "グループ1の画像説明（英語）", "narration": "ナレーション1-1"}},
    {{"image_group": 1, "visual_description": "（同上）", "narration": "ナレーション1-2"}},
    {{"image_group": 1, "visual_description": "（同上）", "narration": "ナレーション1-3"}},
    {{"image_group": 2, "visual_description": "グループ2の画像説明（英語）", "narration": "ナレーション2-1"}},
    {{"image_group": 2, "visual_description": "（同上）", "narration": "ナレーション2-2"}},
    {{"image_group": 2, "visual_description": "（同上）", "narration": "ナレーション2-3"}},
    {{"image_group": 3, "visual_description": "グループ3の画像説明（英語）", "narration": "ナレーション3-1"}},
    {{"image_group": 3, "visual_description": "（同上）", "narration": "ナレーション3-2"}},
    {{"image_group": 3, "visual_description": "（同上）", "narration": "ナレーション3-3"}},
    {{"image_group": 4, "visual_description": "グループ4の画像説明（英語）", "narration": "ナレーション4-1"}},
    {{"image_group": 4, "visual_description": "（同上）", "narration": "ナレーション4-2"}},
    {{"image_group": 4, "visual_description": "（同上）", "narration": "ナレーション4-3"}}
  ],
  "closing_text": "締めの一言（日本語、20文字程度）"
}}
```

**必ず12シーン（4グループ × 3シーン）で生成してください。**"""

        console.print(f"\n[cyan]📝 シーン構成を生成中（{num_scenes}シーン）...[/cyan]")
        
        response = self.gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        
        # JSONを抽出
        content = response.text
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        json_str = content[json_start:json_end]
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            console.print(f"[yellow]⚠️ JSON パースエラー、修正を試みます...[/yellow]")
            import re
            # 余分なカンマを削除、改行を整理
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                console.print(f"[red]❌ JSON パース失敗[/red]")
                console.print(f"[dim]{content[:800]}...[/dim]")
                raise
        
        console.print(f"  ✅ {len(data.get('scenes', []))}シーン生成")
        console.print(f"  📰 {data.get('headline', headline)}")
        console.print(f"  🎭 ムード: {data.get('mood', 'neutral')}")
        
        return data
    
    def analyze_article(
        self,
        article_text: str,
        headline: str,
    ) -> list[Scene]:
        """記事を分析して複数シーンに分解（後方互換用）"""
        
        prompt = f"""以下のニュース記事を{self.num_scenes}つの映像的なシーンに分解してください。

# 記事
タイトル: {headline}
本文: {article_text}

# シーン構成ガイド（{self.num_scenes}シーン）
1. オープニング: 状況設定、主人公や舞台の紹介
2. 展開1: 出来事の始まり、問題や状況の発生
3. 展開2: クライマックス、最も印象的な瞬間
4. エンディング: 結末、現在の状況、余韻

# 出力形式 (JSON)
各シーンについて以下を生成:
- description: シーンの説明（日本語、1文で映像をイメージできるように）
- image_prompt: Flux画像生成用プロンプト（英語、70語以内）
  * 具体的な被写体、場所、時間帯、雰囲気を含める
  * "photorealistic, cinematic lighting, 4K quality" を含める
  * 人物がいる場合は表情や動作も描写
- video_prompt: Luma動画生成用プロンプト（英語、25語以内）
  * カメラワーク（pan, zoom, dolly等）を指定
  * 動きの方向と速度を含める
- subtitle: このシーンの字幕（日本語、20-30文字、感情が伝わるように）

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
        
        response = self.gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        
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
                output_dir=self.dirs["images"],
            )
            
            if result.success:
                scene.image_path = result.file_path
                console.print(f"  ✅ シーン{scene.index + 1}: {result.file_path}")
            else:
                console.print(f"  ❌ シーン{scene.index + 1}: {result.error_message}")
        
        return scenes
    
    def generate_scene_videos_remotion(
        self,
        scenes: list[Scene],
        output_prefix: str,
        headline: str = "",
        sub_headline: str = "",
        is_breaking: bool = True,
        news_style: bool = True,
        mood: str = "exciting",
    ) -> list[Scene]:
        """Remotion でニュース風動画を生成
        
        Args:
            scenes: シーンリスト（image_path があればそれを背景に使用）
            output_prefix: 出力ファイル名プレフィックス
            headline: ヘッドライン（最初のシーンのみ表示）
            sub_headline: サブヘッドライン
            is_breaking: BREAKING NEWS 表示
            news_style: ニュース風スタイルを使用
            mood: ムード（グラデーション背景の場合に使用）
        """
        
        console.print("\n[cyan]🎬 シーン動画を生成中 (Remotion)...[/cyan]")
        
        # ムードに基づく色（フォールバック用）
        mood_colors = {
            "exciting": ["#FF6B6B", "#FF8E53"],
            "heartwarming": ["#A8E6CF", "#DCEDC1"],
            "funny": ["#FFE66D", "#FFB347"],
            "shocking": ["#E94560", "#1A1A2E"],
            "informative": ["#4ECDC4", "#44A08D"],
        }
        
        # 画像グループごとにアニメーション進捗を計算（v11方式）
        # 同じ画像を使うシーンでアニメーションが継続する
        image_groups = {}  # image_path -> list of scene indices
        image_group_numbers = {}  # image_path -> group number (1-based)
        group_counter = 1
        for scene in scenes:
            img = getattr(scene, 'image_path', None)
            if img:
                if img not in image_groups:
                    image_groups[img] = []
                    image_group_numbers[img] = group_counter
                    group_counter += 1
                image_groups[img].append(scene.index)
        
        # 各グループの合計時間を計算
        group_durations = {}
        for img, indices in image_groups.items():
            total = sum(getattr(scenes[i], 'audio_duration', 5.0) or 5.0 for i in indices)
            group_durations[img] = total
        
        # 各シーンのアニメーション開始/終了位置を計算
        group_progress = {img: 0.0 for img in image_groups}
        scene_anim = {}  # scene.index -> (start, end)
        for scene in scenes:
            img = getattr(scene, 'image_path', None)
            if img and img in group_durations:
                total = group_durations[img]
                dur = getattr(scene, 'audio_duration', 5.0) or 5.0
                start = group_progress[img] / total if total > 0 else 0
                group_progress[img] += dur
                end = group_progress[img] / total if total > 0 else 1
                scene_anim[scene.index] = (start, end)
            else:
                scene_anim[scene.index] = (0.0, 1.0)
        
        for scene in scenes:
            output_path = str(self.dirs["videos"] / f"{output_prefix}_scene{scene.index + 1}.mp4")
            duration = getattr(scene, 'audio_duration', 5.0) or 5.0
            narration_text = getattr(scene, 'narration_text', scene.subtitle) or scene.description
            anim_start, anim_end = scene_anim.get(scene.index, (0.0, 1.0))
            
            # 画像グループ番号を取得（同じ画像 = 同じアニメーションパターン）
            img = getattr(scene, 'image_path', None)
            group_num = image_group_numbers.get(img, scene.index + 1) if img else scene.index + 1
            
            # 背景画像があればニュース風、なければモーショングラフィックス
            if scene.image_path and news_style:
                # ニュース風（背景画像 + オーバーレイ）
                # - チャンネルロゴ: 全シーンで表示
                # - バナー（BREAKING + タイトル + サブタイトル）: 全シーンで表示
                # - 字幕: 全シーンで表示
                result = self.remotion_gen.generate_news_scene(
                    scene_number=group_num,  # 画像グループ番号でアニメーションパターン決定
                    duration=duration,
                    output_path=output_path,
                    background_image=scene.image_path,
                    subtitle=narration_text if narration_text else "",  # 全文表示
                    headline=headline,  # 全シーンで表示
                    sub_headline=sub_headline,  # 全シーンで表示
                    channel_name=self.channel_name,
                    is_breaking=is_breaking,  # 全シーンで表示
                    show_overlay=True,  # 全シーンで表示
                    animation_start=anim_start,
                    animation_end=anim_end,
                )
            else:
                # モーショングラフィックス風（グラデーション背景）
                base_colors = mood_colors.get(mood, mood_colors["exciting"])
                scene_config = SceneConfig(
                    scene_number=scene.index + 1,
                    duration=duration,
                    background_colors=base_colors,
                    elements=[
                        {
                            "type": "emoji",
                            "content": self._get_emoji_for_scene(scene.description),
                            "style": {"size": "xxl"},
                            "position": {"x": "center", "y": "center", "offsetY": -100},
                            "animation": {"enter": "bounce-in", "delay": 0},
                        },
                        {
                            "type": "text",
                            "content": narration_text[:40] if narration_text else scene.description[:40],
                            "style": {"size": "lg", "weight": "bold", "color": "#FFFFFF"},
                            "position": {"x": "center", "y": "center", "offsetY": 120},
                            "animation": {"enter": "fade-in-up", "delay": 0.5},
                        },
                    ],
                    subtitle=scene.subtitle[:50] if scene.subtitle else "",
                )
                result = self.remotion_gen.generate_scene(scene_config, output_path)
            
            if result.success:
                scene.video_path = output_path
                console.print(f"  ✅ シーン{scene.index + 1}: {output_path} ({result.duration_seconds:.1f}秒)")
            else:
                console.print(f"  ❌ シーン{scene.index + 1}: {result.error_message}")
        
        return scenes
    
    def _get_emoji_for_scene(self, description: str) -> str:
        """シーン説明から適切な絵文字を選択"""
        emoji_map = {
            "猫": "🐱", "犬": "🐶", "動物": "🐾",
            "家": "🏠", "帰": "🏠",
            "車": "🚗", "旅": "🧳", "道": "🛣️",
            "海": "🌊", "山": "⛰️", "空": "☁️",
            "愛": "❤️", "心": "💕",
            "驚": "😱", "衝撃": "💥",
            "笑": "😂", "面白": "🤣",
            "泣": "😭", "感動": "🥹",
            "火": "🔥", "熱": "🔥",
            "走": "🏃", "歩": "🚶",
            "食": "🍽️", "料理": "👨‍🍳",
            "勝": "🏆", "優勝": "🥇",
            "発見": "🔍", "調査": "🔬",
        }
        
        for keyword, emoji in emoji_map.items():
            if keyword in description:
                return emoji
        
        return "📰"  # デフォルト
    
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
            
            output_path = str(self.dirs["videos"] / f"{output_prefix}_scene{scene.index + 1}.mp4")
            
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
        article_text: str,
        output_prefix: str,
        closing_text: str = "",
    ) -> tuple[str, float]:
        """記事全文からナレーション音声を生成（締めナレーション含む）
        
        Args:
            article_text: ナレーション用の記事テキスト
            output_prefix: 出力ファイル名プレフィックス
            closing_text: 締めナレーション（省略可）
        
        Returns:
            tuple: (audio_path, total_duration)
        """
        
        console.print("\n[cyan]🎤 ナレーション生成中...[/cyan]")
        
        # 記事全文をナレーションに使用
        full_text = article_text
        
        main_path = str(self.dirs["audio"] / f"{output_prefix}_narration.mp3")
        result = self.narration_gen.generate(text=full_text, output_path=main_path)
        
        if not result.success:
            console.print(f"  ❌ 音声生成失敗: {result.error_message}")
            return None, 0
        
        console.print(f"  ✅ 本編音声: {result.file_path} ({result.duration_seconds:.1f}秒)")
        
        # 締めナレーションがあれば追加
        if closing_text:
            console.print("  🎤 締めナレーション生成中...")
            closing_path = str(self.dirs["audio"] / f"{output_prefix}_closing.mp3")
            closing_result = self.narration_gen.generate(text=closing_text, output_path=closing_path)
            
            if closing_result.success:
                console.print(f"  ✅ 締め音声: {closing_result.file_path} ({closing_result.duration_seconds:.1f}秒)")
                
                # 音声を結合
                combined_path = str(self.dirs["audio"] / f"{output_prefix}_full.mp3")
                subprocess.run([
                    "ffmpeg", "-y",
                    "-i", main_path, "-i", closing_path,
                    "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[a]",
                    "-map", "[a]", combined_path
                ], capture_output=True)
                
                # 結合後の長さを取得
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", combined_path],
                    capture_output=True, text=True
                )
                total_duration = float(probe.stdout.strip())
                console.print(f"  ✅ 合計音声: {total_duration:.1f}秒")
                return combined_path, total_duration
        
        return result.file_path, result.duration_seconds
    
    def compose_final_video(
        self,
        scenes: list[Scene],
        audio_path: str,
        audio_duration: float,
        headline: str,
        sub_headline: str,
        output_prefix: str,
        is_breaking: bool = True,
    ) -> str:
        """全シーンを結合して最終動画を作成（音声長に合わせてスロー調整）"""
        
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
        size_parts = [p for p in probe.stdout.strip().split(',') if p]
        width, height = int(size_parts[0]), int(size_parts[1])
        
        # 一時ファイル用ディレクトリ
        temp_dir = self.dirs["temp"]
        
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
        
        # 2. 各シーンの長さを取得
        def get_duration(path):
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True
            )
            return float(probe.stdout.strip())
        
        video_durations = [get_duration(v) for v in overlaid_videos]
        total_video_duration = sum(video_durations)
        
        console.print(f"  動画合計: {total_video_duration:.1f}秒, 音声: {audio_duration:.1f}秒")
        
        # 3. 音声が長い場合、最後のシーンをスローにして調整
        if audio_duration > total_video_duration:
            other_scenes_duration = sum(video_durations[:-1])
            needed_last_scene = audio_duration - other_scenes_duration + 0.3
            slowdown_factor = needed_last_scene / video_durations[-1]
            
            console.print(f"  最後のシーンを {slowdown_factor:.2f}x スローに調整")
            
            # 最後のシーンをスロー化
            last_scene_slow = str(temp_dir / "last_scene_slow.mp4")
            subprocess.run([
                "ffmpeg", "-y", "-i", overlaid_videos[-1],
                "-filter:v", f"setpts={slowdown_factor}*PTS",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-an", last_scene_slow
            ], capture_output=True)
            overlaid_videos[-1] = last_scene_slow
        
        # 4. 動画を結合（filter_complex方式）
        inputs = []
        for v in overlaid_videos:
            inputs.extend(["-i", v])
        
        n = len(overlaid_videos)
        filter_str = "".join([f"[{i}:v]" for i in range(n)]) + f"concat=n={n}:v=1:a=0[v]"
        
        concat_video_path = str(temp_dir / "concat.mp4")
        cmd = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", filter_str,
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            concat_video_path
        ]
        subprocess.run(cmd, capture_output=True)
        console.print("  ✅ 動画結合完了")
        
        # 5. 音声を追加
        final_path = str(self.dirs["final"] / f"{output_prefix}_final.mp4")
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
        headline: str,
        sub_headline: str = "",
        scenes_data: list[dict] = None,
        closing_text: str = "",
        hook: str = "",  # フック（冒頭の引き）
        keywords: list[str] = None,  # 強調キーワード
        visual_style: str = "",  # 映像スタイル
        article_text: str = "",  # 後方互換用
        output_prefix: Optional[str] = None,
        is_breaking: bool = True,
        existing_images: list[str] = None,  # 既存画像パス
    ) -> NewsVideoResult:
        """パイプライン全体を実行
        
        Args:
            headline: ヘッドライン
            sub_headline: サブヘッドライン
            scenes_data: シーン構成データ（新形式）
            closing_text: 締めナレーション（省略可）
            hook: 冒頭のフック（視聴者を引き込むフレーズ）
            keywords: 強調したいキーワードリスト
            visual_style: 映像全体のスタイル（例: 温かみのある家族写真風）
            article_text: 記事本文（後方互換用、scenes_dataがない場合に使用）
            output_prefix: 出力ファイル名プレフィックス
            is_breaking: BREAKING NEWSバナー表示
        """
        
        if output_prefix is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_prefix = f"news_{timestamp}"
        
        console.print("\n" + "=" * 50)
        console.print(f"[bold]📰 ニュース動画生成: {headline[:30]}...[/bold]")
        console.print("=" * 50)
        
        try:
            # シーン構成データがある場合は新フロー
            if scenes_data and len(scenes_data) > 0:
                return self._run_with_scene_sync(
                    headline=headline,
                    sub_headline=sub_headline,
                    scenes_data=scenes_data,
                    closing_text=closing_text,
                    hook=hook,
                    keywords=keywords or [],
                    visual_style=visual_style,
                    output_prefix=output_prefix,
                    is_breaking=is_breaking,
                    existing_images=existing_images,
                )
            
            # 後方互換: 従来のフロー（article_textから分析）
            if not article_text:
                return NewsVideoResult(
                    success=False,
                    error_message="scenes_data または article_text が必要です",
                )
            
            # 1. 記事分析
            scenes = self.analyze_article(article_text, headline)
            
            # 2. 画像生成
            scenes = self.generate_scene_images(scenes, output_prefix)
            
            # 3. 動画生成
            scenes = self.generate_scene_videos(scenes, output_prefix)
            
            # 4. ナレーション生成（記事全文を使用）
            audio_path, audio_duration = self.generate_narration(
                article_text, output_prefix, closing_text=closing_text
            )
            
            # 5. 最終合成（音声長に合わせてスロー調整）
            final_path = self.compose_final_video(
                scenes=scenes,
                audio_path=audio_path,
                audio_duration=audio_duration,
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
    
    def _run_with_scene_sync(
        self,
        headline: str,
        sub_headline: str,
        scenes_data: list[dict],
        closing_text: str,
        hook: str,
        keywords: list[str],
        visual_style: str,
        output_prefix: str,
        is_breaking: bool,
        mood: str = "exciting",
        existing_images: list[str] = None,
    ) -> NewsVideoResult:
        """シーン同期フロー: 各シーンのナレーションと映像を同期させる"""
        
        console.print(f"\n[cyan]🎬 シーン同期モード ({len(scenes_data)}シーン)[/cyan]")
        console.print(f"[cyan]💰 モード: {'Remotion (無料)' if self.use_remotion else 'Luma (有料)'}[/cyan]")
        if hook:
            console.print(f"[yellow]🎣 フック: {hook}[/yellow]")
        if visual_style:
            console.print(f"[magenta]🎨 スタイル: {visual_style}[/magenta]")
        
        # 1. scenes_dataからSceneオブジェクトを作成
        scenes = []
        for i, sd in enumerate(scenes_data):
            # visual_descriptionから画像プロンプトを生成（visual_styleを統一適用）
            visual_desc = sd.get("visual_description", sd.get("title", ""))
            image_prompt = self._create_image_prompt(visual_desc, headline, visual_style)
            
            scene = Scene(
                index=i,
                description=visual_desc,
                image_prompt=image_prompt,
                video_prompt=f"Slow cinematic camera movement, {visual_desc}",
                subtitle=sd.get("narration", "")[:30],  # 字幕は短く
            )
            # ナレーションテキストと強調ワードを保持
            scene.narration_text = sd.get("narration", "")
            scene.emphasis_word = sd.get("emphasis_word", "")
            scenes.append(scene)
            console.print(f"  シーン{i+1}: {visual_desc[:40]}...")
        
        # 2. 動画生成（Remotion or Luma）
        if self.use_remotion:
            # Remotion: 先にナレーションを生成して、その長さに合わせる
            console.print("\n[cyan]🎤 シーン別ナレーション生成中（先に音声）...[/cyan]")
            for scene in scenes:
                narration_text = getattr(scene, 'narration_text', scene.subtitle)
                if narration_text:
                    audio_path = str(self.dirs["audio"] / f"{output_prefix}_scene{scene.index + 1}.mp3")
                    result = self.narration_gen.generate(text=narration_text, output_path=audio_path)
                    if result.success:
                        scene.audio_path = audio_path
                        scene.audio_duration = result.duration_seconds
                        console.print(f"  ✅ シーン{scene.index + 1}: {result.duration_seconds:.1f}秒")
            
            # 画像生成（ニュース風の背景用）または既存画像を使用
            if existing_images and len(existing_images) >= len(scenes):
                console.print("\n[cyan]🖼️ 既存画像を使用...[/cyan]")
                for i, scene in enumerate(scenes):
                    scene.image_path = str(Path(existing_images[i]).resolve())
                    console.print(f"  ✅ シーン{i+1}: {existing_images[i]}")
            else:
                console.print("\n[cyan]🖼️ 背景画像を生成中 (Flux)...[/cyan]")
                scenes = self.generate_scene_images(scenes, output_prefix)
            
            # Remotion で動画生成（背景画像 + ニュースオーバーレイ）
            scenes = self.generate_scene_videos_remotion(
                scenes, output_prefix,
                headline=headline,
                sub_headline=sub_headline,
                is_breaking=is_breaking,
                news_style=True,
                mood=mood,
            )
        else:
            # Luma: 画像生成 → 動画生成（有料）
            scenes = self.generate_scene_images(scenes, output_prefix)
            scenes = self.generate_scene_videos(scenes, output_prefix)
        
        # 4. シーンごとにナレーション生成（Remotionの場合は既に生成済み）
        scene_audios = []
        total_audio_duration = 0
        
        if self.use_remotion:
            # Remotion: 既に生成済みなので集計のみ
            for scene in scenes:
                if hasattr(scene, 'audio_path') and scene.audio_path:
                    scene_audios.append(scene.audio_path)
                    total_audio_duration += getattr(scene, 'audio_duration', 0)
        else:
            # Luma: ここでナレーション生成
            console.print("\n[cyan]🎤 シーン別ナレーション生成中...[/cyan]")
            for scene in scenes:
                narration_text = getattr(scene, 'narration_text', scene.subtitle)
                if not narration_text:
                    continue
                    
                audio_path = str(self.dirs["audio"] / f"{output_prefix}_scene{scene.index + 1}.mp3")
                result = self.narration_gen.generate(text=narration_text, output_path=audio_path)
                
                if result.success:
                    scene.audio_path = audio_path
                    scene.audio_duration = result.duration_seconds
                    total_audio_duration += result.duration_seconds
                    scene_audios.append(audio_path)
                    console.print(f"  ✅ シーン{scene.index + 1}: {result.duration_seconds:.1f}秒")
                else:
                    console.print(f"  ❌ シーン{scene.index + 1}: 音声生成失敗")
        
        # 5. 締めナレーション
        if closing_text:
            closing_path = str(self.dirs["audio"] / f"{output_prefix}_closing.mp3")
            closing_result = self.narration_gen.generate(text=closing_text, output_path=closing_path)
            if closing_result.success:
                scene_audios.append(closing_path)
                total_audio_duration += closing_result.duration_seconds
                console.print(f"  ✅ 締め: {closing_result.duration_seconds:.1f}秒")
        
        # 6. 全音声を結合
        console.print("\n[cyan]🔊 音声結合中...[/cyan]")
        combined_audio = str(self.dirs["audio"] / f"{output_prefix}_combined.mp3")
        
        if len(scene_audios) > 1:
            # ffmpegで結合
            concat_list = str(self.dirs["temp"] / "audio_concat.txt")
            with open(concat_list, "w") as f:
                for ap in scene_audios:
                    f.write(f"file '{ap}'\n")
            
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list, "-c", "copy", combined_audio
            ], capture_output=True)
        else:
            combined_audio = scene_audios[0] if scene_audios else None
        
        console.print(f"  ✅ 合計音声: {total_audio_duration:.1f}秒")
        
        # 6.5. BGMミックス
        final_audio = combined_audio
        if combined_audio:
            # ナレーションテキストからムードを検出
            all_narration = " ".join([getattr(s, 'narration_text', '') for s in scenes])
            mood = self.bgm_manager.detect_mood(headline, all_narration)
            bgm_track = self.bgm_manager.get_bgm(mood)
            
            if bgm_track and bgm_track.exists():
                console.print(f"\n[cyan]🎵 BGMミックス中... ({mood.value})[/cyan]")
                mixed_audio = str(self.dirs["audio"] / f"{output_prefix}_mixed.mp3")
                
                if self.bgm_manager.mix_audio(
                    narration_path=combined_audio,
                    bgm_path=bgm_track.path,
                    output_path=mixed_audio,
                    narration_volume=1.0,
                    bgm_volume=0.18,  # BGMは控えめだが聞こえる程度
                ):
                    final_audio = mixed_audio
                    console.print(f"  ✅ BGM追加: {bgm_track.name}")
                else:
                    console.print(f"  ⚠️ BGMミックス失敗、ナレーションのみ使用")
            else:
                console.print(f"  ℹ️ BGMなし（{mood.value}用BGM未設定）")
        
        # 7. 最終合成（シーンごとに音声長に合わせる）
        # Remotion + 画像生成の場合はオーバーレイをスキップ（Remotion で既に含まれている）
        skip_overlay = self.use_remotion and any(s.image_path for s in scenes)
        
        final_path = self._compose_scene_synced_video(
            scenes=scenes,
            combined_audio=final_audio,  # BGMミックス済み音声
            total_audio_duration=total_audio_duration,
            headline=headline,
            sub_headline=sub_headline,
            output_prefix=output_prefix,
            is_breaking=is_breaking,
            skip_overlay=skip_overlay,
        )
        
        # 動画の長さを取得
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", final_path],
            capture_output=True, text=True
        )
        duration = float(probe.stdout.strip()) if probe.stdout.strip() else total_audio_duration
        
        return NewsVideoResult(
            success=True,
            video_path=final_path,
            scenes=scenes,
            audio_path=combined_audio,
            duration_seconds=duration,
        )
    
    def _create_image_prompt(self, visual_desc: str, headline: str, visual_style: str = "") -> str:
        """visual_descriptionから画像プロンプトを生成（スタイル統一）"""
        base = "Photorealistic, cinematic lighting, 4K quality, high detail"
        
        # visual_styleがあれば追加
        if visual_style:
            style_map = {
                "温かみ": "warm color palette, soft lighting, heartwarming atmosphere",
                "家族": "family-friendly, warm tones, emotional",
                "ドキュメンタリー": "documentary style, natural lighting, realistic",
                "コミカル": "playful, bright colors, whimsical",
                "感動": "emotional, touching, cinematic, dramatic lighting",
                "驚き": "dramatic, impactful, vivid colors",
            }
            # スタイルキーワードをマッチング
            style_addition = ""
            for key, value in style_map.items():
                if key in visual_style:
                    style_addition = value
                    break
            if not style_addition:
                style_addition = visual_style  # そのまま使用
            
            return f"{base}, {style_addition}, {visual_desc}"
        
        return f"{base}, {visual_desc}"
    
    def _compose_scene_synced_video(
        self,
        scenes: list[Scene],
        combined_audio: str,
        total_audio_duration: float,
        headline: str,
        sub_headline: str,
        output_prefix: str,
        is_breaking: bool,
        skip_overlay: bool = False,
    ) -> str:
        """シーン同期で最終動画を合成
        
        Args:
            skip_overlay: True の場合、オーバーレイを追加しない（Remotion ニュース風の場合）
        """
        
        console.print("\n[cyan]🎬 シーン同期合成中...[/cyan]")
        
        valid_scenes = [s for s in scenes if s.video_path]
        if not valid_scenes:
            raise ValueError("有効なシーン動画がありません")
        
        # 各シーンの目標時間を計算
        num_scenes = len(valid_scenes)
        base_duration_per_scene = total_audio_duration / num_scenes
        
        console.print(f"  シーン数: {num_scenes}, 各シーン目標: {base_duration_per_scene:.1f}秒")
        
        # 動画サイズを取得
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0",
             valid_scenes[0].video_path],
            capture_output=True, text=True
        )
        size_parts = [p for p in probe.stdout.strip().split(',') if p]
        width, height = int(size_parts[0]), int(size_parts[1])
        
        temp_dir = self.dirs["temp"]
        
        # 各シーンを目標時間に調整してオーバーレイ追加
        adjusted_videos = []
        
        for i, scene in enumerate(valid_scenes):
            # シーン別の音声があれば、その長さに合わせる
            target_duration = getattr(scene, 'audio_duration', base_duration_per_scene)
            
            # 動画の実際の長さを取得
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", scene.video_path],
                capture_output=True, text=True
            )
            actual_duration = float(probe.stdout.strip())
            
            # スロー率を計算（最大2倍まで）
            slowdown = min(target_duration / actual_duration, 2.0)
            
            adjusted_path = str(temp_dir / f"adjusted_{i}.mp4")
            
            if skip_overlay:
                # オーバーレイなし（Remotion ニュース風の場合は既に含まれている）
                filter_complex = f"setpts={slowdown}*PTS"
                subprocess.run([
                    "ffmpeg", "-y",
                    "-i", scene.video_path,
                    "-vf", filter_complex,
                    "-t", str(target_duration),
                    "-c:v", "libx264", "-preset", "fast",
                    "-an",
                    adjusted_path
                ], capture_output=True)
            else:
                # オーバーレイ作成（最初のシーンのみヘッドライン表示）
                overlay_path = str(temp_dir / f"overlay_{i}.png")
                self.compositor.create_transparent_overlay(
                    width=width,
                    height=height,
                    headline=headline if i == 0 else "",
                    sub_headline=sub_headline if i == 0 else "",
                    is_breaking=is_breaking and i == 0,
                    output_path=overlay_path,
                    style="gradient",
                )
                
                # 動画調整（スロー + オーバーレイ）
                filter_complex = f"[0:v]setpts={slowdown}*PTS[slowed];[slowed][1:v]overlay=0:0"
                subprocess.run([
                    "ffmpeg", "-y",
                    "-i", scene.video_path,
                    "-i", overlay_path,
                    "-filter_complex", filter_complex,
                    "-t", str(target_duration),
                    "-c:v", "libx264", "-preset", "fast",
                    "-an",
                    adjusted_path
                ], capture_output=True)
            
            adjusted_videos.append(adjusted_path)
            console.print(f"  ✅ シーン{i+1}: {actual_duration:.1f}秒 → {target_duration:.1f}秒 (x{slowdown:.2f})")
        
        # イントロ動画を生成
        console.print("\n[cyan]🎬 イントロ生成中...[/cyan]")
        intro_path = str(temp_dir / "intro.mp4")
        self.intro_outro_gen.generate_intro_video(intro_path, temp_dir)
        console.print(f"  ✅ イントロ: 3秒")
        
        # アウトロ動画を生成
        console.print("[cyan]🎬 アウトロ生成中...[/cyan]")
        outro_path = str(temp_dir / "outro.mp4")
        self.intro_outro_gen.generate_outro_video(outro_path, temp_dir)
        console.print(f"  ✅ アウトロ: 4秒")
        
        # 動画を結合（イントロ + メイン + アウトロ）
        console.print("\n[cyan]🎬 全体結合中...[/cyan]")
        concat_list = str(temp_dir / "video_concat.txt")
        with open(concat_list, "w") as f:
            # イントロ
            if Path(intro_path).exists():
                f.write(f"file '{intro_path}'\n")
            # メインシーン
            for vp in adjusted_videos:
                f.write(f"file '{vp}'\n")
            # アウトロ
            if Path(outro_path).exists():
                f.write(f"file '{outro_path}'\n")
        
        concat_video = str(temp_dir / f"{output_prefix}_concat.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list, "-c", "copy", concat_video
        ], capture_output=True)
        
        # 音声を追加（イントロ分は無音パディング）
        final_path = str(self.dirs["final"] / f"{output_prefix}_final.mp4")
        
        if combined_audio:
            # イントロ分の無音(3秒)を音声の前にパディング
            padded_audio = str(temp_dir / f"{output_prefix}_padded.mp3")
            pad_result = subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-t", "3", "-i", "anullsrc=r=44100:cl=stereo",  # 3秒無音
                "-i", combined_audio,
                "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]",
                "-map", "[out]",
                "-c:a", "libmp3lame", "-b:a", "192k",
                padded_audio
            ], capture_output=True, text=True)
            
            if pad_result.returncode != 0:
                console.print(f"[yellow]⚠️ 無音パディング失敗、元の音声を使用[/yellow]")
                padded_audio = combined_audio
            
            # パディング済み音声を動画と合成
            result = subprocess.run([
                "ffmpeg", "-y",
                "-i", concat_video,
                "-i", padded_audio,
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                final_path
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                console.print(f"[red]⚠️ 音声追加エラー: {result.stderr[:200]}[/red]")
        else:
            subprocess.run(["cp", concat_video, final_path])
        
        console.print(f"\n[green]🎉 完成: {final_path}[/green]")
        
        return final_path


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
