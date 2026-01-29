"""
ニュース動画エージェント

Clawdbotから呼び出して:
1. 毎朝ニュース候補を通知
2. 選択を受けて動画生成
3. 完成通知
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from google import genai
from rich.console import Console

from src.fetchers.odd_news_fetcher import OddNewsFetcher, NewsArticle
from src.pipelines.news_video_pipeline import NewsVideoPipeline
from src.config import config, OUTPUT_DIR

console = Console()

# 状態保存用
STATE_FILE = OUTPUT_DIR / "agent_state.json"


@dataclass
class AgentState:
    """エージェント状態"""
    candidates: list[dict] = None
    selected_index: Optional[int] = None
    video_path: Optional[str] = None
    last_fetch: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "candidates": self.candidates,
            "selected_index": self.selected_index,
            "video_path": self.video_path,
            "last_fetch": self.last_fetch,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentState":
        return cls(
            candidates=data.get("candidates"),
            selected_index=data.get("selected_index"),
            video_path=data.get("video_path"),
            last_fetch=data.get("last_fetch"),
        )
    
    def save(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls) -> "AgentState":
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                return cls.from_dict(json.load(f))
        return cls()


class NewsVideoAgent:
    """ニュース動画生成エージェント"""
    
    def __init__(self):
        self.fetcher = OddNewsFetcher()
        self.pipeline = None  # 遅延初期化
        self.state = AgentState.load()
        
        # Gemini for AI scoring
        self.gemini_client = genai.Client(api_key=config.gemini.api_key)
        
        console.print("[green]NewsVideoAgent initialized[/green]")
    
    def ai_score_articles(self, articles: list[NewsArticle]) -> list[NewsArticle]:
        """AIで記事をスコアリング（映像化しやすさ）"""
        
        console.print("[cyan]🤖 AI スコアリング中...[/cyan]")
        
        # バッチでスコアリング
        articles_text = "\n".join([
            f"{i+1}. {a.title}\n   {a.summary[:100]}"
            for i, a in enumerate(articles[:20])  # 上位20件のみ
        ])
        
        prompt = f"""以下のニュース記事を「動画コンテンツ化しやすさ」でスコアリングしてください。

# 評価基準
- 視覚的に面白い（映像化しやすい）: +20点
- 動物が登場: +15点  
- 感動・ほっこり系: +15点
- 世界記録・珍しい達成: +10点
- ストーリー性がある: +10点
- ネガティブ（事故・犯罪）: -30点
- 政治・論争的: -20点

# 記事リスト
{articles_text}

