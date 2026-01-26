"""ニュースコンテンツ企画モジュール - ニュース記事から動画企画を生成"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional, List

from google import genai
from google.genai import types

from ..config import config
from ..logger import setup_logger

logger = setup_logger("news_content_planner")


@dataclass
class NewsScene:
    """ニュース動画のシーン"""
    number: int
    scene_type: str  # "hook", "main", "detail", "conclusion"
    narration: str  # このシーンのナレーション
    image_prompt: str  # Flux Pro用の画像プロンプト
    duration: int = 5
    
    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "scene_type": self.scene_type,
            "narration": self.narration,
            "image_prompt": self.image_prompt,
            "duration": self.duration,
        }


@dataclass
class NewsVideoProject:
    """ニュース動画プロジェクト"""
    original_title: str
    original_content: str
    rewritten_title: str
    hook: str
    scenes: List[NewsScene] = field(default_factory=list)
    key_points: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    @property
    def full_narration(self) -> str:
        """全シーンのナレーションを結合"""
        parts = [self.hook]
        parts.extend(scene.narration for scene in self.scenes)
        return "\n".join(parts)
    
    @property
    def total_duration(self) -> int:
        return sum(scene.duration for scene in self.scenes)
    
    @property
    def image_prompts(self) -> List[str]:
        return [scene.image_prompt for scene in self.scenes]
    
    def to_dict(self) -> dict:
        return {
            "original_title": self.original_title,
            "rewritten_title": self.rewritten_title,
            "hook": self.hook,
            "scenes": [s.to_dict() for s in self.scenes],
            "key_points": self.key_points,
            "tags": self.tags,
            "total_duration": self.total_duration,
        }


class NewsContentPlanner:
    """ニュース記事から動画企画を生成"""
    
    SYSTEM_PROMPT = """あなたはニュース動画制作のプロフェッショナルです。
ニュース記事を、若者向けの短尺動画コンテンツに変換してください。

【出力要件】
1. 視聴者を引き込むフック（冒頭の一文）
2. 3-4シーンの構成（各シーンにナレーションと画像指示）
3. 事実は絶対に変えない
4. カジュアルで親しみやすい口調

【画像プロンプトの要件】
- 英語で記述
- 具体的なシーン描写（抽象的な地図や文字は避ける）
- ニュース映像風のリアルな構図
- "photorealistic, news broadcast style, 8K, cinematic lighting" を含める
- 人の顔は避ける（著作権対策）

【出力形式】
```json
{
    "title": "キャッチーなタイトル",
    "hook": "視聴者を引き込む冒頭の一文",
    "scenes": [
        {
            "number": 1,
            "scene_type": "hook",
            "narration": "このシーンで読み上げるテキスト",
            "image_prompt": "English prompt for image generation, photorealistic, news broadcast style, 8K, cinematic lighting",
            "duration": 5
        }
    ],
    "key_points": ["要点1", "要点2", "要点3"],
    "tags": ["タグ1", "タグ2"]
}
```"""

    # カテゴリ別の画像スタイルガイド
    CATEGORY_STYLES = {
        "政治": "Japanese government building, Diet building, political press conference room, official meeting room",
        "経済": "Tokyo financial district, stock exchange screens, business district at night, corporate office",
        "テクノロジー": "modern tech office, server room with blue lights, futuristic digital interface, robotics lab",
        "国際": "world map with connections, international airport, global cityscape, diplomatic setting",
        "社会": "Japanese urban street scene, public transportation, residential area, daily life",
        "事件": "police cars with lights, urban night scene, investigation scene (no faces), news reporter backdrop",
        "スポーツ": "sports stadium, athletic track, competition venue, trophy and medals",
        "エンタメ": "concert stage, movie theater, entertainment venue, red carpet",
        "科学": "laboratory equipment, space imagery, scientific research, medical facility",
        "天気": "dramatic sky, weather patterns, seasonal scenery, natural phenomena",
    }

    def __init__(self):
        if not config.gemini.api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        
        self.client = genai.Client(api_key=config.gemini.api_key)
        self.model = config.gemini.model_text
        logger.info(f"NewsContentPlanner initialized with {self.model}")

    def plan(
        self,
        title: str,
        content: str,
        target_duration: int = 60,
        scene_count: int = 3,
    ) -> NewsVideoProject:
        """ニュース記事から動画企画を生成
        
        Args:
            title: ニュースタイトル
            content: ニュース本文
            target_duration: 目標秒数
            scene_count: シーン数
            
        Returns:
            NewsVideoProject
        """
        start_time = time.time()
        logger.info(f"Planning news video: {title[:50]}...")
        
        # カテゴリを判定
        category = self._detect_category(title + content)
        style_hint = self.CATEGORY_STYLES.get(category, self.CATEGORY_STYLES["社会"])
        
        # 各シーンの長さを計算
        scene_duration = target_duration // scene_count
        
        try:
            result = self._call_api(title, content, scene_count, scene_duration, style_hint)
            
            if result:
                scenes = [
                    NewsScene(
                        number=s.get("number", i+1),
                        scene_type=s.get("scene_type", "main"),
                        narration=s.get("narration", ""),
                        image_prompt=self._enhance_prompt(s.get("image_prompt", ""), category),
                        duration=s.get("duration", scene_duration),
                    )
                    for i, s in enumerate(result.get("scenes", []))
                ]
                
                project = NewsVideoProject(
                    original_title=title,
                    original_content=content,
                    rewritten_title=result.get("title", title),
                    hook=result.get("hook", ""),
                    scenes=scenes,
                    key_points=result.get("key_points", []),
                    tags=result.get("tags", []),
                )
                
                elapsed = time.time() - start_time
                logger.info(f"Planning complete: {len(scenes)} scenes, {elapsed:.1f}s")
                return project
                
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            raise
        
        # フォールバック
        return self._create_fallback_project(title, content, scene_count, scene_duration)

    def _call_api(
        self,
        title: str,
        content: str,
        scene_count: int,
        scene_duration: int,
        style_hint: str,
    ) -> Optional[dict]:
        """Gemini API を呼び出し"""
        user_prompt = f"""以下のニュースを{scene_count}シーンの動画企画に変換してください。
