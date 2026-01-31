"""Trend sources - Google Trends, X (Twitter)."""
import aiohttp
import ssl
from datetime import datetime
from typing import Optional
from .base import NewsSource, Article, Category

# SSL verification skip for development
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


class GoogleTrendsSource(NewsSource):
    """Google Trends Daily Trends"""
    
    @property
    def name(self) -> str:
        return "Google Trends"
    
    @property
    def category(self) -> Category:
        return Category.TREND
    
    async def fetch(self, count: int = 10, geo: str = "JP") -> list[Article]:
        """Google Trendsから急上昇ワードを取得
        
        Args:
            count: 取得件数
            geo: 国コード (JP, US, etc.)
        """
        # Google Trends RSS feed
        url = f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo}"
        
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return []
                text = await response.text()
        
        # Simple XML parsing
        import re
        articles = []
        
        # Extract items from RSS
        items = re.findall(r'<item>(.*?)</item>', text, re.DOTALL)
        
        for item in items[:count]:
            title_match = re.search(r'<title>(.*?)</title>', item)
            link_match = re.search(r'<ht:news_item_url>(.*?)</ht:news_item_url>', item)
            traffic_match = re.search(r'<ht:approx_traffic>(.*?)</ht:approx_traffic>', item)
            snippet_match = re.search(r'<ht:news_item_snippet>(.*?)</ht:news_item_snippet>', item)
            
            if title_match:
                # トラフィック数をスコアに変換
                traffic = traffic_match.group(1) if traffic_match else "0"
                score = int(traffic.replace(",", "").replace("+", "").replace("K", "000").replace("M", "000000")) if traffic else 0
                
                articles.append(Article(
                    title=title_match.group(1),
                    url=link_match.group(1) if link_match else f"https://trends.google.com/trends/explore?q={title_match.group(1)}&geo={geo}",
                    source=self.name,
                    category=self.category,
                    summary=snippet_match.group(1) if snippet_match else "",
                    score=score,
                    published_at=datetime.now(),
                    tags=["trend", geo.lower()],
                ))
        
        return articles


class YahooNewsSource(NewsSource):
    """Yahoo!ニュース急上昇"""
    
    @property
    def name(self) -> str:
        return "Yahoo!ニュース"
    
    @property
    def category(self) -> Category:
        return Category.TREND
    
    async def fetch(self, count: int = 10) -> list[Article]:
        """Yahoo!ニュースからトレンド記事を取得"""
        url = "https://news.yahoo.co.jp/rss/topics/top-picks.xml"
        
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return []
                text = await response.text()
        
        import re
        articles = []
        
        items = re.findall(r'<item>(.*?)</item>', text, re.DOTALL)
        
        for item in items[:count]:
            title_match = re.search(r'<title>(.*?)</title>', item)
            link_match = re.search(r'<link>(.*?)</link>', item)
            desc_match = re.search(r'<description>(.*?)</description>', item)
            
            if title_match and link_match:
                articles.append(Article(
                    title=title_match.group(1),
                    url=link_match.group(1),
                    source=self.name,
                    category=self.category,
                    summary=desc_match.group(1) if desc_match else "",
                    score=0,
                    published_at=datetime.now(),
                    tags=["yahoo", "japan"],
                ))
        
        return articles
