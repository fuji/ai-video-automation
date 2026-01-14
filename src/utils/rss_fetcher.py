"""RSSフェッチャー - Yahoo!ニュース・NHK NEWS RSS取得"""

import feedparser
import ssl
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..logger import setup_logger

logger = setup_logger("rss_fetcher")


@dataclass
class RSSArticle:
    """RSS記事データ"""
    title: str
    link: str
    published: Optional[str] = None
    summary: str = ""
    source: str = ""
    category: str = ""


class RSSFetcher:
    """Yahoo!ニュース・NHK NEWS RSS取得"""

    # Yahoo!ニュース RSS
    YAHOO_RSS_BASE = "https://news.yahoo.co.jp/rss/topics/"
    YAHOO_CATEGORIES = {
        "top": "top-picks.xml",
        "domestic": "domestic.xml",
        "world": "world.xml",
        "business": "business.xml",
        "entertainment": "entertainment.xml",
        "sports": "sports.xml",
        "it": "it.xml",
        "science": "science.xml",
        "local": "local.xml",
    }

    # NHK NEWS RSS
    NHK_RSS_BASE = "https://www.nhk.or.jp/rss/news/"
    NHK_CATEGORIES = {
        "main": "cat0.xml",  # 主要ニュース
        "society": "cat1.xml",  # 社会
        "science": "cat3.xml",  # 科学・文化
        "politics": "cat4.xml",  # 政治
        "business": "cat5.xml",  # ビジネス
        "international": "cat6.xml",  # 国際
        "sports": "cat7.xml",  # スポーツ
    }

    def __init__(self):
        # SSL証明書の検証を無効化（開発環境用）
        self.ssl_context = ssl._create_unverified_context()
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        logger.info("RSSFetcher initialized")

    def fetch_feed(self, url: str) -> Optional[feedparser.FeedParserDict]:
        """RSSフィードを取得（SSL検証なし）

        Args:
            url: RSSフィードURL

        Returns:
            feedparser.FeedParserDict or None
        """
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": self.user_agent}
            )

            with urllib.request.urlopen(
                request,
                context=self.ssl_context,
                timeout=10
            ) as response:
                content = response.read()

            feed = feedparser.parse(content)
            return feed

        except Exception as e:
            logger.warning(f"RSS fetch error for {url}: {e}")
            return None

    def fetch_yahoo_news(
        self,
        category: str = "top",
        limit: int = 10,
    ) -> list[RSSArticle]:
        """Yahoo!ニュース RSS取得

        Args:
            category: カテゴリ（top, domestic, world, business, etc.）
            limit: 取得件数

        Returns:
            RSSArticleのリスト
        """
        rss_file = self.YAHOO_CATEGORIES.get(category, "top-picks.xml")
        url = self.YAHOO_RSS_BASE + rss_file

        logger.info(f"Fetching Yahoo! News RSS: {category}")

        feed = self.fetch_feed(url)

        if not feed:
            logger.error(f"Yahoo! News RSS fetch failed for {category}")
            return []

        if feed.bozo:
            logger.warning(f"RSS parse warning: {feed.bozo_exception}")

        articles = []
        for entry in feed.entries[:limit]:
            articles.append(RSSArticle(
                title=entry.get("title", ""),
                link=entry.get("link", ""),
                published=entry.get("published", ""),
                summary=entry.get("summary", ""),
                source="Yahoo!ニュース",
                category=category,
            ))

        logger.info(f"Fetched {len(articles)} articles from Yahoo! News")
        return articles

    def fetch_nhk_news(
        self,
        category: str = "main",
        limit: int = 10,
    ) -> list[RSSArticle]:
        """NHK NEWS RSS取得

        Args:
            category: カテゴリ（main, society, politics, etc.）
            limit: 取得件数

        Returns:
            RSSArticleのリスト
        """
        rss_file = self.NHK_CATEGORIES.get(category, "cat0.xml")
        url = self.NHK_RSS_BASE + rss_file

        logger.info(f"Fetching NHK NEWS RSS: {category}")

        feed = self.fetch_feed(url)

        if not feed:
            logger.error(f"NHK NEWS RSS fetch failed for {category}")
            return []

        if feed.bozo:
            logger.warning(f"RSS parse warning: {feed.bozo_exception}")

        articles = []
        for entry in feed.entries[:limit]:
            articles.append(RSSArticle(
                title=entry.get("title", ""),
                link=entry.get("link", ""),
                published=entry.get("published", ""),
                summary=entry.get("summary", entry.get("description", "")),
                source="NHK NEWS",
                category=category,
            ))

        logger.info(f"Fetched {len(articles)} articles from NHK NEWS")
        return articles

    def fetch_all_sources(
        self,
        limit_per_source: int = 10,
    ) -> list[RSSArticle]:
        """全ソースからニュース取得

        Args:
            limit_per_source: ソースあたりの取得件数

        Returns:
            RSSArticleのリスト（重複除去済み）
        """
        all_articles = []

        # Yahoo!ニュース（主要カテゴリ）
        for category in ["top", "domestic", "business", "it"]:
            articles = self.fetch_yahoo_news(category, limit=limit_per_source)
            all_articles.extend(articles)

        # NHK NEWS
        for category in ["main", "society", "business"]:
            articles = self.fetch_nhk_news(category, limit=limit_per_source)
            all_articles.extend(articles)

        # 重複除去
        seen_links = set()
        unique_articles = []
        for article in all_articles:
            if article.link not in seen_links:
                seen_links.add(article.link)
                unique_articles.append(article)

        logger.info(f"Total unique articles: {len(unique_articles)}")
        return unique_articles

    def search_news(
        self,
        keyword: str,
        limit: int = 10,
    ) -> list[RSSArticle]:
        """キーワードでニュース検索

        Args:
            keyword: 検索キーワード
            limit: 取得件数

        Returns:
            マッチしたRSSArticleのリスト
        """
        # 全ソースから取得
        all_articles = self.fetch_all_sources(limit_per_source=20)

        # キーワードマッチング
        keyword_lower = keyword.lower()
        filtered = [
            article for article in all_articles
            if keyword_lower in article.title.lower()
            or keyword_lower in article.summary.lower()
        ]

        logger.info(f"Found {len(filtered)} articles for keyword: {keyword}")
        return filtered[:limit]

    def get_latest_news(
        self,
        count: int = 10,
        categories: list[str] = None,
    ) -> list[RSSArticle]:
        """最新ニュース取得

        Args:
            count: 取得件数
            categories: 取得するカテゴリ（Noneで全て）

        Returns:
            RSSArticleのリスト
        """
        if categories is None:
            categories = ["top"]

        all_articles = []
        for category in categories:
            # Yahoo!優先
            articles = self.fetch_yahoo_news(category, limit=count)
            all_articles.extend(articles)

        # 重複除去
        seen_links = set()
        unique_articles = []
        for article in all_articles:
            if article.link not in seen_links:
                seen_links.add(article.link)
                unique_articles.append(article)

        return unique_articles[:count]


if __name__ == "__main__":
    # テスト実行
    fetcher = RSSFetcher()

    print("=== Yahoo! News (Top) ===")
    articles = fetcher.fetch_yahoo_news("top", limit=5)
    for a in articles:
        print(f"  - {a.title[:40]}...")

    print("\n=== NHK NEWS (Main) ===")
    articles = fetcher.fetch_nhk_news("main", limit=5)
    for a in articles:
        print(f"  - {a.title[:40]}...")

    print("\n=== Search Test ===")
    articles = fetcher.search_news("経済", limit=3)
    for a in articles:
        print(f"  - [{a.source}] {a.title[:40]}...")
