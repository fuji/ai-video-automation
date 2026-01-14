"""ニューススクレイピングモジュール - 記事本文抽出"""

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    from newspaper import Article
    HAS_NEWSPAPER = True
except ImportError:
    HAS_NEWSPAPER = False

from ..logger import setup_logger

logger = setup_logger("news_scraper")


@dataclass
class ScrapedArticle:
    """スクレイピングした記事情報"""
    url: str
    title: str = ""
    text: str = ""
    summary: str = ""
    authors: list[str] = field(default_factory=list)
    publish_date: Optional[str] = None
    top_image: Optional[str] = None
    images: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    source_domain: str = ""
    word_count: int = 0
    read_time_seconds: int = 0

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "summary": self.summary,
            "authors": self.authors,
            "publish_date": self.publish_date,
            "top_image": self.top_image,
            "images": self.images,
            "keywords": self.keywords,
            "source_domain": self.source_domain,
            "word_count": self.word_count,
            "read_time_seconds": self.read_time_seconds,
        }


class NewsScraper:
    """ニュース記事スクレイピング"""

    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})
        logger.info("NewsScraper initialized")

    def scrape(self, url: str) -> ScrapedArticle:
        """URLから記事をスクレイピング

        Args:
            url: 記事URL

        Returns:
            ScrapedArticle
        """
        logger.info(f"Scraping: {url}")

        # newspaper3kが利用可能な場合は優先使用
        if HAS_NEWSPAPER:
            try:
                return self._scrape_with_newspaper(url)
            except Exception as e:
                logger.warning(f"newspaper3k failed, falling back: {e}")

        # フォールバック: BeautifulSoup
        return self._scrape_with_bs4(url)

    def _scrape_with_newspaper(self, url: str) -> ScrapedArticle:
        """newspaper3kでスクレイピング"""
        article = Article(url, language="ja")
        article.download()
        article.parse()

        # NLPで要約とキーワード抽出
        try:
            article.nlp()
            summary = article.summary
            keywords = article.keywords
        except Exception:
            summary = ""
            keywords = []

        # 読了時間計算（日本語: 約400文字/分）
        text = article.text or ""
        word_count = len(text)
        read_time = int(word_count / 400 * 60)

        scraped = ScrapedArticle(
            url=url,
            title=article.title or "",
            text=text,
            summary=summary,
            authors=list(article.authors),
            publish_date=str(article.publish_date) if article.publish_date else None,
            top_image=article.top_image,
            images=list(article.images)[:5],
            keywords=keywords[:10],
            source_domain=urlparse(url).netloc,
            word_count=word_count,
            read_time_seconds=read_time,
        )

        logger.info(f"Scraped: {scraped.title[:50]}... ({scraped.word_count} chars)")
        return scraped

    def _scrape_with_bs4(self, url: str) -> ScrapedArticle:
        """BeautifulSoupでスクレイピング（フォールバック）"""
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            response.encoding = response.apparent_encoding

            soup = BeautifulSoup(response.text, "lxml")

            # タイトル取得
            title = ""
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text().strip()

            # OGタイトルを優先
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = og_title["content"]

            # 本文抽出
            text = self._extract_article_text(soup)

            # 画像取得
            top_image = None
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                top_image = og_image["content"]

            # 説明取得
            summary = ""
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                summary = og_desc["content"]

            # 読了時間計算
            word_count = len(text)
            read_time = int(word_count / 400 * 60)

            scraped = ScrapedArticle(
                url=url,
                title=title,
                text=text,
                summary=summary,
                top_image=top_image,
                source_domain=urlparse(url).netloc,
                word_count=word_count,
                read_time_seconds=read_time,
            )

            logger.info(f"Scraped (BS4): {scraped.title[:50]}... ({scraped.word_count} chars)")
            return scraped

        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            return ScrapedArticle(url=url)

    def _extract_article_text(self, soup: BeautifulSoup) -> str:
        """記事本文を抽出"""
        # 不要な要素を削除
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()

        # 記事本文を探す（一般的なセレクター）
        article_selectors = [
            "article",
            '[class*="article"]',
            '[class*="content"]',
            '[class*="entry"]',
            '[class*="post"]',
            "main",
            '[role="main"]',
        ]

        for selector in article_selectors:
            article = soup.select_one(selector)
            if article:
                # 段落を抽出
                paragraphs = article.find_all("p")
                if paragraphs:
                    text = "\n".join(p.get_text().strip() for p in paragraphs if p.get_text().strip())
                    if len(text) > 100:  # 最低100文字
                        return self._clean_text(text)

        # フォールバック: bodyから全テキスト
        body = soup.find("body")
        if body:
            text = body.get_text(separator="\n")
            return self._clean_text(text)

        return ""

    def _clean_text(self, text: str) -> str:
        """テキストをクリーンアップ"""
        # 連続空白を単一に
        text = re.sub(r"\s+", " ", text)

        # 改行の正規化
        text = re.sub(r"\n\s*\n", "\n\n", text)

        # 前後の空白削除
        text = text.strip()

        return text

    def extract_key_sentences(self, text: str, count: int = 5) -> list[str]:
        """重要な文を抽出

        Args:
            text: 本文
            count: 抽出数

        Returns:
            重要文のリスト
        """
        if not text:
            return []

        # 文に分割（日本語対応）
        sentences = re.split(r'[。！？\n]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

        if len(sentences) <= count:
            return sentences

        # スコアリング（長さと位置）
        scored = []
        for i, sentence in enumerate(sentences):
            score = 0

            # 長さスコア（20-60文字が最適）
            length = len(sentence)
            if 20 <= length <= 60:
                score += 10
            elif 15 <= length <= 80:
                score += 5

            # 位置スコア（冒頭と末尾を重視）
            if i < 3:
                score += 5
            if i >= len(sentences) - 2:
                score += 3

            scored.append((score, sentence))

        # スコア順にソートして上位を返す
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:count]]


if __name__ == "__main__":
    # テスト実行
    scraper = NewsScraper()

    # テストURL（NHKニュース）
    test_url = "https://www3.nhk.or.jp/news/"

    print("=== News Scraper Test ===")
    try:
        article = scraper.scrape(test_url)
        print(f"Title: {article.title}")
        print(f"Word count: {article.word_count}")
        print(f"Read time: {article.read_time_seconds}s")
        print(f"Summary: {article.summary[:100]}...")

        print("\n=== Key Sentences ===")
        key_sentences = scraper.extract_key_sentences(article.text, 3)
        for i, s in enumerate(key_sentences, 1):
            print(f"  {i}. {s}")
    except Exception as e:
        print(f"Error: {e}")
