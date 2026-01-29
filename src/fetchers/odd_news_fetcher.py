"""
海外おもしろニュース取得モジュール

UPI Odd News などから面白いニュースを取得してスコアリング
"""

import feedparser
import httpx
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import re
import json

from bs4 import BeautifulSoup
from rich.console import Console

console = Console()


@dataclass
class NewsArticle:
    """ニュース記事"""
    title: str
    url: str
    summary: str
    published: Optional[datetime] = None
    source: str = ""
    score: int = 0
    full_text: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "published": self.published.isoformat() if self.published else None,
            "source": self.source,
            "score": self.score,
        }


class OddNewsFetcher:
    """海外おもしろニュース取得"""
    
    # RSSフィード
    RSS_FEEDS = {
        "upi_odd": "https://rss.upi.com/news/odd_news.rss",
        "reddit_nottheonion": "https://www.reddit.com/r/nottheonion/.rss",
        "reddit_upliftingnews": "https://www.reddit.com/r/UpliftingNews/.rss",
        "reddit_mademesmile": "https://www.reddit.com/r/MadeMeSmile/.rss",
        "bbc_news": "https://feeds.bbci.co.uk/news/rss.xml",
    }
    
    # スコアリング用キーワード
    SCORE_KEYWORDS = {
        # 動物系 (高スコア)
        "cat": 15, "dog": 15, "猫": 15, "犬": 15,
        "animal": 10, "pet": 10, "bird": 10,
        "fox": 12, "bear": 12, "elephant": 12,
        
        # 奇跡・感動系
        "miracle": 15, "rescue": 12, "save": 10,
        "reunite": 15, "found": 10, "return": 10,
        "survive": 12, "incredible": 10,
        
        # 面白い系
        "funny": 8, "bizarre": 8, "unusual": 8,
        "weird": 8, "strange": 8,
        
        # 世界記録系
        "world record": 15, "guinness": 15,
        "first": 10, "largest": 10, "oldest": 10,
        
        # ネガティブ (減点)
        "death": -20, "die": -15, "kill": -20,
        "accident": -10, "crash": -10,
        "arrest": -15, "crime": -15,
    }
    
    def __init__(self):
        self.client = httpx.Client(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            },
            follow_redirects=True,
        )
    
    def fetch_rss(self, feed_url: str, source_name: str) -> list[NewsArticle]:
        """RSSフィードから記事を取得"""
        articles = []
        
        try:
            # SSL問題を回避するためhttpxで取得してからパース
            response = self.client.get(feed_url)
            feed = feedparser.parse(response.text)
            
            for entry in feed.entries[:20]:  # 最新20件
                # 公開日時
                published = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                
                # サマリー
                summary = ""
                if hasattr(entry, 'summary'):
                    summary = BeautifulSoup(entry.summary, 'html.parser').get_text()[:200]
                
                article = NewsArticle(
                    title=entry.title,
                    url=entry.link,
                    summary=summary,
                    published=published,
                    source=source_name,
                )
                articles.append(article)
                
        except Exception as e:
            console.print(f"[red]RSS取得エラー ({source_name}): {e}[/red]")
        
        return articles
    
    def score_article(self, article: NewsArticle) -> int:
        """記事をスコアリング"""
        score = 50  # ベーススコア
        
        text = f"{article.title} {article.summary}".lower()
        
        for keyword, points in self.SCORE_KEYWORDS.items():
            if keyword.lower() in text:
                score += points
        
        # タイトルの長さ (短すぎ・長すぎは減点)
        title_len = len(article.title)
        if title_len < 20:
            score -= 10
        elif title_len > 100:
            score -= 5
        
        # スコアを0-100に正規化
        score = max(0, min(100, score))
        
        return score
    
    def fetch_full_article(self, url: str) -> Optional[str]:
        """記事本文を取得"""
        try:
            response = self.client.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # UPI の記事本文を取得
            article_body = soup.find('article') or soup.find('div', class_='article-body')
            
            if article_body:
                paragraphs = article_body.find_all('p')
                text = '\n'.join([p.get_text() for p in paragraphs])
                return text[:2000]  # 最大2000文字
            
            return None
            
        except Exception as e:
            console.print(f"[red]記事取得エラー: {e}[/red]")
            return None
    
    def fetch_top_news(self, limit: int = 5) -> list[NewsArticle]:
        """上位N件のニュースを取得"""
        
        console.print("[cyan]📰 ニュース取得中...[/cyan]")
        
        all_articles = []
        
        # 全RSSフィードから取得
        for source_name, feed_url in self.RSS_FEEDS.items():
            articles = self.fetch_rss(feed_url, source_name)
            all_articles.extend(articles)
            console.print(f"  {source_name}: {len(articles)}件")
        
        # スコアリング
        console.print("[cyan]📊 スコアリング中...[/cyan]")
        for article in all_articles:
            article.score = self.score_article(article)
        
        # スコア順にソート
        all_articles.sort(key=lambda x: x.score, reverse=True)
        
        # 上位N件を返す
        top_articles = all_articles[:limit]
        
        console.print(f"[green]✅ 上位{len(top_articles)}件を選出[/green]")
        
        return top_articles
    
    def format_for_discord(self, articles: list[NewsArticle]) -> str:
        """Discord用にフォーマット"""
        
        lines = ["📰 **今日のおもしろニュース候補:**\n"]
        
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        
        for i, article in enumerate(articles):
            emoji = emojis[i] if i < len(emojis) else f"{i+1}."
            
            # タイトルを日本語に簡易翻訳（後でAI翻訳に置き換え）
            title = article.title[:50]
            
            lines.append(f"{emoji} **{title}** (スコア: {article.score})")
            lines.append(f"   {article.summary[:80]}...")
            lines.append("")
        
        lines.append("番号で選択 / 「スキップ」で今日はパス")
        
        return "\n".join(lines)


# CLI用
if __name__ == "__main__":
    fetcher = OddNewsFetcher()
    articles = fetcher.fetch_top_news(5)
    
    print("\n" + "=" * 50)
    for i, article in enumerate(articles, 1):
        print(f"\n{i}. [{article.score}点] {article.title}")
        print(f"   {article.url}")
        print(f"   {article.summary[:100]}...")
    
    print("\n" + fetcher.format_for_discord(articles))
