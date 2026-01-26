"""ニュースリライトモジュール - 若者向けにニュースを編集"""

import time
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import types

from ..config import config
from ..logger import setup_logger

logger = setup_logger("news_rewriter")


@dataclass
class RewriteResult:
    """リライト結果"""
    success: bool
    original_title: str
    original_content: str
    rewritten_title: Optional[str] = None
    rewritten_content: Optional[str] = None
    hook: Optional[str] = None  # 冒頭のキャッチーな一文
    key_points: Optional[list[str]] = None  # 要点リスト
    image_prompts: Optional[list[str]] = None  # 画像生成用プロンプト
    error_message: Optional[str] = None
    generation_time: float = 0.0


class NewsRewriter:
    """Gemini を使用してニュースを若者向けにリライト"""

    # リライトのシステムプロンプト
    SYSTEM_PROMPT = """あなたは若者向けニュースメディアの編集者です。
硬いニュース記事を、10代〜20代が興味を持つようにリライトしてください。

【絶対ルール】
1. 事実は絶対に変えない（嘘・誇張禁止）
2. 数字や固有名詞は正確に保持
3. 情報源が曖昧な場合は「〜らしい」「〜とのこと」を使う

【リライトのコツ】
1. キャッチーな導入（「え、マジで？」感を出す）
2. カジュアルな口語体（ですます調より、だ・である調 + 若者言葉）
3. 「なぜこれが重要か」を若者目線で追加
4. ツッコミどころがあれば軽く突っ込む（炎上ではなく笑い）
5. 60-90秒で読める長さに収める（300-400文字程度）

【出力形式】
以下のJSON形式で出力してください：
```json
{
    "title": "リライトしたタイトル（キャッチーに）",
    "hook": "冒頭の一文（視聴者を引き込む）",
    "content": "リライトした本文",
    "key_points": ["要点1", "要点2", "要点3"],
    "image_prompts": [
        "画像1用の英語プロンプト（ニュース映像風、具体的なシーン）",
        "画像2用の英語プロンプト（補足的なビジュアル）"
    ]
}
```"""

    def __init__(self):
        if not config.gemini.api_key:
            raise ValueError("GEMINI_API_KEY is not set")

        self.client = genai.Client(api_key=config.gemini.api_key)
        self.model = config.gemini.model_text

        logger.info(f"NewsRewriter initialized with {self.model}")

    def rewrite(
        self,
        title: str,
        content: str,
        target_audience: str = "若者",
        retry_count: int = None,
    ) -> RewriteResult:
        """ニュースをリライト

        Args:
            title: 元のニュースタイトル
            content: 元のニュース本文
            target_audience: ターゲット層
            retry_count: リトライ回数

        Returns:
            RewriteResult
        """
        start_time = time.time()
        retries = retry_count or config.retry_count

        logger.info(f"Rewriting news: {title[:50]}...")

        for attempt in range(retries):
            try:
                result = self._call_api(title, content, target_audience)

                if result:
                    return RewriteResult(
                        success=True,
                        original_title=title,
                        original_content=content,
                        rewritten_title=result.get("title"),
                        rewritten_content=result.get("content"),
                        hook=result.get("hook"),
                        key_points=result.get("key_points", []),
                        image_prompts=result.get("image_prompts", []),
                        generation_time=time.time() - start_time,
                    )

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{retries} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(config.retry_delay)

        return RewriteResult(
            success=False,
            original_title=title,
            original_content=content,
            error_message="All attempts failed",
            generation_time=time.time() - start_time,
        )

    def _call_api(
        self,
        title: str,
        content: str,
        target_audience: str,
    ) -> Optional[dict]:
        """Gemini API を呼び出し"""
        import json
        import re

        user_prompt = f"""以下のニュースを{target_audience}向けにリライトしてください。

【元のタイトル】
{title}

【元の本文】
{content}

JSON形式で出力してください。"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                {"role": "user", "parts": [{"text": self.SYSTEM_PROMPT}]},
                {"role": "model", "parts": [{"text": "了解しました。ニュースをリライトします。"}]},
                {"role": "user", "parts": [{"text": user_prompt}]},
            ],
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=2048,
            ),
        )

        # レスポンスからJSONを抽出
        text = response.text

        # コードブロック内のJSONを抽出
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # コードブロックがない場合は全体をJSONとして試す
            json_str = text

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.debug(f"Raw response: {text}")
            return None

    def rewrite_for_video(
        self,
        title: str,
        content: str,
        duration_seconds: int = 60,
    ) -> RewriteResult:
        """動画用にニュースをリライト（時間を考慮）

        Args:
            title: 元のニュースタイトル
            content: 元のニュース本文
            duration_seconds: 動画の目標秒数

        Returns:
            RewriteResult
        """
        # 1秒あたり約4文字として計算
        target_chars = duration_seconds * 4

        logger.info(f"Rewriting for {duration_seconds}s video (~{target_chars} chars)")

        result = self.rewrite(title, content)

        if result.success and result.rewritten_content:
            # 文字数調整（必要に応じて）
            current_chars = len(result.rewritten_content)
            if current_chars > target_chars * 1.2:
                logger.warning(f"Content too long ({current_chars} chars), may need trimming")

        return result


# 便利な関数
def rewrite_news(title: str, content: str) -> RewriteResult:
    """ニュースをリライト（簡易関数）"""
    rewriter = NewsRewriter()
    return rewriter.rewrite(title, content)


if __name__ == "__main__":
    # テスト実行
    test_title = "国土交通省、首都高速道路の一部区間で料金改定を発表"
    test_content = """
    国土交通省は26日、首都高速道路の一部区間において、
    2026年4月から新たな料金体系を導入すると発表した。
    混雑時間帯の料金を引き上げる一方、深夜・早朝の料金を
    引き下げる「時間帯別料金制」を採用する。
    同省は「交通量の平準化と渋滞緩和が目的」と説明している。
    対象となるのは都心環状線を含む約50kmの区間で、
    混雑時は現行より最大300円の値上げとなる見込み。
    """

    try:
        rewriter = NewsRewriter()
        result = rewriter.rewrite(test_title, test_content)

        print("=" * 50)
        print("リライト結果")
        print("=" * 50)

        if result.success:
            print(f"\n【タイトル】\n{result.rewritten_title}")
            print(f"\n【フック】\n{result.hook}")
            print(f"\n【本文】\n{result.rewritten_content}")
            print(f"\n【要点】")
            for i, point in enumerate(result.key_points or [], 1):
                print(f"  {i}. {point}")
            print(f"\n【画像プロンプト】")
            for i, prompt in enumerate(result.image_prompts or [], 1):
                print(f"  {i}. {prompt}")
            print(f"\n生成時間: {result.generation_time:.1f}s")
        else:
            print(f"エラー: {result.error_message}")

    except Exception as e:
        print(f"Error: {e}")