# 出力（JSON）
各記事のスコア（0-100）と理由を簡潔に:
```json
{{
  "scores": [
    {{"index": 1, "score": 85, "reason": "猫の感動話、映像化◎"}},
    ...
  ]
}}
```"""

        try:
            response = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            content = response.text
            
            # JSON抽出
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            json_str = content[json_start:json_end]
            data = json.loads(json_str)
            
            # スコアを反映
            score_map = {s["index"]: s for s in data["scores"]}
            for i, article in enumerate(articles[:20]):
                if i + 1 in score_map:
                    score_info = score_map[i + 1]
                    # キーワードスコアとAIスコアを統合
                    ai_score = score_info["score"]
                    article.score = int((article.score + ai_score) / 2)  # 平均
                    console.print(f"  {i+1}. [{article.score}] {article.title[:40]}...")
            
            # 再ソート
            articles.sort(key=lambda x: x.score, reverse=True)
            
        except Exception as e:
            console.print(f"[yellow]AI スコアリング失敗（キーワードスコアを使用）: {e}[/yellow]")
        
        return articles
    
    def fetch_candidates(self, limit: int = 5) -> str:
        """ニュース候補を取得してDM用テキストを返す"""
        
        console.print("\n[bold]📰 今日のニュース候補を取得中...[/bold]\n")
        
        # RSS取得 + キーワードスコアリング
        articles = self.fetcher.fetch_top_news(limit=20)
        
        # AIスコアリング
        articles = self.ai_score_articles(articles)
        
        # 上位N件を候補に
        top_articles = articles[:limit]
        
        # 状態保存
        self.state.candidates = [a.to_dict() for a in top_articles]
        self.state.last_fetch = datetime.now().isoformat()
        self.state.selected_index = None
        self.state.video_path = None
        self.state.save()
        
        # Discord用フォーマット
        return self._format_candidates(top_articles)
    
    def _format_candidates(self, articles: list[NewsArticle]) -> str:
        """候補をDiscord用にフォーマット"""
        
        lines = ["📰 **今日のおもしろニュース候補:**\n"]
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        
        for i, article in enumerate(articles):
            emoji = emojis[i] if i < len(emojis) else f"{i+1}."
            title = article.title[:50] if len(article.title) > 50 else article.title
            
            lines.append(f"{emoji} **{title}** ({article.score}点)")
            if article.summary:
                lines.append(f"   _{article.summary[:60]}..._")
            lines.append("")
        
        lines.append("**操作:**")
        lines.append("• 番号で選択（例: `1`）")
        lines.append("• `スキップ` - 今日はパス")
        lines.append("• `全自動` - 1位を自動生成")
        lines.append("• URL直接指定も可")
        
        return "\n".join(lines)
    
    def select_article(self, selection: str) -> str:
        """記事を選択して動画生成を開始"""
        
        selection = selection.strip().lower()
        
        # スキップ
        if selection in ["スキップ", "skip", "パス", "pass"]:
            self.state.selected_index = None
            self.state.save()
            return "了解！今日はスキップ 👋"
        
        # 全自動
        if selection in ["全自動", "auto", "自動"]:
            selection = "1"
        
        # 番号選択
        if selection.isdigit():
            index = int(selection) - 1
            if not self.state.candidates:
                return "❌ 候補がありません。まず `ニュース候補` で取得してください。"
            if index < 0 or index >= len(self.state.candidates):
                return f"❌ 1-{len(self.state.candidates)} の番号で選択してください。"
            
            self.state.selected_index = index
            self.state.save()
            
            article = self.state.candidates[index]
            return self._start_generation(article)
        
        # URL指定
        if selection.startswith("http"):
            return self._start_generation_from_url(selection)
        
        return "❓ 番号、`スキップ`、`全自動`、または URL で指定してください。"
    
    def _start_generation(self, article: dict) -> str:
        """動画生成を開始"""
        
        title = article["title"]
        url = article["url"]
        
        console.print(f"\n[bold green]🎬 動画生成開始: {title[:40]}...[/bold green]\n")
        
        # 記事本文を取得
        full_text = self.fetcher.fetch_full_article(url)
        if not full_text:
            full_text = article.get("summary", title)
        
        # 日本語にリライト（4シーン構成）
        translated = self._translate_to_japanese(title, full_text, num_scenes=4)
        
        console.print(f"📝 リライト完了:")
        console.print(f"  見出し: {translated.get('headline', 'N/A')}")
        console.print(f"  シーン数: {len(translated.get('scenes', []))}")
        
        # パイプライン初期化（遅延）
        if self.pipeline is None:
            self.pipeline = NewsVideoPipeline(
                channel_name="FJ News 24",
                num_scenes=4,
                scene_duration=5.0,
            )
        
        # 動画生成（シーン構成データを渡す）
        result = self.pipeline.run(
            headline=translated["headline"],
            sub_headline=translated.get("sub_headline", ""),
            scenes_data=translated.get("scenes", []),
            closing_text=translated.get("closing", ""),
            is_breaking=True,
        )
        
        if result.success:
            self.state.video_path = result.video_path
            self.state.save()
            
            return f"""🎉 **動画完成！**

📹 {result.video_path}
⏱️ {result.duration_seconds:.1f}秒

確認して問題なければ投稿してね！"""
        else:
            return f"❌ 生成失敗: {result.error_message}"
    
    def _start_generation_from_url(self, url: str) -> str:
        """URLから直接動画生成"""
        
        console.print(f"\n[bold green]🎬 URL から動画生成: {url}[/bold green]\n")
        
        full_text = self.fetcher.fetch_full_article(url)
        if not full_text:
            return "❌ 記事の取得に失敗しました。"
        
        # タイトル抽出を試みる
        title = url.split("/")[-1].replace("-", " ")[:50]
        
        translated = self._translate_to_japanese(title, full_text)
        
        console.print(f"📝 リライト完了:")
        console.print(f"  見出し: {translated.get('headline', 'N/A')}")
        console.print(f"  サブ: {translated.get('sub_headline', 'N/A')}")
        console.print(f"  シーン数: {len(translated.get('scenes', []))}")
        
        if self.pipeline is None:
            self.pipeline = NewsVideoPipeline()
        
        result = self.pipeline.run(
            headline=translated["headline"],
            sub_headline=translated.get("sub_headline", ""),
            scenes_data=translated.get("scenes", []),
            closing_text=translated.get("closing", ""),
        )
        
        if result.success:
            self.state.video_path = result.video_path
            self.state.save()
            return f"🎉 **動画完成！** {result.video_path}"
        else:
            return f"❌ 生成失敗: {result.error_message}"
    
    def _translate_to_japanese(self, title: str, article: str, num_scenes: int = 4) -> dict:
        """記事を日本語にリライト（4シーン構成・ユーモア＆オリジナリティ）"""
        
        prompt = f"""以下の英語ニュースを、日本語の面白いニュース動画用に{num_scenes}シーン構成でリライトしてください。

