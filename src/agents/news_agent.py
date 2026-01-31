"""News Video Agent - インタラクティブな記事選択と動画生成"""
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
import requests
from rich.console import Console

from src.sources.base import Category, Article
from src.sources.selector import NewsSelector
from src.pipelines.news_video_pipeline import NewsVideoPipeline

console = Console()


class NewsVideoAgent:
    """ニュース動画エージェント"""
    
    # カテゴリキーワードマッピング
    CATEGORY_KEYWORDS = {
        "バズ": Category.BUZZ,
        "バズニュース": Category.BUZZ,
        "buzz": Category.BUZZ,
        "動物": Category.ANIMALS,
        "ペット": Category.ANIMALS,
        "animals": Category.ANIMALS,
        "トレンド": Category.TREND,
        "trend": Category.TREND,
        "過去": Category.ARCHIVE,
        "伝説": Category.ARCHIVE,
        "archive": Category.ARCHIVE,
        "レジェンド": Category.ARCHIVE,
        "z世代": Category.GENZ,
        "genz": Category.GENZ,
        "あるある": Category.GENZ,
    }
    
    def __init__(self):
        self.webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
        self.pending_articles: dict[str, list[Article]] = {}  # channel_id -> articles
        self.pipeline = None
    
    def _send_discord_message(self, content: str = None, embed: dict = None) -> bool:
        """Discord Webhookでメッセージ送信"""
        if not self.webhook_url:
            console.print("[yellow]⚠️ DISCORD_WEBHOOK_URL not set[/yellow]")
            return False
        
        payload = {}
        if content:
            payload["content"] = content
        if embed:
            payload["embeds"] = [embed]
        
        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            return response.status_code == 204
        except Exception as e:
            console.print(f"[red]❌ Discord送信エラー: {e}[/red]")
            return False
    
    def detect_category(self, message: str) -> Optional[Category]:
        """メッセージからカテゴリを検出"""
        message_lower = message.lower()
        for keyword, category in self.CATEGORY_KEYWORDS.items():
            if keyword in message_lower:
                return category
        return None
    
    def detect_selection(self, message: str) -> Optional[int]:
        """メッセージから番号選択を検出"""
        # 数字のみ or "1番" or "#1" など
        match = re.search(r'^(\d+)(?:番)?$|^#?(\d+)$', message.strip())
        if match:
            num = match.group(1) or match.group(2)
            return int(num)
        return None
    
    async def show_article_list(self, category: Category, count: int = 10) -> list[Article]:
        """記事リストを取得してDiscordに表示"""
        console.print(f"[cyan]📰 {category.value} の記事を取得中...[/cyan]")
        
        articles = await NewsSelector.fetch_by_category(category, count)
        
        if not articles:
            self._send_discord_message("❌ 記事が見つかりませんでした")
            return []
        
        # Embed形式で記事リストを作成
        description_lines = []
        for i, article in enumerate(articles, 1):
            title = article.title[:50] + "..." if len(article.title) > 50 else article.title
            score_emoji = "🔥" if article.score > 1000 else "📰"
            url_text = f"\n   └ <{article.url}>" if article.url else ""
            description_lines.append(f"**{i}.** {score_emoji} {title}{url_text}")
        
        embed = {
            "title": f"📰 {category.value.upper()} ニュース",
            "description": "\n".join(description_lines),
            "color": 0x00aaff,
            "footer": {"text": "番号を入力して選択してください（例: 1）"},
        }
        
        self._send_discord_message(embed=embed)
        return articles
    
    async def start_generation_from_article(self, article: Article) -> str:
        """記事から動画生成を開始"""
        console.print(f"[green]🎬 動画生成開始: {article.title[:50]}...[/green]")
        
        # 開始通知
        self._send_discord_message(
            embed={
                "title": "🎬 動画生成開始",
                "description": f"**{article.title}**\n\n生成には数分かかります...",
                "color": 0xffaa00,
            }
        )
        
        # パイプライン初期化
        if self.pipeline is None:
            from dotenv import load_dotenv
            load_dotenv()
            self.pipeline = NewsVideoPipeline(channel_name="N1", use_remotion=True)
        
        # 記事からシーン構成を生成（日本語見出し含む）
        scenes_data, headline_ja, sub_headline_ja = await self._generate_scenes_from_article(article)
        
        console.print(f"[cyan]📰 日本語見出し: {headline_ja}[/cyan]")
        console.print(f"[cyan]📰 サブ見出し: {sub_headline_ja}[/cyan]")
        
        # パイプライン実行
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_prefix = f"news_{timestamp}"
        
        result = self.pipeline.run(
            headline=headline_ja,  # 日本語見出し
            sub_headline=sub_headline_ja,  # 日本語サブ見出し
            scenes_data=scenes_data,
            output_prefix=output_prefix,
            is_breaking=True,
        )
        
        if result.success:
            return result.video_path
        else:
            self._send_discord_message(f"❌ 生成失敗: {result.error_message}")
            return ""
    
    async def _generate_scenes_from_article(self, article: Article) -> tuple[list[dict], str, str]:
        """記事からシーン構成を自動生成
        
        Returns:
            tuple: (scenes_data, japanese_headline, japanese_sub_headline)
        """
        # Geminiで記事を分析してシーン構成を生成
        import google.genai as genai
        from src.config import config
        
        client = genai.Client(api_key=config.gemini.api_key)
        
        prompt = f"""以下のニュース記事から、ショート動画（60秒以内）用のシーン構成を作成してください。

タイトル: {article.title}
概要: {article.summary or "概要なし"}
URL: {article.url}

以下のJSON形式で出力してください:
```json
{{
  "headline": "日本語の見出し（15文字以内、インパクト重視）",
  "sub_headline": "日本語のサブ見出し（20文字以内）",
  "scenes": [
    {{
      "title": "シーンタイトル",
      "narration": "ナレーションテキスト（1文）",
      "visual_description": "映像の説明（英語推奨）",
      "emphasis_word": "強調キーワード"
    }}
  ]
}}
```

注意:
- headline と sub_headline は必ず日本語で
- scenes は8-10シーン
- フックで視聴者を引き込む冒頭
- 各シーン5-7秒程度のナレーション
- 驚きや感動のポイントを強調
- 最後は視聴者への問いかけで締める
"""
        
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            
            # JSONを抽出
            text = response.text
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
                scenes = data.get("scenes", [])
                headline_ja = data.get("headline", article.title)
                sub_headline_ja = data.get("sub_headline", "")
                return scenes, headline_ja, sub_headline_ja
        except Exception as e:
            console.print(f"[yellow]⚠️ Gemini分析エラー: {e}[/yellow]")
        
        # フォールバック: 基本的なシーン構成
        fallback_scenes = [
            {
                "title": "導入",
                "narration": f"今日は驚きのニュースをお届けします。",
                "visual_description": "News studio with breaking news graphics",
                "emphasis_word": "驚き",
            },
            {
                "title": "詳細",
                "narration": article.summary[:200] if article.summary else "詳細をお伝えします。",
                "visual_description": "Documentary style footage related to the news",
                "emphasis_word": "",
            },
            {
                "title": "締め",
                "narration": "いかがでしたか？面白かったらいいねお願いします！",
                "visual_description": "End screen with subscribe button",
                "emphasis_word": "いいね",
            },
        ]
        # フォールバック時は元のタイトルをそのまま使用（翻訳失敗）
        return fallback_scenes, article.title, ""
    
    async def handle_message(self, message: str, channel_id: str = "default") -> str:
        """メッセージを処理"""
        # カテゴリ検出
        category = self.detect_category(message)
        if category:
            articles = await self.show_article_list(category)
            self.pending_articles[channel_id] = articles
            return f"記事リストを表示しました（{len(articles)}件）"
        
        # 番号選択検出
        selection = self.detect_selection(message)
        if selection and channel_id in self.pending_articles:
            articles = self.pending_articles[channel_id]
            if 1 <= selection <= len(articles):
                article = articles[selection - 1]
                video_path = await self.start_generation_from_article(article)
                if video_path:
                    del self.pending_articles[channel_id]
                    return f"動画生成完了: {video_path}"
                return "動画生成に失敗しました"
            return f"無効な番号です（1-{len(articles)}）"
        
        return ""
    
    # URL直接入力対応
    def _start_generation_from_url(self, url: str) -> str:
        """URLから直接動画生成"""
        # ページタイトルを取得
        title = self._fetch_page_title(url)
        
        article = Article(
            title=title,
            url=url,
            source="Direct URL",
            category=Category.BUZZ,
            summary="",
        )
        return asyncio.run(self.start_generation_from_article(article))
    
    def _fetch_page_title(self, url: str) -> str:
        """URLからページタイトルを取得"""
        try:
            import requests
            from html.parser import HTMLParser
            
            class TitleParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.in_title = False
                    self.title = ""
                
                def handle_starttag(self, tag, attrs):
                    if tag.lower() == "title":
                        self.in_title = True
                
                def handle_endtag(self, tag):
                    if tag.lower() == "title":
                        self.in_title = False
                
                def handle_data(self, data):
                    if self.in_title:
                        self.title += data
            
            response = requests.get(url, timeout=10, headers={"User-Agent": "N1NewsBot/1.0"})
            response.raise_for_status()
            
            parser = TitleParser()
            parser.feed(response.text[:10000])  # 最初の10KBだけパース
            
            if parser.title:
                # タイトルをクリーンアップ
                title = parser.title.strip()
                # サイト名を除去（例: " | CNN" や " - BBC"）
                for sep in [" | ", " - ", " – ", " — "]:
                    if sep in title:
                        title = title.split(sep)[0].strip()
                return title[:100]  # 最大100文字
        except Exception as e:
            console.print(f"[yellow]⚠️ タイトル取得失敗: {e}[/yellow]")
        
        return "最新ニュース"


