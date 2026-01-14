"""コンテンツ企画モジュール - Gemini APIでコンセプト生成"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from google import genai
from google.genai import types

from ..config import config
from ..logger import setup_logger

logger = setup_logger("content_planner")


@dataclass
class Scene:
    """シーン情報"""
    number: int
    title: str
    image_prompt: str
    video_prompt: str
    duration: int = 5
    transition: str = "fade"
    image_path: Optional[str] = None
    video_path: Optional[str] = None
    reference_image: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "title": self.title,
            "image_prompt": self.image_prompt,
            "video_prompt": self.video_prompt,
            "duration": self.duration,
            "transition": self.transition,
            "image_path": self.image_path,
            "video_path": self.video_path,
            "reference_image": self.reference_image,
        }


@dataclass
class VideoProject:
    """動画プロジェクト"""
    title: str
    description: str
    theme: str
    style: str
    scenes: list[Scene] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def total_duration(self) -> int:
        return sum(s.duration for s in self.scenes)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "theme": self.theme,
            "style": self.style,
            "tags": self.tags,
            "total_duration": self.total_duration,
            "scenes": [s.to_dict() for s in self.scenes],
        }

    def save(self, path: str):
        """プロジェクトをJSONで保存"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Project saved: {path}")

    @classmethod
    def load(cls, path: str) -> "VideoProject":
        """JSONからプロジェクトを読み込み"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        scenes = [Scene(**s) for s in data.get("scenes", [])]
        return cls(
            title=data["title"],
            description=data["description"],
            theme=data["theme"],
            style=data["style"],
            scenes=scenes,
            tags=data.get("tags", []),
        )


class ContentPlanner:
    """Gemini APIを使用したコンテンツ企画"""

    THEMES = [
        "サイバーパンク都市",
        "ファンタジー風景",
        "未来宇宙",
        "自然の神秘",
        "和風モダン",
        "レトロフューチャー",
    ]

    STYLES = [
        "cinematic",
        "anime",
        "photorealistic",
        "artistic",
        "minimalist",
        "surreal",
    ]

    def __init__(self):
        if not config.gemini.api_key:
            raise ValueError("GEMINI_API_KEY is not set")

        # Google Genai クライアント (新API)
        self.client = genai.Client(api_key=config.gemini.api_key)
        self.model_name = config.gemini.model_text
        logger.info(f"ContentPlanner initialized with {self.model_name}")

    def generate_project(
        self,
        theme: str,
        style: str = "cinematic",
        scene_count: int = 3,
    ) -> VideoProject:
        """動画プロジェクトを生成"""
        logger.info(f"Generating project: theme={theme}, style={style}, scenes={scene_count}")

        prompt = self._build_prompt(theme, style, scene_count)

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=config.gemini.temperature,
                    max_output_tokens=config.gemini.max_tokens,
                ),
            )
            return self._parse_response(response.text, theme, style)

        except Exception as e:
            logger.error(f"Failed to generate project: {e}")
            raise

    def _build_prompt(self, theme: str, style: str, scene_count: int) -> str:
        """プロンプト構築"""
        return f"""あなたはAI動画制作のプロフェッショナルです。
以下の条件で、魅力的な動画コンセプトを生成してください。

テーマ: {theme}
スタイル: {style}
シーン数: {scene_count}

以下のJSON形式で出力してください（コードブロックで囲む）:
```json
{{
    "title": "動画タイトル（日本語、キャッチー）",
    "description": "YouTube用説明文（100-200文字）",
    "tags": ["タグ1", "タグ2", "タグ3", "タグ4", "タグ5"],
    "scenes": [
        {{
            "number": 1,
            "title": "シーン1のタイトル",
            "image_prompt": "FLUX/Gemini用の詳細な画像生成プロンプト（英語、100-150語）。構図、ライティング、スタイル、品質指定を含む。",
            "video_prompt": "KLING用の動画生成プロンプト（英語、50-75語）。カメラワーク、被写体の動き、雰囲気の変化を含む。",
            "duration": 5,
            "transition": "fade"
        }}
    ]
}}
```

