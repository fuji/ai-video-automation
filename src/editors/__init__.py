"""動画編集モジュール"""

# video_editor.py は削除済み（Remotion に移行）
from .news_graphics import NewsGraphicsCompositor, GraphicsResult
from .intro_outro import IntroOutroGenerator, IntroOutroConfig, add_fade_transition

__all__ = [
    "NewsGraphicsCompositor",
    "GraphicsResult",
    "IntroOutroGenerator",
    "IntroOutroConfig",
    "add_fade_transition",
]