async def main():
    """CLI entrypoint"""
    import argparse
    
    parser = argparse.ArgumentParser(description="ニュース動画エージェント")
    parser.add_argument("--category", "-c", help="カテゴリ (buzz/animals/trend/archive/genz)")
    parser.add_argument("--select", "-s", type=int, help="記事番号を選択して生成")
    parser.add_argument("--interactive", "-i", action="store_true", help="インタラクティブモード")
    
    args = parser.parse_args()
    
    from dotenv import load_dotenv
    load_dotenv()
    
    agent = NewsVideoAgent()
    
    if args.category:
        category = Category(args.category)
        articles = await agent.show_article_list(category)
        
        if args.select and articles:
            if 1 <= args.select <= len(articles):
                await agent.start_generation_from_article(articles[args.select - 1])
            else:
                console.print(f"[red]無効な番号: {args.select}[/red]")
    
    elif args.interactive:
        console.print("[cyan]インタラクティブモード（'quit'で終了）[/cyan]")
        while True:
            try:
                message = input("> ").strip()
                if message.lower() == "quit":
                    break
                result = await agent.handle_message(message)
                if result:
                    console.print(f"[green]{result}[/green]")
            except KeyboardInterrupt:
                break


if __name__ == "__main__":
    asyncio.run(main())
