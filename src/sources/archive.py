"""Archive source - historical news and "on this day" content."""
import aiohttp
import ssl
from datetime import datetime, date
from typing import Optional
from .base import NewsSource, Article, Category

# SSL verification skip for development
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


class WikipediaOnThisDaySource(NewsSource):
    """Wikipedia「この日の出来事」"""
    
    @property
    def name(self) -> str:
        return "Wikipedia この日の出来事"
    
    @property
    def category(self) -> Category:
        return Category.ARCHIVE
    
    async def fetch(self, count: int = 10, target_date: Optional[date] = None) -> list[Article]:
        """Wikipediaから「この日の出来事」を取得
        
        Args:
            count: 取得件数
            target_date: 対象日（Noneなら今日）
        """
        if target_date is None:
            target_date = date.today()
        
        # Wikipedia API for "On this day"
        month = target_date.month
        day = target_date.day
        
        # English Wikipedia API (more complete)
        url = f"https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/events/{month}/{day}"
        
        headers = {
            "User-Agent": "N1NewsBot/1.0",
            "Accept": "application/json",
        }
        
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return []
                data = await response.json()
        
        articles = []
        events = data.get("events", [])
        
        for event in events[:count]:
            year = event.get("year", "")
            text = event.get("text", "")
            pages = event.get("pages", [])
            
            # 最初のページからURL取得
            page_url = ""
            image_url = None
            if pages:
                page = pages[0]
                page_url = page.get("content_urls", {}).get("desktop", {}).get("page", "")
                if page.get("thumbnail"):
                    image_url = page["thumbnail"].get("source")
            
            articles.append(Article(
                title=f"【{year}年】{text[:100]}",
                url=page_url or f"https://en.wikipedia.org/wiki/{month}_{day}",
                source=self.name,
                category=self.category,
                summary=text,
                score=abs(datetime.now().year - int(year)) if year else 0,  # 古いほど高スコア
                published_at=datetime(int(year), month, day) if year else None,
                image_url=image_url,
                tags=["history", f"{month}/{day}"],
            ))
        
        return articles


class LegendaryNewsSource(NewsSource):
    """伝説のネタニュース（手動キュレーション）"""
    
    # 伝説のニュース集（追加可能）
    LEGENDARY_NEWS = [
        {
            "title": "オーストラリアで「エミュー戦争」勃発、軍が敗北",
            "url": "https://en.wikipedia.org/wiki/Emu_War",
            "summary": "1932年、オーストラリア軍がエミューの大群と戦い、敗北した実話。機関銃を持った兵士がエミューに負けた。",
            "year": 1932,
            "tags": ["australia", "animals", "war", "legendary"],
        },
        {
            "title": "ロンドン市長選に「猫」が立候補",
            "url": "https://en.wikipedia.org/wiki/Larry_(cat)",
            "summary": "イギリス首相官邸の「ネズミ捕獲長」ラリーが話題に。公式の役職を持つ猫。",
            "year": 2011,
            "tags": ["uk", "cats", "politics", "legendary"],
        },
        {
            "title": "NASAが宇宙でペンを使うため数百万ドルを投資、ソ連は鉛筆を使った",
            "url": "https://www.snopes.com/fact-check/the-write-stuff/",
            "summary": "有名な都市伝説だが、実際はFisher社が自費で開発。宇宙ペンの真実。",
            "year": 1965,
            "tags": ["space", "nasa", "legendary", "myth"],
        },
        {
            "title": "日本の「忠犬ハチ公」、主人を9年間待ち続ける",
            "url": "https://en.wikipedia.org/wiki/Hachik%C5%8D",
            "summary": "渋谷駅で亡くなった主人を9年間待ち続けた秋田犬ハチ公の物語。",
            "year": 1935,
            "tags": ["japan", "dogs", "loyalty", "legendary"],
        },
        {
            "title": "スウェーデンで「タコ」が選挙予測、的中率8割",
            "url": "https://en.wikipedia.org/wiki/Paul_the_Octopus",
            "summary": "2010年W杯でパウル君が試合結果を次々と的中させ、世界中で話題に。",
            "year": 2010,
            "tags": ["animals", "sports", "prediction", "legendary"],
        },
        {
            "title": "男性が40年間「石」だと思っていたものが隕石と判明、数億円の価値",
            "url": "https://www.bbc.com/news/world-australia-49687399",
            "summary": "オーストラリアの男性が玄関に置いていた石が、実は46億年前の隕石だった。",
            "year": 2019,
            "tags": ["australia", "space", "discovery", "legendary"],
        },
        {
            "title": "イギリスの町で「ラウンドアバウト愛好家協会」が発足",
            "url": "https://en.wikipedia.org/wiki/UK_Roundabout_Appreciation_Society",
            "summary": "交差点のラウンドアバウトを愛でる協会が実在。メンバー数千人。",
            "year": 2003,
            "tags": ["uk", "hobby", "weird", "legendary"],
        },
        {
            "title": "カナダの町が「UFO着陸パッド」を建設",
            "url": "https://en.wikipedia.org/wiki/St._Paul,_Alberta",
            "summary": "アルバータ州セントポールに公式UFO着陸パッドが存在。世界初。",
            "year": 1967,
            "tags": ["canada", "ufo", "weird", "legendary"],
        },
    ]
    
    @property
    def name(self) -> str:
        return "伝説のニュース"
    
    @property
    def category(self) -> Category:
        return Category.ARCHIVE
    
    async def fetch(self, count: int = 10, **kwargs) -> list[Article]:
        """伝説のニュースをランダムに取得"""
        import random
        
        selected = random.sample(self.LEGENDARY_NEWS, min(count, len(self.LEGENDARY_NEWS)))
        
        articles = []
        for news in selected:
            articles.append(Article(
                title=news["title"],
                url=news["url"],
                source=self.name,
                category=self.category,
                summary=news["summary"],
                score=100,  # 伝説級は高スコア
                published_at=datetime(news["year"], 1, 1) if news.get("year") else None,
                tags=news.get("tags", []),
            ))
        
        return articles
