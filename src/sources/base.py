"""Base classes for news sources."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class Category(str, Enum):
    """ニュースカテゴリ"""
    BUZZ = "buzz"           # バズ（Reddit等）
    ARCHIVE = "archive"     # 過去ニュース
    TREND = "trend"         # トレンド（X, Google）
    ANIMALS = "animals"     # 動物・ペット系
    GENZ = "genz"           # Z世代あるある


@dataclass
class Article:
    """記事データ"""
    title: str
    url: str
    source: str
    category: Category
    summary: str = ""
    score: int = 0  # バズスコア（Upvote, いいね等）
    published_at: Optional[datetime] = None
    image_url: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "category": self.category.value,
            "summary": self.summary,
            "score": self.score,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "image_url": self.image_url,
            "tags": self.tags,
        }


class NewsSource(ABC):
    """ニュースソースの基底クラス"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """ソース名"""
        pass
    
    @property
    @abstractmethod
    def category(self) -> Category:
        """カテゴリ"""
        pass
    
    @abstractmethod
    async def fetch(self, count: int = 10, **kwargs) -> list[Article]:
        """記事を取得"""
        pass
