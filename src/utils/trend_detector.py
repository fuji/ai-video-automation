"""トレンド検知モジュール - Google Trends + Yahoo!/NHK RSS 統合（完全無料）"""

from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass

from pytrends.request import TrendReq

from .rss_fetcher import RSSFetcher, RSSArticle
from ..logger import setup_logger

logger = setup_logger("trend_detector")


@dataclass
class TrendingNews:
    """トレンドニュース情報"""
    title: str
    url: str
    description: str = ""
    source: str = ""
    published_at: Optional[datetime] = None
    image_url: Optional[str] = None
    score: int = 0
    category: str = ""
    trending_keyword: str = ""  # マッチしたトレンドキーワード
    trend_rank: int = 0  # トレンドランク

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "description": self.description,
            "source": self.source,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "image_url": self.image_url,
            "score": self.score,
            "category": self.category,
            "trending_keyword": self.trending_keyword,
            "trend_rank": self.trend_rank,
        }


class TrendDetector:
    """Google Trends + RSS を使用したトレンド検知（完全無料）"""

    def __init__(self):
        # タイムアウトとリトライ設定で404エラー対策
        self.pytrends = TrendReq(
            hl="ja-JP",
            tz=540,  # Japan timezone
            timeout=(5, 10),  # (connect, read) タイムアウト
            retries=2,
            backoff_factor=0.5,
        )
        self.rss_fetcher = RSSFetcher()
        self._trends_available = True  # Google Trendsの可用性フラグ

        logger.info("TrendDetector initialized (Google Trends + RSS)")

    def get_trending_keywords(self, limit: int = 20) -> list[str]:
        """Google Trendsから話題のキーワードを取得

        Args:
            limit: 取得数

        Returns:
            キーワードのリスト
        """
        if not self._trends_available:
            logger.debug("Google Trends marked as unavailable, skipping")
            return []

        try:
            trending = self.pytrends.trending_searches(pn="japan")
            keywords = trending[0].tolist()[:limit]
            logger.info(f"Got {len(keywords)} trending keywords from Google Trends")
            return keywords
        except Exception as e:
            error_str = str(e).lower()
            if "404" in error_str or "response" in error_str:
                logger.warning(f"Google Trends 404 error (API may be temporarily unavailable): {e}")
                self._trends_available = False
            else:
                logger.error(f"Failed to get trending keywords: {e}")
            return []

    def reset_trends_availability(self):
        """Google Trendsの可用性フラグをリセット（手動リトライ用）"""
        self._trends_available = True
        logger.info("Google Trends availability flag reset")

    def is_trends_available(self) -> bool:
        """Google Trendsが利用可能かどうか"""
        return self._trends_available

    def get_realtime_trends(self) -> list[dict]:
        """リアルタイムトレンドを取得

        Returns:
            トレンド情報のリスト
        """
        if not self._trends_available:
            logger.debug("Google Trends marked as unavailable, skipping realtime trends")
            return []

        try:
            trending = self.pytrends.realtime_trending_searches(pn="JP")
            results = []

            for _, row in trending.head(10).iterrows():
                results.append({
                    "title": row.get("title", ""),
                    "news_items": row.get("newsItem", []),
                    "traffic": row.get("formattedTraffic", ""),
                })

            logger.info(f"Got {len(results)} realtime trends")
            return results

        except Exception as e:
            error_str = str(e).lower()
            if "404" in error_str or "response" in error_str:
                logger.warning(f"Google Trends 404 error: {e}")
                self._trends_available = False
            else:
                logger.error(f"Failed to get realtime trends: {e}")
            return []

    def _get_rss_only_news(self, limit: int = 10) -> list[TrendingNews]:
        """RSSのみでニュースを取得（Google Trendsフォールバック用）

        Args:
            limit: 取得数

        Returns:
            TrendingNewsのリスト
        """
        logger.info("Using RSS-only mode (Google Trends unavailable)")
        all_news = []

        # 各カテゴリから最新ニュースを取得
        categories = ["top", "domestic", "business", "it", "science", "world"]
        for category in categories:
            articles = self.rss_fetcher.get_latest_news(
                count=5,
                categories=[category],
            )
            for article in articles:
                news = self._article_to_news(article)
                all_news.append(news)

        # 重複除去
        seen_urls = set()
        unique_news = []
        for news in all_news:
            if news.url not in seen_urls:
                seen_urls.add(news.url)
                unique_news.append(news)

        logger.info(f"Got {len(unique_news)} news items from RSS only")
        return unique_news[:limit * 2]

    def get_trending_news(
        self,
        limit: int = 10,
        use_trends: bool = True,
    ) -> list[TrendingNews]:
        """トレンドニュースを取得（Google Trends + RSS）

        Args:
            limit: 取得数
            use_trends: Google Trendsキーワードを使用

        Returns:
            TrendingNewsのリスト
        """
        all_news = []

        if use_trends and self._trends_available:
            # 1. Google Trendsでバズキーワード取得
            keywords = self.get_trending_keywords(limit=10)

            if not keywords:
                # Google Trendsが失敗した場合、RSSのみモードにフォールバック
                logger.warning("Google Trends failed, falling back to RSS-only mode")
                self._trends_available = False
                return self._get_rss_only_news(limit)

            # 2. 各キーワードでRSS検索
            for rank, keyword in enumerate(keywords[:5], 1):
                articles = self.rss_fetcher.search_news(keyword, limit=3)

                for article in articles:
                    news = self._article_to_news(article)
                    news.trending_keyword = keyword
                    news.trend_rank = rank
                    all_news.append(news)
        elif not self._trends_available:
            # Google Trendsが利用不可の場合はRSSのみ
            return self._get_rss_only_news(limit)

        # 3. 最新ニュースも追加
        latest = self.rss_fetcher.get_latest_news(
            count=10,
            categories=["top", "domestic", "business"],
        )
        for article in latest:
            news = self._article_to_news(article)
            all_news.append(news)

        # 4. 重複除去
        seen_urls = set()
        unique_news = []
        for news in all_news:
            if news.url not in seen_urls:
                seen_urls.add(news.url)
                unique_news.append(news)

        logger.info(f"Got {len(unique_news)} unique news items")
        return unique_news[:limit * 2]  # スコアリング用に多めに返す

    def _article_to_news(self, article: RSSArticle) -> TrendingNews:
        """RSSArticleをTrendingNewsに変換"""
        return TrendingNews(
            title=article.title,
            url=article.link,
            description=article.summary,
            source=article.source,
            category=article.category,
        )

    def score_news(self, news_list: list[TrendingNews]) -> list[TrendingNews]:
        """ニュースをスコアリング（話題性 × 動画適性）

        Args:
            news_list: ニュースリスト

        Returns:
            スコア付きニュースリスト（降順ソート）
        """
        for news in news_list:
            score = 0

            # 1. トレンドランクスコア（最大50点）
            if news.trend_rank > 0:
                score += (11 - news.trend_rank) * 5  # 1位=50, 2位=45, ...

            # 2. タイトル適性スコア（最大30点）
            title_len = len(news.title)
            if 15 <= title_len <= 35:
                score += 30  # 最適な長さ
            elif 10 <= title_len <= 50:
                score += 20
            elif title_len < 60:
                score += 10

            # 3. 説明文の有無（最大10点）
            if news.description and len(news.description) > 50:
                score += 10
            elif news.description:
                score += 5

            # 4. ソースの信頼性ボーナス（最大10点）
            trusted_sources = [
                "Yahoo!ニュース", "NHK", "朝日新聞", "読売新聞",
                "毎日新聞", "日経", "共同通信", "時事通信",
            ]
            if any(s in news.source for s in trusted_sources):
                score += 10

            # 5. カテゴリボーナス（動画向けカテゴリ）
            video_friendly = ["top", "domestic", "business", "it", "science"]
            if news.category in video_friendly:
                score += 5

            news.score = score

        # スコア降順でソート
        sorted_news = sorted(news_list, key=lambda x: x.score, reverse=True)
        logger.info(f"Scored {len(sorted_news)} news items")

        return sorted_news

    def get_best_news(
        self,
        count: int = 1,
        use_trends: bool = True,
    ) -> list[TrendingNews]:
        """動画化に最適なニュースを取得

        Args:
            count: 取得数
            use_trends: Google Trendsを使用

        Returns:
            スコア上位のニュースリスト
        """
        # ニュース取得
        news_list = self.get_trending_news(limit=count * 3, use_trends=use_trends)

        # スコアリング
        scored = self.score_news(news_list)

        # 上位を返す
        best_news = scored[:count]
        logger.info(f"Selected {len(best_news)} best news for video")

        for i, news in enumerate(best_news, 1):
            keyword_info = f" (Trend: {news.trending_keyword})" if news.trending_keyword else ""
            logger.info(f"  {i}. [{news.score}pt] {news.title[:40]}...{keyword_info}")

        return best_news

    def get_news_by_keyword(
        self,
        keyword: str,
        limit: int = 5,
    ) -> list[TrendingNews]:
        """キーワードでニュースを検索

        Args:
            keyword: 検索キーワード
            limit: 取得数

        Returns:
            TrendingNewsのリスト
        """
        articles = self.rss_fetcher.search_news(keyword, limit=limit)

        news_list = []
        for article in articles:
            news = self._article_to_news(article)
            news.trending_keyword = keyword
            news_list.append(news)

        # スコアリングして返す
        return self.score_news(news_list)[:limit]


if __name__ == "__main__":
    # テスト実行
    detector = TrendDetector()

    print("=== Google Trends Keywords ===")
    keywords = detector.get_trending_keywords(5)
    for i, keyword in enumerate(keywords, 1):
        print(f"  {i}. {keyword}")

    print("\n=== Best News for Video ===")
    news = detector.get_best_news(3)
    for n in news:
        print(f"\n  [{n.score}pt] {n.title}")
        print(f"    Source: {n.source}")
        if n.trending_keyword:
            print(f"    Trend Keyword: {n.trending_keyword} (rank {n.trend_rank})")
        print(f"    URL: {n.url[:60]}...")