# 重要ルール
- 元記事をそのまま翻訳するのではなく、あなたの言葉でリライトする
- 軽いユーモアやツッコミを入れて、視聴者が楽しめる内容にする
- 事実は正確に伝えつつ、表現を工夫する
- 「〜だそうです」「〜とのこと」など堅い表現は避け、親しみやすく
- **各シーンのナレーションは映像と同期するので、シーンの内容に合った文章にする**

# シーン構成ガイド（{num_scenes}シーン、各10-15秒）
1. **オープニング**: 視聴者の興味を引くフック。「えっ!?」となる導入
2. **展開1**: 状況説明、何が起きたのかを伝える
3. **展開2**: クライマックス、最も印象的・感動的な部分
4. **エンディング**: 結末と余韻、視聴者への問いかけ

# 元記事
タイトル: {title}
本文: {article[:2500]}

# 出力（JSON）
```json
{{
  "headline": "キャッチーなタイトル（15文字以内）",
  "sub_headline": "補足タイトル（20文字以内）",
  "scenes": [
    {{
      "scene_number": 1,
      "title": "シーンの短いタイトル（5文字以内）",
      "narration": "このシーンのナレーション（50-80文字）。映像に合わせた内容で。",
      "visual_description": "このシーンの映像イメージ（日本語で簡潔に）"
    }},
    {{
      "scene_number": 2,
      "title": "...",
      "narration": "...",
      "visual_description": "..."
    }},
    {{
      "scene_number": 3,
      "title": "...",
      "narration": "...",
      "visual_description": "..."
    }},
    {{
      "scene_number": 4,
      "title": "...",
      "narration": "...",
      "visual_description": "..."
    }}
  ],
  "closing": "締めの一言（20-30文字）。感想やツッコミ"
}}
```"""

        try:
            response = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            content = response.text
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            return json.loads(content[json_start:json_end])
        except Exception as e:
            console.print(f"[yellow]翻訳失敗: {e}[/yellow]")
            return {
                "headline": title[:15],
                "article": article[:200],
            }
    
    def get_status(self) -> str:
        """現在の状態を返す"""
        
        if not self.state.candidates:
            return "📭 候補なし。`ニュース候補` で取得してください。"
        
        status = f"📊 **ステータス**\n"
        status += f"• 最終取得: {self.state.last_fetch}\n"
        status += f"• 候補数: {len(self.state.candidates)}件\n"
        
        if self.state.selected_index is not None:
            article = self.state.candidates[self.state.selected_index]
            status += f"• 選択中: {article['title'][:30]}...\n"
        
        if self.state.video_path:
            status += f"• 完成動画: {self.state.video_path}\n"
        
        return status


# Clawdbot から呼び出すエントリーポイント
_agent = None

def get_agent() -> NewsVideoAgent:
    global _agent
    if _agent is None:
        _agent = NewsVideoAgent()
    return _agent


def fetch_news() -> str:
    """ニュース候補を取得"""
    return get_agent().fetch_candidates()


def select_news(selection: str) -> str:
    """ニュースを選択して動画生成"""
    return get_agent().select_article(selection)


def get_status() -> str:
    """ステータス取得"""
    return get_agent().get_status()


# CLI
if __name__ == "__main__":
    import sys
    
    agent = NewsVideoAgent()
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "fetch":
            print(agent.fetch_candidates())
        elif cmd == "select" and len(sys.argv) > 2:
            print(agent.select_article(sys.argv[2]))
        elif cmd == "status":
            print(agent.get_status())
        else:
            print("Usage: python -m src.agents.news_agent [fetch|select <num>|status]")
    else:
        # デフォルト: 候補取得
        print(agent.fetch_candidates())
