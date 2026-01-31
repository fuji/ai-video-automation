"""イントロ/アウトロ生成モジュール"""

import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from dataclasses import dataclass

from ..logger import setup_logger

logger = setup_logger("intro_outro")

# アセットディレクトリ
ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
FONTS_DIR = Path(__file__).parent.parent.parent / "fonts"


@dataclass
class IntroOutroConfig:
    """イントロ/アウトロ設定"""
    width: int = 1080
    height: int = 1920
    fps: int = 30
    intro_duration: float = 2.0  # 短めに
    outro_duration: float = 3.0  # 短めに
    
    # カラー
    bg_color: str = "#1a1a2e"  # ダークブルー
    accent_color: str = "#e94560"  # レッド
    text_color: str = "#ffffff"
    
    # チャンネル情報
    channel_name: str = "N1"
    channel_tagline: str = "世界のおもしろニュース"


class IntroOutroGenerator:
    """イントロ/アウトロ動画生成"""
    
    def __init__(self, config: IntroOutroConfig = None):
        self.config = config or IntroOutroConfig()
        self._load_fonts()
    
    def _load_fonts(self):
        """フォントをロード"""
        font_paths = [
            FONTS_DIR / "NotoSansJP-Bold.ttf",
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/Fonts/Hiragino Sans GB W6.otf",
        ]
        
        self.font_large = None
        self.font_medium = None
        self.font_small = None
        self.font_logo = None  # ロゴ用Futura Bold
        
        for font_path in font_paths:
            if Path(font_path).exists():
                try:
                    self.font_large = ImageFont.truetype(str(font_path), 80)
                    self.font_medium = ImageFont.truetype(str(font_path), 48)
                    self.font_small = ImageFont.truetype(str(font_path), 36)
                    logger.info(f"Font loaded: {font_path}")
                    break
                except Exception as e:
                    logger.warning(f"Font load failed: {font_path} - {e}")
        
        # ロゴ用Futura Bold
        futura_path = "/System/Library/Fonts/Supplemental/Futura.ttc"
        if Path(futura_path).exists():
            try:
                self.font_logo = ImageFont.truetype(futura_path, 85, index=2)  # Futura Bold
                logger.info("Futura Bold loaded for logo")
            except Exception as e:
                logger.warning(f"Futura load failed: {e}")
                self.font_logo = self.font_large
        else:
            self.font_logo = self.font_large
        
        if not self.font_large:
            self.font_large = ImageFont.load_default()
            self.font_medium = ImageFont.load_default()
            self.font_small = ImageFont.load_default()
            self.font_logo = ImageFont.load_default()
    
    def _draw_logo_with_tight_spacing(self, draw, text, font, cx, cy, fill, spacing=-8):
        """レタースペーシングを詰めてロゴを描画"""
        # 各文字の幅を取得してトータル幅計算
        total_width = 0
        char_data = []
        for char in text:
            bbox = draw.textbbox((0, 0), char, font=font)
            w = bbox[2] - bbox[0]
            char_data.append((char, w, bbox))
            total_width += w
        total_width += spacing * (len(text) - 1)
        
        # 中央から描画開始
        start_x = cx - total_width // 2
        current_x = start_x
        
        for char, w, bbox in char_data:
            char_y = cy - (bbox[3] - bbox[1]) // 2 - bbox[1]
            draw.text((current_x, char_y), char, font=font, fill=fill)
            current_x += w + spacing
    
    def create_intro_frames(self, output_dir: Path) -> list[str]:
        """イントロのフレームを生成 - 白背景 + ロゴ画像フェードイン（イーズイン）"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        frames = []
        total_frames = int(self.config.intro_duration * self.config.fps)
        hold_time = 0.5  # 最後の停止時間
        anim_duration = self.config.intro_duration - hold_time  # アニメーション時間
        
        # ロゴ画像を読み込み
        logo_path = ASSETS_DIR / "logo-n1.png"
        logo_img = None
        if logo_path.exists():
            logo_img = Image.open(logo_path).convert('RGBA')
            # ロゴのサイズを調整（幅600px程度に）
            logo_width = 600
            ratio = logo_width / logo_img.width
            logo_height = int(logo_img.height * ratio)
            logo_img = logo_img.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
            logger.info(f"Logo loaded: {logo_path} ({logo_width}x{logo_height})")
        
        for i in range(total_frames):
            time = i / self.config.fps
            frame_path = output_dir / f"intro_{i:04d}.png"
            
            # 白背景
            img = Image.new('RGBA', (self.config.width, self.config.height), (255, 255, 255, 255))
            
            center_x, center_y = self.config.width // 2, self.config.height // 2
            
            # アニメーション進捗（anim_duration秒でアニメ完了、その後停止）
            if time < anim_duration:
                progress = time / anim_duration
                eased = progress ** 3  # ease-in（ゆっくり→加速）
                alpha = eased
            else:
                alpha = 1.0  # 停止
            
            # ロゴ画像を中央に配置（フェードイン）
            if logo_img and alpha > 0:
                # アルファ値を適用したロゴを作成
                logo_with_alpha = logo_img.copy()
                # 各ピクセルのアルファを調整
                r, g, b, a = logo_with_alpha.split()
                a = a.point(lambda x: int(x * alpha))
                logo_with_alpha = Image.merge('RGBA', (r, g, b, a))
                
                # 中央に配置
                x = center_x - logo_with_alpha.width // 2
                y = center_y - logo_with_alpha.height // 2
                img.paste(logo_with_alpha, (x, y), logo_with_alpha)
            
            # RGBに変換して保存
            img_rgb = Image.new('RGB', img.size, (255, 255, 255))
            img_rgb.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
            img_rgb.save(frame_path)
            frames.append(str(frame_path))
        
        return frames
    
    def create_outro_frames(self, output_dir: Path) -> list[str]:
        """アウトロのフレームを生成 - ロゴ小 + 質問形CTA"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        frames = []
        total_frames = int(self.config.outro_duration * self.config.fps)
        
        # ロゴ画像を事前に読み込み
        logo_path = ASSETS_DIR / "logo-n1.png"
        logo_img_base = None
        logo_width, logo_height = 250, 0
        if logo_path.exists():
            logo_img_base = Image.open(logo_path).convert('RGBA')
            ratio = logo_width / logo_img_base.width
            logo_height = int(logo_img_base.height * ratio)
            logo_img_base = logo_img_base.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
        
        for i in range(total_frames):
            time = i / self.config.fps
            frame_path = output_dir / f"outro_{i:04d}.png"
            
            # 白背景（RGBA）
            img = Image.new('RGBA', (self.config.width, self.config.height), (255, 255, 255, 255))
            
            center_x, center_y = self.config.width // 2, self.config.height // 2
            
            # ロゴ画像（小さく表示、0.3s〜フェードイン）
            if logo_img_base and time >= 0.3:
                logo_alpha = min(1.0, (time - 0.3) / 0.3)
                logo_img = logo_img_base.copy()
                r, g, b, a = logo_img.split()
                a = a.point(lambda x: int(x * logo_alpha))
                logo_img = Image.merge('RGBA', (r, g, b, a))
                x = center_x - logo_width // 2
                y = center_y - 280
                img.paste(logo_img, (x, y), logo_img)
            
            # RGB変換してテキスト描画
            img_rgb = img.convert('RGB')
            draw = ImageDraw.Draw(img_rgb)
            
            # 「面白かった？」(0.5s〜)
            if time >= 0.5:
                text_alpha = min(1.0, (time - 0.5) / 0.3)
                gray = int(51 + (255 - 51) * (1 - text_alpha))
                text = "面白かった？"
                bbox = draw.textbbox((0, 0), text, font=self.font_large)
                text_x = (self.config.width - (bbox[2] - bbox[0])) // 2
                draw.text((text_x, center_y + 20), text, font=self.font_large, fill=f'#{gray:02x}{gray:02x}{gray:02x}')
            
            # 「いいねで教えてね！」(0.8s〜) - 赤色
            if time >= 0.8:
                text_alpha = min(1.0, (time - 0.8) / 0.3)
                r = int(233 * text_alpha + 255 * (1 - text_alpha))
                g = int(69 * text_alpha + 255 * (1 - text_alpha))
                b = int(96 * text_alpha + 255 * (1 - text_alpha))
                text = "いいねで教えてね！"
                bbox = draw.textbbox((0, 0), text, font=self.font_medium)
                text_x = (self.config.width - (bbox[2] - bbox[0])) // 2
                draw.text((text_x, center_y + 130), text, font=self.font_medium, fill=f'#{r:02x}{g:02x}{b:02x}')
            
            # サブテキスト (1.2s〜)
            if time >= 1.2:
                text_alpha = min(1.0, (time - 1.2) / 0.3)
                gray = int(136 + (255 - 136) * (1 - text_alpha))
                text = "チャンネル登録もよろしく！"
                bbox = draw.textbbox((0, 0), text, font=self.font_small)
                text_x = (self.config.width - (bbox[2] - bbox[0])) // 2
                draw.text((text_x, center_y + 210), text, font=self.font_small, fill=f'#{gray:02x}{gray:02x}{gray:02x}')
            
            img_rgb.save(frame_path)
            frames.append(str(frame_path))
        
        return frames
    
    def _blend_color(self, color1: str, color2: str, alpha: float) -> str:
        """2色をアルファブレンド"""
        def hex_to_rgb(hex_color):
            hex_color = hex_color.lstrip('#')
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        
        def rgb_to_hex(rgb):
            return '#{:02x}{:02x}{:02x}'.format(*rgb)
        
        rgb1 = hex_to_rgb(color1)
        rgb2 = hex_to_rgb(color2)
        
        blended = tuple(int(c1 * alpha + c2 * (1 - alpha)) for c1, c2 in zip(rgb1, rgb2))
        return rgb_to_hex(blended)
    
    def generate_intro_video(self, output_path: str, temp_dir: Path) -> bool:
        """イントロ動画を生成"""
        logger.info("Generating intro video...")
        
        frames_dir = temp_dir / "intro_frames"
        frames = self.create_intro_frames(frames_dir)
        
        if not frames:
            return False
        
        # ffmpegで動画化
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(self.config.fps),
            "-i", str(frames_dir / "intro_%04d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-t", str(self.config.intro_duration),
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True)
        
        if result.returncode == 0:
            logger.info(f"Intro video created: {output_path}")
            return True
        else:
            logger.error(f"Intro generation failed: {result.stderr.decode()}")
            return False
    
    def generate_outro_video(self, output_path: str, temp_dir: Path) -> bool:
        """アウトロ動画を生成"""
        logger.info("Generating outro video...")
        
        frames_dir = temp_dir / "outro_frames"
        frames = self.create_outro_frames(frames_dir)
        
        if not frames:
            return False
        
        # ffmpegで動画化
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(self.config.fps),
            "-i", str(frames_dir / "outro_%04d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-t", str(self.config.outro_duration),
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True)
        
        if result.returncode == 0:
            logger.info(f"Outro video created: {output_path}")
            return True
        else:
            logger.error(f"Outro generation failed: {result.stderr.decode()}")
            return False


def add_fade_transition(input_path: str, output_path: str, fade_in: float = 0.5, fade_out: float = 0.5) -> bool:
    """動画にフェードイン/アウトを追加"""
    
    # 動画の長さを取得
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", input_path],
        capture_output=True, text=True
    )
    duration = float(probe.stdout.strip())
    
    fade_out_start = duration - fade_out
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", f"fade=t=in:st=0:d={fade_in},fade=t=out:st={fade_out_start}:d={fade_out}",
        "-c:v", "libx264",
        "-c:a", "copy",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


if __name__ == "__main__":
    from pathlib import Path
    import tempfile
    
    config = IntroOutroConfig(
        channel_name="N1",
        channel_tagline="世界のおもしろニュース"
    )
    
    generator = IntroOutroGenerator(config)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # イントロ生成
        intro_path = str(temp_path / "intro.mp4")
        if generator.generate_intro_video(intro_path, temp_path):
            print(f"✅ Intro: {intro_path}")
        
        # アウトロ生成
        outro_path = str(temp_path / "outro.mp4")
        if generator.generate_outro_video(outro_path, temp_path):
            print(f"✅ Outro: {outro_path}")
