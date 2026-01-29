"""Remotion を使ったモーショングラフィックス動画生成"""

import subprocess
import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from ..logger import setup_logger

logger = setup_logger("remotion_generator")

# Remotion プロジェクトのパス
REMOTION_DIR = Path(__file__).parent.parent / "remotion"


@dataclass
class RemotionResult:
    """Remotion 生成結果"""
    success: bool
    video_path: Optional[str] = None
    duration_seconds: float = 0.0
    error_message: Optional[str] = None


@dataclass
class SceneConfig:
    """シーン設定"""
    scene_number: int
    duration: float
    background_colors: list[str] = None
    elements: list[dict] = None
    subtitle: str = ""
    overlay_path: Optional[str] = None
    # 背景画像（ニュース風）
    background_image: Optional[str] = None
    # ニュースオーバーレイ設定
    news_overlay: Optional[dict] = None  # {headline, subHeadline, channelName, isBreaking, showOverlay}
    # アニメーション進捗範囲（0-1）。同じ画像グループで継続的なアニメーションを実現
    animation_start: float = 0.0
    animation_end: float = 1.0


class RemotionGenerator:
    """Remotion を使った動画生成"""
    
    def __init__(self):
        self.remotion_dir = REMOTION_DIR
        self._ensure_dependencies()
    
    def _ensure_dependencies(self):
        """node_modules が存在するか確認"""
        node_modules = self.remotion_dir / "node_modules"
        if not node_modules.exists():
            logger.info("Installing Remotion dependencies...")
            subprocess.run(
                ["npm", "install"],
                cwd=self.remotion_dir,
                capture_output=True
            )
    
    def generate_scene(
        self,
        scene: SceneConfig,
        output_path: str,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
    ) -> RemotionResult:
        """シーン動画を生成
        
        Args:
            scene: シーン設定
            output_path: 出力パス
            width: 動画幅
            height: 動画高さ
            fps: フレームレート
        
        Returns:
            RemotionResult
        """
        try:
            # 背景タイプを決定
            if scene.background_image:
                background = {
                    "type": "image",
                    "imagePath": scene.background_image,
                }
            else:
                background = {
                    "type": "gradient",
                    "colors": scene.background_colors or ["#667eea", "#764ba2"],
                }
            
            # シーンデータをJSON化
            scene_data = {
                "sceneNumber": scene.scene_number,
                "duration": scene.duration,
                "animationStart": scene.animation_start,
                "animationEnd": scene.animation_end,
                "background": background,
                "elements": scene.elements or [],
                "overlayPath": scene.overlay_path,
                "narration": {
                    "subtitle": scene.subtitle,
                },
            }
            
            # ニュースオーバーレイ設定があれば追加
            if scene.news_overlay:
                scene_data["newsOverlay"] = scene.news_overlay
            
            # 一時ファイルにシーンデータを書き込み
            props_file = self.remotion_dir / "scene_props.json"
            with open(props_file, "w") as f:
                json.dump({
                    "scene": scene_data,
                    "width": width,
                    "height": height,
                }, f, ensure_ascii=False)
            
            # 背景画像がある場合、public ディレクトリにコピー
            public_dir = self.remotion_dir / "public"
            public_dir.mkdir(exist_ok=True)
            
            if scene.background_image:
                import shutil
                src_path = Path(scene.background_image)
                if src_path.exists():
                    # 画像を public にコピー
                    dest_name = f"bg_{scene.scene_number}{src_path.suffix}"
                    dest_path = public_dir / dest_name
                    shutil.copy2(src_path, dest_path)
                    # scene_data の imagePath を更新
                    scene_data["background"]["imagePath"] = dest_name
                    logger.info(f"Copied image to public: {dest_name}")
            
            # props ファイルを再書き込み（更新された imagePath を含む）
            with open(props_file, "w") as f:
                json.dump({
                    "scene": scene_data,
                    "width": width,
                    "height": height,
                }, f, ensure_ascii=False)
            
            # Remotion でレンダリング（durationはpropsから自動計算）
            cmd = [
                "npx", "remotion", "render",
                "NewsScene",
                output_path,
                "--props", str(props_file),
            ]
            
            logger.info(f"Rendering scene {scene.scene_number}...")
            result = subprocess.run(
                cmd,
                cwd=self.remotion_dir,
                capture_output=True,
                text=True,
            )
            
            if result.returncode != 0:
                logger.error(f"Remotion render failed: {result.stderr}")
                return RemotionResult(
                    success=False,
                    error_message=result.stderr,
                )
            
            logger.info(f"Scene {scene.scene_number} rendered: {output_path}")
            
            return RemotionResult(
                success=True,
                video_path=output_path,
                duration_seconds=scene.duration,
            )
            
        except Exception as e:
            logger.error(f"Remotion generation error: {e}")
            return RemotionResult(
                success=False,
                error_message=str(e),
            )
    
    def generate_motion_graphics_scene(
        self,
        visual_description: str,
        narration_text: str,
        scene_number: int,
        duration: float,
        output_path: str,
        mood: str = "exciting",
    ) -> RemotionResult:
        """記事の内容からモーショングラフィックスを生成
        
        Args:
            visual_description: シーンの視覚的説明
            narration_text: ナレーションテキスト
            scene_number: シーン番号
            duration: シーン秒数
            output_path: 出力パス
            mood: ムード (exciting, heartwarming, funny, etc.)
        
        Returns:
            RemotionResult
        """
        # ムードに基づいて色を選択
        mood_colors = {
            "exciting": ["#FF6B6B", "#FF8E53"],
            "heartwarming": ["#A8E6CF", "#DCEDC1"],
            "funny": ["#FFE66D", "#FFB347"],
            "shocking": ["#E94560", "#1A1A2E"],
            "informative": ["#4ECDC4", "#44A08D"],
        }
        
        colors = mood_colors.get(mood, mood_colors["exciting"])
        
        # シンプルな要素構成
        elements = [
            {
                "type": "emoji",
                "content": self._get_emoji_for_description(visual_description),
                "style": {"size": "xxl"},
                "position": {"x": "center", "y": "center", "offsetY": -100},
                "animation": {"enter": "bounce-in", "delay": 0},
            },
            {
                "type": "text",
                "content": narration_text[:30] + "..." if len(narration_text) > 30 else narration_text,
                "style": {"size": "lg", "weight": "bold", "color": "#FFFFFF"},
                "position": {"x": "center", "y": "center", "offsetY": 100},
                "animation": {"enter": "fade-in-up", "delay": 0.5},
            },
        ]
        
        scene = SceneConfig(
            scene_number=scene_number,
            duration=duration,
            background_colors=colors,
            elements=elements,
            subtitle=narration_text[:50],
        )
        
        return self.generate_scene(scene, output_path)
    
    def generate_news_scene(
        self,
        scene_number: int,
        duration: float,
        output_path: str,
        background_image: str,
        subtitle: str = "",
        headline: str = "",
        sub_headline: str = "",
        channel_name: str = "FJ News 24",
        is_breaking: bool = True,
        show_overlay: bool = True,
        animation_start: float = 0.0,
        animation_end: float = 1.0,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
    ) -> RemotionResult:
        """ニュース風シーンを生成（背景画像 + ニュースオーバーレイ）
        
        Args:
            scene_number: シーン番号
            duration: シーン秒数
            output_path: 出力パス
            background_image: 背景画像パス（絶対パス）
            subtitle: 字幕テキスト
            headline: ヘッドライン（最初のシーンのみ表示推奨）
            sub_headline: サブヘッドライン
            channel_name: チャンネル名
            is_breaking: BREAKING NEWS 表示
            show_overlay: オーバーレイ全体を表示
        
        Returns:
            RemotionResult
        """
        scene = SceneConfig(
            scene_number=scene_number,
            duration=duration,
            background_image=background_image,
            subtitle=subtitle,
            animation_start=animation_start,
            animation_end=animation_end,
            news_overlay={
                "channelName": channel_name,
                "headline": headline,
                "subHeadline": sub_headline,
                "isBreaking": is_breaking,
                "showOverlay": show_overlay,
            },
        )
        
        return self.generate_scene(scene, output_path, width, height, fps)
    
    def _get_emoji_for_description(self, description: str) -> str:
        """説明文から適切な絵文字を選択"""
        emoji_map = {
            "猫": "🐱",
            "犬": "🐶",
            "家": "🏠",
            "車": "🚗",
            "飛行機": "✈️",
            "海": "🌊",
            "山": "⛰️",
            "火": "🔥",
            "愛": "❤️",
            "驚": "😱",
            "笑": "😂",
            "泣": "😭",
            "旅": "🧳",
            "走": "🏃",
            "歩": "🚶",
        }
        
        for keyword, emoji in emoji_map.items():
            if keyword in description:
                return emoji
        
        return "📰"  # デフォルト


# 簡単なテスト
if __name__ == "__main__":
    generator = RemotionGenerator()
    
    scene = SceneConfig(
        scene_number=1,
        duration=5.0,
        background_colors=["#FF6B6B", "#FF8E53"],
        elements=[
            {
                "type": "emoji",
                "content": "🐱",
                "style": {"size": "xxl"},
                "position": {"x": "center", "y": "center", "offsetY": -100},
                "animation": {"enter": "bounce-in", "delay": 0},
            },
            {
                "type": "text",
                "content": "テスト動画",
                "style": {"size": "xl", "weight": "bold", "color": "#FFFFFF"},
                "position": {"x": "center", "y": "center", "offsetY": 100},
                "animation": {"enter": "fade-in-up", "delay": 0.5},
            },
        ],
        subtitle="これはテストです",
    )
    
    result = generator.generate_scene(scene, "test_output.mp4")
    print(f"Result: {result}")
