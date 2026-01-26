"""ニュース解説生成モジュール - Gemini APIで分かりやすい解説を生成"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from google import genai
from google.genai import types

from ..config import config
from ..logger import setup_logger
from ..utils.news_scraper import NewsScraper, ScrapedArticle

logger = setup_logger("news_explainer")


@dataclass
class NewsExplanation:
    """ニュース解説データ"""
    title: str
    original_title: str
    hook: str  # 冒頭のフック（3-5秒）
    main_points: list[str] = field(default_factory=list)  # 要点（各10-15秒）
    conclusion: str = ""  # 結論（5-10秒）
    full_script: str = ""  # フルスクリプト
    estimated_duration: int = 60  # 推定秒数
    keywords: list[str] = field(default_factory=list)
    difficulty: str = "中学生"  # 理解レベル
    source_url: str = ""
    image_prompts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "original_title": self.original_title,
            "hook": self.hook,
            "main_points": self.main_points,
            "conclusion": self.conclusion,
            "full_script": self.full_script,
            "estimated_duration": self.estimated_duration,
            "keywords": self.keywords,
            "difficulty": self.difficulty,
            "source_url": self.source_url,
            "image_prompts": self.image_prompts,
        }

    def get_narration_script(self) -> str:
        """ナレーション用スクリプトを取得"""
        parts = [self.hook]
        parts.extend(self.main_points)
        parts.append(self.conclusion)
        return "。".join(parts)


class NewsExplainer:
    """Gemini APIでニュースを分かりやすく解説"""

    DIFFICULTY_LEVELS = {
        "小学生": "10歳の子供でも理解できるように、難しい言葉は使わず、例え話を多用して",
        "中学生": "中学生が理解できるように、専門用語は簡単に説明しながら",
        "高校生": "高校生向けに、適度な専門用語を使いながら論理的に",
        "一般": "一般成人向けに、ニュースキャスターのように分かりやすく",
        "若者": "Z世代向けに、カジュアルでユーモアを交えながら、友達に話すように",
    }

    def __init__(self):
        if not config.gemini.api_key:
            raise ValueError("GEMINI_API_KEY が設定されていません")

        # Google Genai クライアント (新API)
        self.client = genai.Client(api_key=config.gemini.api_key)
        self.model_name = config.gemini.model_text
        self.scraper = NewsScraper()

        # レート制限対策（無料プラン: 2リクエスト/分）
        self.last_request_time = 0
        self.min_request_interval = 30  # 30秒間隔

        logger.info("NewsExplainer initialized")

    def _wait_for_rate_limit(self):
        """レート制限を回避するため待機"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            wait_time = self.min_request_interval - elapsed
            logger.info(f"Rate limit: waiting {wait_time:.1f}s")
            time.sleep(wait_time)
        self.last_request_time = time.time()

    def _generate_with_retry(self, prompt: str, max_retries: int = 3):
        """リトライ付きでGemini APIを呼び出し"""
        self._wait_for_rate_limit()

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.7,
                        max_output_tokens=2000,
                    ),
                )
                return response.text

            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "resource_exhausted" in error_str or "quota" in error_str:
                    if attempt < max_retries - 1:
                        wait_time = 60 * (attempt + 1)  # 60秒, 120秒と増加
                        logger.warning(f"Rate limit hit, waiting {wait_time}s (attempt {attempt+1}/{max_retries})")
                        time.sleep(wait_time)
                        self.last_request_time = time.time()
                        continue
                raise

        return None

    def explain(
        self,
        article: ScrapedArticle,
        difficulty: str = "中学生",
        target_duration: int = 60,
    ) -> NewsExplanation:
        """記事を解説動画用に変換

        Args:
            article: スクレイピングした記事
            difficulty: 難易度レベル
            target_duration: 目標秒数（30-90）

        Returns:
            NewsExplanation
        """
        logger.info(f"Explaining: {article.title[:50]}...")

        difficulty_instruction = self.DIFFICULTY_LEVELS.get(
            difficulty, self.DIFFICULTY_LEVELS["中学生"]
        )

        prompt = self._build_prompt(article, difficulty_instruction, target_duration)

        try:
            # レート制限対策付きでAPI呼び出し
            response_text = self._generate_with_retry(prompt)

            if not response_text:
                logger.warning("Empty response from Gemini API")
                return self._create_fallback_explanation(article, difficulty)

            explanation = self._parse_response(response_text, article, difficulty)
            logger.info(f"Generated explanation: ~{explanation.estimated_duration}s")

            return explanation

        except Exception as e:
            logger.error(f"Explanation generation failed: {e}")
            # フォールバック: 簡易解説
            return self._create_fallback_explanation(article, difficulty)

    def from_url(
        self,
        url: str,
        difficulty: str = "中学生",
        target_duration: int = 60,
    ) -> NewsExplanation:
        """URLから記事を取得して解説

        Args:
            url: 記事URL
            difficulty: 難易度
            target_duration: 目標秒数

        Returns:
            NewsExplanation
        """
        article = self.scraper.scrape(url)

        if not article.text:
            raise ValueError(f"Failed to scrape article: {url}")

        explanation = self.explain(article, difficulty, target_duration)
        explanation.source_url = url

        return explanation

    def _build_prompt(
        self,
        article: ScrapedArticle,
        difficulty_instruction: str,
        target_duration: int,
    ) -> str:
        """プロンプト構築"""
        # 本文を適度な長さに
        text = article.text[:2000] if article.text else article.summary

        return f"""あなたはYouTubeショート動画のスクリプトライターです。
以下のニュース記事を、{difficulty_instruction}解説してください。

【元記事】
タイトル: {article.title}
本文: {text}

【動画の要件】
- 長さ: 約{target_duration}秒（{int(target_duration * 5)}文字程度）
- ターゲット: Z世代・若者（10代〜20代）
- トーン: カジュアル、面白い、友達に話すような感じ
- 構成:
  1. フック（「マジで？」と思わせる冒頭、3-5秒）
  2. メインポイント（2-3個の要点、各10-15秒）
  3. 結論（オチ or 感想、5-10秒）

【スタイルガイド - 霜降り明星・粗品風ツッコミ】
- 鋭いツッコミを入れる（例: 「いや、おかしいやろ」「なんでやねん」「どういうこと？」）
- 大げさにリアクションする（例: 「えぐっ！」「やばすぎて草」「嘘やろ？」）
- 数字や事実に対して驚く（例: 「30億て。30億て！」「桁がバグってる」）
- 例え話でボケる（例: 「俺の家賃何年分やねん」「普通に国買えるやん」）
- ツッコミからの感想（例: 「...まあでも正直ちょっと羨ましいけどな」）
- テンポよく、間を大事に
- 関西弁OK、標準語でも可
- 視聴者に同意を求める（例: 「いや、思うやん？」「おかしいと思わん？」）

【出力形式（JSON）】
```json
{{
    "title": "動画タイトル（煽りつつ気になる感じ、20-30文字）",
    "hook": "冒頭の1文（いきなりツッコミから入る）",
    "main_points": [
        "要点1（事実→ツッコミ→解説の流れ）",
        "要点2（数字があれば大げさにリアクション）",
        "要点3（オプション、ボケ入れてもOK）"
    ],
    "conclusion": "結論（最後にオチ or 本音の感想）",
    "keywords": ["キーワード1", "キーワード2", "キーワード3"],
    "image_prompts": [
        "シーン1の背景画像生成プロンプト（英語、詳細）",
        "シーン2の背景画像生成プロンプト（英語、詳細）",
        "シーン3の背景画像生成プロンプト（英語、詳細）"
    ]
}}
```

【注意事項】
- 事実は正確に（誇張はOKだけど嘘はNG）
- 誹謗中傷・差別的表現は絶対NG
- 専門用語は「つまり〜ってこと」と噛み砕く
- image_promptsは各シーンに合った視覚的な背景を英語で指定"""

    def _parse_response(
        self,
        text: str,
        article: ScrapedArticle,
        difficulty: str,
    ) -> NewsExplanation:
        """レスポンス解析"""
        # JSONを抽出
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)

        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = text

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}")
            return self._create_fallback_explanation(article, difficulty)

        # フルスクリプト作成
        parts = [data.get("hook", "")]
        parts.extend(data.get("main_points", []))
        parts.append(data.get("conclusion", ""))
        full_script = "。".join(p for p in parts if p)

        # 秒数推定（日本語: 約5文字/秒）
        estimated_duration = len(full_script) // 5

        return NewsExplanation(
            title=data.get("title", article.title),
            original_title=article.title,
            hook=data.get("hook", ""),
            main_points=data.get("main_points", []),
            conclusion=data.get("conclusion", ""),
            full_script=full_script,
            estimated_duration=estimated_duration,
            keywords=data.get("keywords", []),
            difficulty=difficulty,
            source_url=article.url,
            image_prompts=data.get("image_prompts", []),
        )

    def _create_fallback_explanation(
        self,
        article: ScrapedArticle,
        difficulty: str,
    ) -> NewsExplanation:
        """フォールバック解説作成"""
        # 本文から重要文を抽出
        key_sentences = self.scraper.extract_key_sentences(article.text, 3)

        hook = f"今話題の「{article.title}」について解説します。"
        main_points = key_sentences if key_sentences else [article.summary[:100]]
        conclusion = "以上、最新ニュースの解説でした。"

        full_script = hook + "。".join(main_points) + "。" + conclusion
        estimated_duration = len(full_script) // 5

        return NewsExplanation(
            title=article.title,
            original_title=article.title,
            hook=hook,
            main_points=main_points,
            conclusion=conclusion,
            full_script=full_script,
            estimated_duration=estimated_duration,
            difficulty=difficulty,
            source_url=article.url,
        )

    def adjust_duration(
        self,
        explanation: NewsExplanation,
        target_seconds: int,
    ) -> NewsExplanation:
        """スクリプトの長さを調整

        Args:
            explanation: 元の解説
            target_seconds: 目標秒数

        Returns:
            調整後のNewsExplanation
        """
        current_chars = len(explanation.full_script)
        target_chars = target_seconds * 5  # 5文字/秒

        if abs(current_chars - target_chars) < 50:
            # 十分近い
            return explanation

        # 再生成が必要
        ratio = target_chars / current_chars

        if ratio < 1:
            # 短くする
            logger.info(f"Shortening script: {current_chars} -> {target_chars} chars")
            # main_pointsを削減
            if len(explanation.main_points) > 2 and ratio < 0.7:
                explanation.main_points = explanation.main_points[:2]
        else:
            # 長くする - 各ポイントを詳細化
            logger.info(f"Script expansion needed (manual adjustment recommended)")

        # フルスクリプト再構築
        parts = [explanation.hook]
        parts.extend(explanation.main_points)
        parts.append(explanation.conclusion)
        explanation.full_script = "。".join(p for p in parts if p)
        explanation.estimated_duration = len(explanation.full_script) // 5

        return explanation


