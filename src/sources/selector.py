"""News Selector - カテゴリから記事を選定"""
import asyncio
from datetime import date
from typing import Optional
from rich.console import Console
from rich.table import Table

from .base import Category, Article
from .reddit import (
    NotTheOnionSource,
    UpliftingNewsSource,
    AnimalsBeingDerpsSource,
    AwwSource,
    RarePuppersSource,
    CatsSource,
)
from .trends import GoogleTrendsSource, YahooNewsSource
from .archive import WikipediaOnThisDaySource, LegendaryNewsSource
from .genz import GenZRedditSource, TikTokTrendsSource


console = Console()


class NewsSelector:
    """ニュースセレクター"""
    
    # カテゴリ別ソース
    SOURCES = {
        Category.BUZZ: [
            NotTheOnionSource(),
            UpliftingNewsSource(),
        ],
        Category.ANIMALS: [
            AnimalsBeingDerpsSource(),
            AwwSource(),
            RarePuppersSource(),
            CatsSource(),
        ],
        Category.TREND: [
            GoogleTrendsSource(),
            YahooNewsSource(),
        ],
        Category.ARCHIVE: [
            WikipediaOnThisDaySource(),
            LegendaryNewsSource(),
        ],
        Category.GENZ: [
            GenZRedditSource(),
            TikTokTrendsSource(),
        ],
    }
    
    @classmethod
    async def fetch_by_category(
        cls,
        category: Category,
        count: int = 10,
        **kwargs
    ) -> list[Article]:
        """カテゴリ別に記事を取得"""
        sources = cls.SOURCES.get(category, [])
        if not sources:
            return []
        
        all_articles = []
        
        for source in sources:
            try:
                articles = await source.fetch(count=count // len(sources) + 1, **kwargs)
                all_articles.extend(articles)
            except Exception as e:
                console.print(f"[yellow]⚠️ {source.name}: {e}[/yellow]")
        
        # スコア順でソート
        all_articles.sort(key=lambda x: x.score, reverse=True)
        return all_articles[:count]
    
    @classmethod
    async def fetch_all(cls, count_per_category: int = 5) -> dict[Category, list[Article]]:
        """全カテゴリから記事を取得"""
        results = {}
        
        for category in Category:
            results[category] = await cls.fetch_by_category(category, count_per_category)
        
        return results
    
    @classmethod
    def display_articles(cls, articles: list[Article], title: str = "記事リスト"):
        """記事をテーブル表示"""
        table = Table(title=title)
        table.add_column("No", style="cyan", width=4)
        table.add_column("タイトル", style="white", max_width=50)
        table.add_column("ソース", style="green", width=20)
        table.add_column("スコア", style="yellow", width=8)
        
        for i, article in enumerate(articles, 1):
            table.add_row(
                str(i),
                article.title[:50] + "..." if len(article.title) > 50 else article.title,
                article.source,
                str(article.score),
            )
        
        console.print(table)


async def main():
    """CLI entrypoint"""
    import argparse
    
    parser = argparse.ArgumentParser(description="ニュースセレクター")
    parser.add_argument(
        "--type", "-t",
        choices=["buzz", "animals", "trend", "archive", "genz", "all"],
        default="buzz",
        help="カテゴリ"
    )
    parser.add_argument("--count", "-c", type=int, default=10, help="取得件数")
    parser.add_argument("--date", "-d", help="日付 (MM-DD形式、archiveのみ)")
    parser.add_argument("--json", "-j", action="store_true", help="JSON出力")
    
    args = parser.parse_args()
    
    if args.type == "all":
        results = await NewsSelector.fetch_all(args.count)
        for category, articles in results.items():
            if articles:
                console.print(f"\n[bold cyan]📁 {category.value.upper()}[/bold cyan]")
                NewsSelector.display_articles(articles, f"{category.value}")
    else:
        category = Category(args.type)
        
        kwargs = {}
        if args.date and category == Category.ARCHIVE:
            month, day = map(int, args.date.split("-"))
            kwargs["target_date"] = date(2024, month, day)
        
        articles = await NewsSelector.fetch_by_category(category, args.count, **kwargs)
        
        if args.json:
            import json
            print(json.dumps([a.to_dict() for a in articles], ensure_ascii=False, indent=2))
        else:
            NewsSelector.display_articles(articles, f"{category.value.upper()}")


if __name__ == "__main__":
    asyncio.run(main())
