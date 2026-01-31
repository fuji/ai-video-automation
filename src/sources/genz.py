"""Gen Z related sources - relatable content for younger audiences."""
import aiohttp
import ssl
from datetime import datetime
from .base import NewsSource, Article, Category

# SSL verification skip for development
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


class GenZRedditSource(NewsSource):
    """Reddit Z世代向けコンテンツ"""
    
    SUBREDDITS = [
        "GenZ",
        "meirl", 
        "me_irl",
        "2meirl4meirl",
        "starterpacks",
        "suspiciouslyspecific",
    ]
    
    @property
    def name(self) -> str:
        return "Reddit GenZ"
    
    @property
    def category(self) -> Category:
        return Category.GENZ
    
    async def fetch(self, count: int = 10, **kwargs) -> list[Article]:
        """複数のZ世代向けSubredditから取得"""
        headers = {"User-Agent": "N1NewsBot/1.0"}
        all_articles = []
        
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        async with aiohttp.ClientSession(connector=connector) as session:
            for subreddit in self.SUBREDDITS:
                url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=5"
                
                try:
                    async with session.get(url, headers=headers) as response:
                        if response.status != 200:
                            continue
                        data = await response.json()
                    
                    for post in data.get("data", {}).get("children", []):
                        post_data = post.get("data", {})
                        
                        # NSFWを除外
                        if post_data.get("over_18"):
                            continue
                        
                        all_articles.append(Article(
                            title=post_data.get("title", ""),
                            url=f"https://reddit.com{post_data.get('permalink', '')}",
                            source=f"r/{subreddit}",
                            category=self.category,
                            summary=post_data.get("selftext", "")[:300] if post_data.get("selftext") else "",
                            score=post_data.get("score", 0),
                            published_at=datetime.fromtimestamp(post_data.get("created_utc", 0)),
                            image_url=post_data.get("thumbnail") if post_data.get("thumbnail", "").startswith("http") else None,
                            tags=["genz", subreddit.lower()],
                        ))
                except Exception:
                    continue
        
        # スコア順でソート
        all_articles.sort(key=lambda x: x.score, reverse=True)
        return all_articles[:count]


class TikTokTrendsSource(NewsSource):
    """TikTokトレンド（模擬 - 実際はスクレイピング困難）"""
    
    # TikTokトレンドのキュレーション（手動更新）
    TRENDS = [
        {
            "title": "「それな」で始まる会話、100%内容がない説",
            "summary": "Z世代の会話あるある。「それな」「わかる」「まじ」だけで会話が成立。",
            "tags": ["genz", "communication", "viral"],
        },
        {
            "title": "親に「ちょっと」と呼ばれた時の絶望感",
            "summary": "「ちょっと」と言われて行ったら1時間拘束される現象。",
            "tags": ["genz", "family", "relatable"],
        },
        {
            "title": "授業中に当てられた時の生存戦略",
            "summary": "目を合わせない、下を向く、トイレに行くフリ…全て無駄だった。",
            "tags": ["genz", "school", "relatable"],
        },
        {
            "title": "「了解です」vs「承知しました」論争",
            "summary": "上司へのメール、どっちが正解？Z世代を悩ませるビジネスマナー。",
            "tags": ["genz", "work", "communication"],
        },
        {
            "title": "寝る前の5分のスマホが3時間になる現象",
            "summary": "「ちょっとだけ」が永遠に続くショート動画の沼。",
            "tags": ["genz", "smartphone", "relatable"],
        },
    ]
    
    @property
    def name(self) -> str:
        return "Z世代あるある"
    
    @property
    def category(self) -> Category:
        return Category.GENZ
    
    async def fetch(self, count: int = 10, **kwargs) -> list[Article]:
        """Z世代あるあるネタを取得"""
        import random
        
        selected = random.sample(self.TRENDS, min(count, len(self.TRENDS)))
        
        articles = []
        for i, trend in enumerate(selected):
            articles.append(Article(
                title=trend["title"],
                url="",  # 元URLなし
                source=self.name,
                category=self.category,
                summary=trend["summary"],
                score=90 - i * 5,  # 順番でスコア付け
                published_at=datetime.now(),
                tags=trend.get("tags", []),
            ))
        
        return articles
