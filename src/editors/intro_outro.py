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
    channel_name: str = "FJ News 24"
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
        
        if not self.font_large:
            self.font_large = ImageFont.load_default()
            self.font_medium = ImageFont.load_default()
            self.font_small = ImageFont.load_default()
    
    def create_intro_frames(self, output_dir: Path) -> list[str]:
        """イントロのフレームを生成 - 白背景 + 赤丸スムース拡大 + 白文字静止"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        frames = []
        total_frames = int(self.config.intro_duration * self.config.fps)
        
        import math
        
        for i in range(total_frames):
            progress = i / total_frames
            frame_path = output_dir / f"intro_{i:04d}.png"
            
            # 白背景
            img = Image.new('RGB', (self.config.width, self.config.height), '#ffffff')
            draw = ImageDraw.Draw(img)
            
            center_x, center_y = self.config.width // 2, self.config.height // 2
            
            # 赤丸のスムースな拡大（イージング: ease-out）
            # 0→1 に ease-out で拡大
            eased = 1 - (1 - progress) ** 3  # cubic ease-out
            min_radius = 0
            max_radius = 280
            circle_radius = int(min_radius + (max_radius - min_radius) * eased)
            
            if circle_radius > 0:
                draw.ellipse(
                    [center_x - circle_radius, center_y - circle_radius,
                     center_x + circle_radius, center_y + circle_radius],
                    fill=self.config.accent_color
                )
            
            # チャンネル名（白文字、静止、常に表示）
            text = self.config.channel_name
            bbox = draw.textbbox((0, 0), text, font=self.font_large)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = (self.config.width - text_width) // 2
            text_y = center_y - text_height // 2
            
            draw.text((text_x, text_y), text, font=self.font_large, fill='#ffffff')
            
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
            
            # チャンネル名（下部）- 赤文字
            channel_text = self.config.channel_name
            bbox = draw.textbbox((0, 0), channel_text, font=self.font_small)
            ch_width = bbox[2] - bbox[0]
            ch_x = (self.config.width - ch_width) // 2
            ch_y = self.config.height - 200
            
            ch_color = self._blend_color(self.config.accent_color, '#ffffff', alpha)
            draw.text((ch_x, ch_y), channel_text, font=self.font_small, fill=ch_color)
            
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
        channel_name="FJ News 24",
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
