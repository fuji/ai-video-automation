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
        """イントロのフレームを生成 - 白背景 + 赤角丸四角形拡大 + 白N1固定（Futura Bold）"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        frames = []
        total_frames = int(self.config.intro_duration * self.config.fps)
        hold_time = 0.5  # 最後の停止時間
        anim_duration = self.config.intro_duration - hold_time  # アニメーション時間
        
        for i in range(total_frames):
            time = i / self.config.fps
            frame_path = output_dir / f"intro_{i:04d}.png"
            
            # 白背景
            img = Image.new('RGB', (self.config.width, self.config.height), '#ffffff')
            draw = ImageDraw.Draw(img)
            
            center_x, center_y = self.config.width // 2, self.config.height // 2
            
            # アニメーション進捗（anim_duration秒でアニメ完了、その後停止）
            if time < anim_duration:
                progress = time / anim_duration
                eased = progress ** 3  # ease-in（ゆっくり→加速）
                scale = eased
            else:
                scale = 1.0  # 停止
            
            # 赤の角丸四角形（塗りつぶし）- 0から拡大
            if scale > 0.01:
                rect_width = int(280 * scale)
                rect_height = int(110 * scale)
                radius = int(15 * scale)
                draw.rounded_rectangle(
                    [center_x - rect_width // 2, center_y - rect_height // 2,
                     center_x + rect_width // 2, center_y + rect_height // 2],
                    radius=max(1, radius),
                    fill=self.config.accent_color
                )
            
            # チャンネル名（白、Futura Bold、レタースペーシング詰め）- 最初から表示
            self._draw_logo_with_tight_spacing(
                draw, 
                self.config.channel_name, 
                self.font_logo, 
                center_x, 
                center_y, 
                '#ffffff',
                spacing=-8
            )
            
            img.save(frame_path)
            frames.append(str(frame_path))
        
        return frames
    
    def create_outro_frames(self, output_dir: Path) -> list[str]:
        """アウトロのフレームを生成 - シンプル白背景"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        frames = []
        total_frames = int(self.config.outro_duration * self.config.fps)
        
        for i in range(total_frames):
            progress = i / total_frames
            frame_path = output_dir / f"outro_{i:04d}.png"
            
            # 白背景
            img = Image.new('RGB', (self.config.width, self.config.height), '#ffffff')
            draw = ImageDraw.Draw(img)
            
            center_x, center_y = self.config.width // 2, self.config.height // 2
            
            # フェードイン (0-0.2)
            if progress < 0.2:
                alpha = progress / 0.2
            else:
                alpha = 1.0
            
            # メインテキスト
            main_text = "ご視聴ありがとう！"
            bbox = draw.textbbox((0, 0), main_text, font=self.font_large)
            text_width = bbox[2] - bbox[0]
            text_x = (self.config.width - text_width) // 2
            text_y = center_y - 100
            
            text_color = self._blend_color('#333333', '#ffffff', alpha)
            draw.text((text_x, text_y), main_text, font=self.font_large, fill=text_color)
            
            # サブテキスト
            sub_texts = [
                "いいね & チャンネル登録",
                "よろしくお願いします！"
            ]
            
            for j, sub_text in enumerate(sub_texts):
                bbox = draw.textbbox((0, 0), sub_text, font=self.font_medium)
                sub_width = bbox[2] - bbox[0]
                sub_x = (self.config.width - sub_width) // 2
                sub_y = text_y + 120 + j * 70
                
                sub_color = self._blend_color('#666666', '#ffffff', alpha * 0.9)
                draw.text((sub_x, sub_y), sub_text, font=self.font_medium, fill=sub_color)
            
            # チャンネル名（下部）- 削除済み
            
            img.save(frame_path)
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
