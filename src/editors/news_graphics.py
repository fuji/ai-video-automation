"""ニュースグラフィック合成モジュール - TV ニュース番組風"""

from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import os

from ..config import IMAGES_DIR, OUTPUT_DIR
from ..logger import setup_logger

logger = setup_logger("news_graphics")

# アセットディレクトリ
ASSETS_DIR = OUTPUT_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class GraphicsResult:
    """グラフィック合成結果"""
    success: bool
    output_path: Optional[str] = None
    error_message: Optional[str] = None


class NewsGraphicsCompositor:
    """TV ニュース番組風グラフィックを画像に合成"""

    # カラーパレット（TV ニュース風）
    COLORS = {
        # メインカラー
        "breaking_red": (200, 30, 30),       # BREAKING NEWS の赤
        "header_red": (180, 20, 20),         # ヘッダー背景の濃い赤
        "live_red": (220, 40, 40),           # LIVE の赤
        
        # アクセント
        "accent_blue": (0, 90, 180),         # 青いアクセント
        "accent_yellow": (255, 200, 0),      # 黄色アクセント
        
        # 背景
        "banner_dark": (30, 30, 35),         # 濃いグレー背景
        "banner_black": (15, 15, 20),        # ほぼ黒
        "gradient_dark": (40, 40, 50),       # グラデーション用
        
        # テキスト
        "text_white": (255, 255, 255),
        "text_light": (230, 230, 230),
        "text_yellow": (255, 220, 50),       # 強調用の黄色テキスト
    }

    def __init__(self, channel_name: str = "NEWS CHANNEL"):
        """
        Args:
            channel_name: チャンネル名（後で変更可能）
        """
        self.channel_name = channel_name
        self.font_path = self._find_font()
        self.bold_font_path = self._find_bold_font()
        logger.info(f"NewsGraphicsCompositor initialized (channel: {channel_name})")

    def set_channel_name(self, name: str):
        """チャンネル名を変更"""
        self.channel_name = name
        logger.info(f"Channel name updated: {name}")

    def _find_font(self) -> Optional[str]:
        """使用可能なフォントを探す"""
        font_paths = [
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        
        for path in font_paths:
            if os.path.exists(path):
                return path
        return None

    def _find_bold_font(self) -> Optional[str]:
        """太字フォントを探す"""
        font_paths = [
            "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/Library/Fonts/Arial Bold.ttf",
        ]
        
        for path in font_paths:
            if os.path.exists(path):
                return path
        return self.font_path

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        """フォントを取得"""
        try:
            path = self.bold_font_path if bold else self.font_path
            if path:
                return ImageFont.truetype(path, size)
        except Exception as e:
            logger.warning(f"Font load failed: {e}")
        return ImageFont.load_default()

    def add_tv_news_overlay(
        self,
        image_path: str,
        headline: str,
        sub_headline: str = "",
        is_breaking: bool = True,
        output_path: Optional[str] = None,
    ) -> GraphicsResult:
        """TV ニュース番組風のフルオーバーレイを追加
        
        Args:
            image_path: 入力画像パス
            headline: メインヘッドライン（大きく表示）
            sub_headline: サブヘッドライン（小さく表示）
            is_breaking: BREAKING NEWS バナーを表示
            output_path: 出力パス
        """
        try:
            img = Image.open(image_path).convert("RGBA")
            width, height = img.size
            
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            
            # === 1. チャンネルロゴ（右上） ===
            logo_margin = int(width * 0.015)
            logo_font_size = int(height * 0.032)
            logo_font = self._get_font(logo_font_size, bold=True)
            
            # FJ を詰めて描画するため、文字幅を計算
            # "FJ" の部分は詰める、" News 24" はそのまま
            fj_text = "FJ"
            rest_text = " News 24"
            
            # 各文字の幅を取得
            f_bbox = draw.textbbox((0, 0), "F", font=logo_font)
            j_bbox = draw.textbbox((0, 0), "J", font=logo_font)
            rest_bbox = draw.textbbox((0, 0), rest_text, font=logo_font)
            
            f_w = f_bbox[2] - f_bbox[0]
            j_w = j_bbox[2] - j_bbox[0]
            rest_w = rest_bbox[2] - rest_bbox[0]
            
            # FJ の letter-spacing を詰める（-30%くらい）
            fj_spacing = int(f_w * -0.15)
            fj_total_w = f_w + j_w + fj_spacing
            
            total_text_w = fj_total_w + rest_w
            text_h = f_bbox[3] - f_bbox[1]
            
            # 上下左右均等パディング
            padding = int(logo_font_size * 0.35)
            logo_w = total_text_w + padding * 2
            logo_h = text_h + padding * 2
            
            logo_x = width - logo_w - logo_margin
            logo_y = logo_margin
            
            # 赤い背景
            draw.rectangle(
                [(logo_x, logo_y), (logo_x + logo_w, logo_y + logo_h)],
                fill=(*self.COLORS["breaking_red"], 245)
            )
            
            # テキスト描画位置（縦中央）
            text_y = logo_y + (logo_h - text_h) // 2
            current_x = logo_x + padding
            
            # F を描画
            draw.text((current_x, text_y), "F", font=logo_font, fill=self.COLORS["text_white"])
            current_x += f_w + fj_spacing
            
            # J を描画
            draw.text((current_x, text_y), "J", font=logo_font, fill=self.COLORS["text_white"])
            current_x += j_w
            
            # " News 24" を描画
            draw.text((current_x, text_y), rest_text, font=logo_font, fill=self.COLORS["text_white"])
            
            # === 2. 下部のニュースバナー ===
            # BREAKING NEWS ラベル + ヘッドラインを含む領域
            total_banner_h = int(height * 0.18) if is_breaking else int(height * 0.14)
            main_banner_y = height - total_banner_h - int(height * 0.08)
            
            # BREAKING NEWS ラベル（ヘッドラインの上）
            breaking_h = int(height * 0.045) if is_breaking else 0
            headline_area_y = main_banner_y + breaking_h
            headline_area_h = total_banner_h - breaking_h
            
            if is_breaking:
                # BREAKING NEWS 赤いバー（左寄せ）
                breaking_font_size = int(breaking_h * 0.7)
                breaking_font = self._get_font(breaking_font_size, bold=True)
                breaking_text = "BREAKING NEWS"
                breaking_bbox = draw.textbbox((0, 0), breaking_text, font=breaking_font)
                breaking_w = breaking_bbox[2] - breaking_bbox[0] + 30
                
                draw.rectangle(
                    [(0, main_banner_y), (breaking_w, main_banner_y + breaking_h)],
                    fill=(*self.COLORS["breaking_red"], 250)
                )
                draw.text(
                    (15, main_banner_y + 5),
                    breaking_text,
                    font=breaking_font,
                    fill=self.COLORS["text_white"]
                )
            
            # メインヘッドライン背景（白背景 + 赤枠、幅いっぱい、BREAKING NEWSとくっつける）
            headline_size = int(headline_area_h * 0.55)
            headline_font = self._get_font(headline_size, bold=True)
            headline_text = headline[:25]
            
            # 赤い枠線（上下左右）
            border_width = 4
            
            # 赤い枠線を先に全体に描画
            draw.rectangle(
                [(0, headline_area_y), (width, headline_area_y + headline_area_h)],
                fill=(*self.COLORS["breaking_red"], 255)
            )
            
            # 白い背景（枠線の内側）
            draw.rectangle(
                [(border_width, headline_area_y + border_width), 
                 (width - border_width, headline_area_y + headline_area_h - border_width)],
                fill=(255, 255, 255, 250)
            )
            
            # ヘッドラインテキスト（黒文字、左寄せ、縦中央）
            headline_bbox = draw.textbbox((0, 0), headline_text, font=headline_font)
            headline_text_h = headline_bbox[3] - headline_bbox[1]
            
            headline_x = int(width * 0.025)  # 左寄せ
            headline_y = headline_area_y + (headline_area_h - headline_text_h) // 2  # 縦中央
            draw.text((headline_x, headline_y), headline_text, font=headline_font, fill=(0, 0, 0, 255))
            
            # === 3. サブバナー（サブヘッドライン用） ===
            if sub_headline:
                sub_banner_h = int(height * 0.065)
                sub_banner_y = headline_area_y + headline_area_h
                
                # 少し明るいグレー背景
                draw.rectangle(
                    [(0, sub_banner_y), (width, sub_banner_y + sub_banner_h)],
                    fill=(*self.COLORS["banner_dark"], 230)
                )
                
                # サブヘッドライン
                sub_size = int(sub_banner_h * 0.55)
                sub_font = self._get_font(sub_size)
                draw.text(
                    (headline_x, sub_banner_y + int(sub_banner_h * 0.2)),
                    sub_headline[:40],
                    font=sub_font,
                    fill=self.COLORS["text_light"]
                )
            
            # 合成
            result = Image.alpha_composite(img, overlay)
            
            # 保存
            if output_path is None:
                stem = Path(image_path).stem
                output_path = str(IMAGES_DIR / f"{stem}_news.png")
            
            result.convert("RGB").save(output_path, "PNG", quality=95)
            logger.info(f"TV news overlay added: {output_path}")
            
            return GraphicsResult(success=True, output_path=output_path)
            
        except Exception as e:
            logger.error(f"Failed to add overlay: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return GraphicsResult(success=False, error_message=str(e))

    # 後方互換性のためのエイリアス
    def add_full_news_overlay(self, *args, **kwargs) -> GraphicsResult:
        """add_tv_news_overlay のエイリアス"""
        return self.add_tv_news_overlay(*args, **kwargs)


if __name__ == "__main__":
    compositor = NewsGraphicsCompositor(channel_name="AI NEWS")
    
    test_images = list(IMAGES_DIR.glob("content_planner_test.png"))
    if test_images:
        test_image = str(test_images[0])
        print(f"Testing with: {test_image}")
        
        result = compositor.add_tv_news_overlay(
            test_image,
            headline="トヨタ新型EV発表",
            sub_headline="航続距離700km、テスラに対抗",
            is_breaking=True,
            show_live=True,
        )
        print(f"Result: {result}")