要件:
1. image_promptは高品質画像のため詳細に（8K, cinematic, highly detailed等）
2. video_promptは動きとカメラワークを明確に指示
3. 各シーンは視覚的連続性を持つ
4. transitionは "fade", "dissolve", "wipe" から選択
5. durationは5または10秒
6. 全体でストーリー性のある構成に"""

    def _parse_response(self, text: str, theme: str, style: str) -> VideoProject:
        """レスポンス解析"""
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)

        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = text

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            raise ValueError(f"Invalid JSON response: {e}")

        scenes = []
        for s in data.get("scenes", []):
            scenes.append(Scene(
                number=s.get("number", len(scenes) + 1),
                title=s.get("title", f"Scene {len(scenes) + 1}"),
                image_prompt=s.get("image_prompt", ""),
                video_prompt=s.get("video_prompt", ""),
                duration=s.get("duration", 5),
                transition=s.get("transition", "fade"),
            ))

        project = VideoProject(
            title=data.get("title", f"{theme} - {style}"),
            description=data.get("description", ""),
            theme=theme,
            style=style,
            scenes=scenes,
            tags=data.get("tags", []),
        )

        logger.info(f"Generated project: {project.title} ({len(scenes)} scenes)")
        return project

    def enhance_prompt(self, base_prompt: str, style: str) -> str:
        """プロンプトを強化"""
        enhance_request = f"""Enhance this image generation prompt for higher quality output.
Add technical specifications and style details.

Base prompt: {base_prompt}
Style: {style}

Output only the enhanced prompt (no explanation), under 150 words.
Include: lighting, composition, color palette, technical quality terms."""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=enhance_request,
            )
            return response.text.strip()
        except Exception as e:
            logger.warning(f"Failed to enhance prompt: {e}")
            return base_prompt


def create_sample_project() -> VideoProject:
    """サンプルプロジェクト作成（API不要）"""
    scenes = [
        Scene(
            number=1,
            title="ネオンの雨",
            image_prompt="Cyberpunk city street at night, heavy rain, neon signs reflecting on wet asphalt, towering skyscrapers with holographic advertisements, diverse crowd with umbrellas, atmospheric fog, cinematic wide shot, 8K ultra detailed, photorealistic, blade runner aesthetic",
            video_prompt="Slow aerial descent through rain into cyberpunk city, camera panning across neon-lit streets, rain droplets visible, holographic ads flickering, atmospheric and moody, smooth dolly movement",
            duration=5,
            transition="fade",
        ),
        Scene(
            number=2,
            title="謎の人物",
            image_prompt="Mysterious hooded figure standing on rooftop overlooking cyberpunk cityscape, back to camera, dramatic silhouette against holographic billboards, rain-soaked coat, moody lighting, cinematic composition, 8K, photorealistic, atmospheric",
            video_prompt="Camera slowly rotating around the figure, coat billowing in wind, city lights blinking below, gradual zoom towards the cityscape, cinematic and dramatic atmosphere",
            duration=5,
            transition="dissolve",
        ),
        Scene(
            number=3,
            title="地下マーケット",
            image_prompt="Underground cyberpunk market, crowded with humans and androids, neon signs in multiple languages, steam rising from food stalls, cables and pipes overhead, vibrant colors, detailed textures, street-level perspective, 8K cinematic",
            video_prompt="Tracking shot through crowded market, following movement of diverse characters, steam rising, neon lights flickering, immersive POV, gradual reveal of market depth",
            duration=5,
            transition="wipe",
        ),
    ]

    return VideoProject(
        title="ネオン・レイン - サイバーパンクの夜",
        description="雨に濡れたネオンの街を舞台に、近未来の都市生活を描くAI生成ショートフィルム。サイバーパンクの世界観を体験してください。",
        theme="サイバーパンク都市",
        style="cinematic",
        scenes=scenes,
        tags=["サイバーパンク", "AI生成", "ショートフィルム", "ネオン", "未来都市"],
    )


if __name__ == "__main__":
    # テスト実行
    try:
        planner = ContentPlanner()
        project = planner.generate_project("サイバーパンク都市", "cinematic", 3)
        print(json.dumps(project.to_dict(), indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"API error: {e}")
        print("\nUsing sample project:")
        sample = create_sample_project()
        print(json.dumps(sample.to_dict(), indent=2, ensure_ascii=False))