if __name__ == "__main__":
    # テスト実行
    try:
        explainer = NewsExplainer()

        # テスト用の記事
        test_article = ScrapedArticle(
            url="https://example.com/news",
            title="AIが変える未来の働き方",
            text="""
人工知能（AI）技術の急速な発展により、私たちの働き方は大きく変わろうとしています。
特に生成AIの登場は、様々な業界に革命をもたらしています。

専門家によると、2025年までに現在の仕事の30%がAIによって自動化される可能性があるとのことです。
しかし、同時に新しい職種も生まれると予測されています。

企業は従業員のリスキリング（学び直し）を急ピッチで進めており、
AIと協働できる人材の育成が急務となっています。
            """,
            summary="AI技術の発展で働き方が変化、リスキリングが重要に",
        )

        print("=== News Explainer Test ===")
        explanation = explainer.explain(test_article, difficulty="中学生", target_duration=60)

        print(f"\nTitle: {explanation.title}")
        print(f"Duration: ~{explanation.estimated_duration}s")
        print(f"\nHook: {explanation.hook}")
        print(f"\nMain Points:")
        for i, point in enumerate(explanation.main_points, 1):
            print(f"  {i}. {point}")
        print(f"\nConclusion: {explanation.conclusion}")

    except Exception as e:
        print(f"Error: {e}")
