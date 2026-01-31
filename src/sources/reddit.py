"""Reddit source for buzz and animal news."""
import aiohttp
import ssl
from datetime import datetime
from .base import NewsSource, Article, Category

# SSL verification skip for development
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


class RedditSource(NewsSource):
    """Reddit API source"""
    
    def __init__(self, subreddit: str, category: Category = Category.BUZZ):
        self.subreddit = subreddit
        self._category = category
        self.base_url = f"https://www.reddit.com/r/{subreddit}"
    
    @property
    def name(self) -> str:
        return f"Reddit r/{self.subreddit}"
    
    @property
    def category(self) -> Category:
        return self._category
    
    async def fetch(self, count: int = 10, sort: str = "hot", time: str = "day") -> list[Article]:
        """Redditから記事を取得
        
        Args:
            count: 取得件数
            sort: hot, new, top, rising
            time: hour, day, week, month, year, all (sortがtopの時のみ)
        """
        url = f"{self.base_url}/{sort}.json?limit={count}&t={time}"
        headers = {"User-Agent": "N1NewsBot/1.0"}
        
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return []
                data = await response.json()
        
        articles = []
        for post in data.get("data", {}).get("children", []):
            post_data = post.get("data", {})
            
            # 自己投稿やNSFWを除外
            if post_data.get("is_self") or post_data.get("over_18"):
                continue
            
            articles.append(Article(
                title=post_data.get("title", ""),
                url=post_data.get("url", ""),
                source=self.name,
                category=self.category,
                summary=post_data.get("selftext", "")[:500] if post_data.get("selftext") else "",
                score=post_data.get("score", 0),
                published_at=datetime.fromtimestamp(post_data.get("created_utc", 0)),
                image_url=post_data.get("thumbnail") if post_data.get("thumbnail", "").startswith("http") else None,
                tags=[post_data.get("link_flair_text")] if post_data.get("link_flair_text") else [],
            ))
        
        return articles[:count]


# プリセット
class NotTheOnionSource(RedditSource):
    """r/nottheonion - 現実なのにジョークみたいなニュース"""
    def __init__(self):
        super().__init__("nottheonion", Category.BUZZ)


class UpliftingNewsSource(RedditSource):
    """r/UpliftingNews - 心温まるニュース"""
    def __init__(self):
        super().__init__("UpliftingNews", Category.BUZZ)


class AnimalsBeingDerpsSource(RedditSource):
    """r/AnimalsBeingDerps - おもしろ動物"""
    def __init__(self):
        super().__init__("AnimalsBeingDerps", Category.ANIMALS)


class AwwSource(RedditSource):
    """r/aww - かわいい動物"""
    def __init__(self):
        super().__init__("aww", Category.ANIMALS)


class RarePuppersSource(RedditSource):
    """r/rarepuppers - 犬"""
    def __init__(self):
        super().__init__("rarepuppers", Category.ANIMALS)


class CatsSource(RedditSource):
    """r/cats - 猫"""
    def __init__(self):
        super().__init__("cats", Category.ANIMALS)