各シーンは約{scene_duration}秒です。

【カテゴリに合った画像スタイル参考】
{style_hint}

【ニュースタイトル】
{title}

【ニュース本文】
{content}

JSON形式で出力してください。"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                {"role": "user", "parts": [{"text": self.SYSTEM_PROMPT}]},
                {"role": "model", "parts": [{"text": "了解しました。ニュース動画企画を作成します。"}]},
                {"role": "user", "parts": [{"text": user_prompt}]},
            ],
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=4096,
            ),
        )
        
        text = response.text
        
        # JSONを抽出
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = text
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return None

    def _detect_category(self, text: str) -> str:
        """テキストからカテゴリを判定"""
        category_keywords = {
            "政治": ["政治", "選挙", "国会", "首相", "政府", "法案", "与党", "野党", "大臣"],
            "経済": ["経済", "株", "円", "企業", "市場", "金融", "投資", "景気", "物価", "賃金"],
            "テクノロジー": ["AI", "テクノロジー", "IT", "デジタル", "ロボット", "技術", "開発", "スマホ"],
            "国際": ["国際", "世界", "海外", "外交", "米国", "中国", "EU", "アメリカ", "韓国"],
            "社会": ["社会", "生活", "教育", "医療", "福祉", "少子化", "高齢化"],
            "事件": ["事件", "事故", "逮捕", "捜査", "被害", "容疑", "警察"],
            "スポーツ": ["スポーツ", "五輪", "サッカー", "野球", "優勝", "試合", "選手"],
            "エンタメ": ["芸能", "映画", "音楽", "ドラマ", "アニメ", "ゲーム"],
            "科学": ["科学", "研究", "発見", "宇宙", "実験", "ノーベル"],
            "天気": ["天気", "気象", "台風", "地震", "災害", "気温"],
        }
        
        for category, keywords in category_keywords.items():
            if any(kw in text for kw in keywords):
                return category
        return "社会"

    def _enhance_prompt(self, base_prompt: str, category: str) -> str:
        """画像プロンプトを強化"""
        if not base_prompt:
            style_hint = self.CATEGORY_STYLES.get(category, "")
            base_prompt = f"{style_hint}, news scene"
        
        # 必須要素を追加
        quality_tags = "photorealistic, news broadcast style, 8K resolution, cinematic lighting, professional photography"
        safety_tags = "no text overlay, no human faces, no logos"
        
        # 既に品質タグが含まれていなければ追加
        if "photorealistic" not in base_prompt.lower():
            base_prompt = f"{base_prompt}, {quality_tags}, {safety_tags}"
        
        return base_prompt

    def _create_fallback_project(
        self,
        title: str,
        content: str,
        scene_count: int,
        scene_duration: int,
    ) -> NewsVideoProject:
        """フォールバック用のプロジェクトを作成"""
        category = self._detect_category(title + content)
        style = self.CATEGORY_STYLES.get(category, self.CATEGORY_STYLES["社会"])
        
        scenes = []
        for i in range(scene_count):
            scene_type = ["hook", "main", "conclusion"][min(i, 2)]
            scenes.append(NewsScene(
                number=i + 1,
                scene_type=scene_type,
                narration=title if i == 0 else content[:100],
                image_prompt=f"{style}, {self._enhance_prompt('', category)}",
                duration=scene_duration,
            ))
        
        return NewsVideoProject(
            original_title=title,
            original_content=content,
            rewritten_title=title,
            hook=title,
            scenes=scenes,
            key_points=[],
            tags=[],
        )


if __name__ == "__main__":
    # テスト実行
    test_title = "トヨタ、新型EV「bZ5」を発表 航続距離700kmで競合に挑む"
    test_content = """
    トヨタ自動車は25日、新型電気自動車（EV）「bZ5」を発表した。
    航続距離は700kmを実現し、テスラやBYDなどの競合他社に対抗する。
    価格は500万円台からで、2026年春に発売予定。
    豊田章男会長は「EVでも世界一を目指す」と意気込みを語った。
    """
    
    try:
        planner = NewsContentPlanner()
        project = planner.plan(test_title, test_content, target_duration=60, scene_count=3)
        
        print("=" * 50)
        print(f"タイトル: {project.rewritten_title}")
        print(f"フック: {project.hook}")
        print(f"\nシーン数: {len(project.scenes)}")
        for scene in project.scenes:
            print(f"\n  Scene {scene.number} ({scene.scene_type}, {scene.duration}s):")
            print(f"    ナレーション: {scene.narration[:50]}...")
            print(f"    画像プロンプト: {scene.image_prompt[:80]}...")
        print("=" * 50)
        
    except Exception as e:
        print(f"Error: {e}")
