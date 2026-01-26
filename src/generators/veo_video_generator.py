"""Veo 3.1 動画生成モジュール - 画像から動画を生成"""

import os
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import types

from ..config import config, VIDEOS_DIR
from ..logger import setup_logger

logger = setup_logger("veo_video_generator")


@dataclass
class VeoVideoResult:
    """Veo動画生成結果"""
    success: bool
    output_path: Optional[str] = None
    duration: float = 0.0
    error_message: Optional[str] = None
    generation_time: float = 0.0


class VeoVideoGenerator:
    """Veo 3.1 で画像から超ダイナミックな動画を生成"""

    # カテゴリ別・シーンタイプ別の超ダイナミックなプロンプト
    # 重要: 静止画っぽく見えないように、動きを具体的に指示する
    MOVEMENT_PROMPTS = {
        "政治": {
            "intro": (
                "Cinematic drone shot slowly descending towards Japanese Diet building, "
                "camera continuously moving forward and down, clouds drifting across sky, "
                "trees swaying in gentle wind, flags fluttering on poles, "
                "golden hour light shifting across the building facade, "
                "birds flying across frame, shadow of drone visible moving on ground, "
                "gimbal stabilized smooth motion, real broadcast news footage feel"
            ),
            "detail": (
                "Steadicam shot gliding through government corridor, "
                "camera pushing forward at walking pace, people passing by in both directions, "
                "shadows moving as we pass windows, reflections sliding on polished floor, "
                "dust particles visible in light beams from windows, "
                "focus smoothly shifts from foreground to background, "
                "realistic indoor lighting with subtle flicker"
            ),
            "outro": (
                "Crane shot rising above the Diet building, camera rotating 15 degrees, "
                "city revealing below as we ascend, car lights streaming on roads, "
                "clouds moving overhead in accelerated motion, "
                "building lights turning on as dusk settles, "
                "ambient city sounds implied, gradual zoom out to wide shot"
            ),
        },
        "経済": {
            "intro": (
                "Hyperlapse through Marunouchi financial district, camera moving forward, "
                "pedestrians walking in accelerated motion, traffic flowing continuously, "
                "neon signs flickering and pulsing, rain drops streaking on camera lens, "
                "reflections rippling on wet pavement, steam rising from vents, "
                "streetlights glowing with halos, real urban documentary feel"
            ),
            "detail": (
                "Camera orbiting around trading desk monitors, continuous rotation, "
                "stock numbers scrolling rapidly, green and red prices updating, "
                "reflections on multiple glass screens, keyboard keys clicking implied, "
                "shallow depth with background traders moving, screen glow illuminating faces, "
                "real financial news room atmosphere"
            ),
            "outro": (
                "Aerial view ascending above Tokyo skyline, camera tilting up, "
                "office building lights twinkling like stars, "
                "trains moving along tracks below, helicopter passing in distance, "
                "clouds moving across moon, gradual color shift to night blue"
            ),
        },
        "テクノロジー": {
            "intro": (
                "Camera flying forward through 3D data visualization space, "
                "data streams flowing past camera continuously, nodes connecting with light pulses, "
                "holographic UI panels materializing and dissolving, "
                "particles swirling in helical patterns, circuit patterns pulsing with electricity, "
                "camera weaving between floating data structures, "
                "lens flares from bright nodes, sci-fi movie quality"
            ),
            "detail": (
                "Camera pushing towards holographic display, focus pulling through layers, "
                "digital code waterfalls cascading down, graphs animating with new data, "
                "neural network visualization with firing synapses, "
                "rotating 3D models of technology, ambient particle field drifting, "
                "reflection of display on glass surface, futuristic UI interaction"
            ),
            "outro": (
                "Camera pulling back through infinite digital layers, zooming out continuously, "
                "data networks shrinking to points of light, global connection web visible, "
                "transition from micro to macro scale, stars emerging in background, "
                "final reveal of Earth with data flowing between continents"
            ),
        },
        "国際": {
            "intro": (
                "Earth rotating slowly from orbital view, camera drifting right, "
                "clouds swirling over continents, city lights twinkling on night side, "
                "aurora borealis rippling over poles, sun rising creating lens flare, "
                "satellites visible as moving points of light, "
                "space debris tumbling past, realistic space footage quality"
            ),
            "detail": (
                "Camera flying across 3D world map, moving between continents, "
                "connection lines animating between cities, pulsing nodes indicating activity, "
                "terrain elevation rising as camera passes, ocean waves visible below, "
                "news graphics appearing with country labels, "
                "smooth camera arc over regions of interest"
            ),
            "outro": (
                "Camera zooming out from Earth, moon entering frame, "
                "stars becoming visible in background, satellite passing in foreground, "
                "Earth rotating continuously, space station visible as bright point, "
                "cosmic perspective establishing, gentle fade to starfield"
            ),
        },
        "科学": {
            "intro": (
                "Microscope view diving into cellular world, camera pushing through membrane, "
                "organelles floating and rotating, cilia waving rhythmically, "
                "bioluminescent flashes occurring randomly, DNA strand rotating slowly, "
                "particles drifting in cellular fluid, focus shifting through depth layers, "
                "scientific documentary visual quality"
            ),
            "detail": (
                "Camera moving through molecular landscape, atoms vibrating with energy, "
                "chemical bonds forming with light emissions, electron clouds pulsing, "
                "crystalline structures rotating, liquid nitrogen mist flowing, "
                "laser beams scanning, data readouts updating in overlay, "
                "laboratory atmosphere with equipment humming"
            ),
            "outro": (
                "Scale transition from microscopic to human to cosmic, continuous zoom out, "
                "fractals unfolding and morphing, cells becoming organs becoming bodies, "
                "then rising above Earth into space, galaxies spiraling, "
                "universe expanding perspective, sense of scientific wonder"
            ),
        },
        "スポーツ": {
            "intro": (
                "Stadium pan shot with crowd creating wave motion, camera on crane swinging, "
                "spotlights sweeping across field, confetti falling continuously, "
                "flags waving in stands, players warming up in distance, "
                "breath visible in cool air, real sports broadcast atmosphere"
            ),
            "detail": (
                "Slow motion capture of athletic movement, athlete body in motion, "
                "muscle fibers visible tensing, sweat droplets suspended then falling, "
                "equipment moving through air, fabric rippling with wind resistance, "
                "crowd blurred in background, focus locked on action, "
                "high speed camera feel, dramatic sports photography"
            ),
            "outro": (
                "Victory celebration with fireworks bursting, confetti shower continuous, "
                "camera crane rising above celebrating crowd, "
                "stadium lights pulsing, smoke from pyrotechnics drifting, "
                "tears of joy visible, golden sunset lighting, triumphant moment"
            ),
        },
        "default": {
            "intro": (
                "Smooth tracking shot through abstract environment, camera gliding forward, "
                "volumetric light beams shifting slowly, dust particles floating in air, "
                "atmospheric fog rolling gently, lens flares from light sources, "
                "depth layers moving at different parallax speeds, "
                "cinematic establishing shot, professional documentary quality"
            ),
            "detail": (
                "Camera push with continuous motion, focus pulling through scene layers, "
                "environmental elements swaying naturally with implied wind, "
                "light beams rotating slowly, shadows moving across surfaces, "
                "particles drifting through frame, reflections rippling, "
                "texture details revealed as camera approaches"
            ),
            "outro": (
                "Graceful camera pull-back with continuous motion, elements settling, "
                "wind effect on floating particles, light fading to amber, "
                "gentle camera rotation as we retreat, perspective widening, "
                "ambient atmosphere deepening, professional fade out"
            ),
        },
    }

    # 動的要素のプール（ランダムに追加）
    DYNAMIC_ELEMENTS = [
        "realistic motion blur on moving objects",
        "subtle natural camera shake for authenticity",
        "professional color grading with cinematic LUT",
        "volumetric fog and atmospheric scattering",
        "dynamic lighting that shifts and evolves",
        "parallax depth layers creating 3D effect",
        "realistic physics simulation on particles",
        "cinematic lens effects including anamorphic flares",
        "smooth 60fps fluid motion",
        "ray-traced reflections and shadows",
        "ambient occlusion for depth",
        "film grain for cinematic texture",
    ]

    def __init__(self, model: str = "veo-3.1"):
        """Veo動画生成クライアント初期化

        Args:
            model: 使用するモデル ("veo-3.1" または "veo-3-fast")
        """
        if not config.gemini.api_key:
            raise ValueError("GEMINI_API_KEY is not set")

        self.client = genai.Client(api_key=config.gemini.api_key)
        self.model = model  # Veo 3.1 (Image-to-Video対応)
        self.output_dir = VIDEOS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # レート制限対策
        self.last_request_time = 0
        self.min_request_interval = 60  # 1分間隔（Veo 3.1は課金プランでも制限あり）

        logger.info(f"VeoVideoGenerator initialized with {self.model}")

    def _wait_for_rate_limit(self):
        """レート制限を回避するため待機"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            wait_time = self.min_request_interval - elapsed
            logger.info(f"Rate limit: waiting {wait_time:.1f}s")
            time.sleep(wait_time)
        self.last_request_time = time.time()

    def _enhance_prompt_for_maximum_motion(
        self,
        base_prompt: str,
        motion_strength: float = 0.9,
        guidance_scale: float = 8.0,
    ) -> str:
        """プロンプトを強化して最大限の動きを引き出す

        Veo 3.1は主にプロンプトで動きを制御するため、
        プロンプトを詳細にすることで本物の動画らしさを実現する

        Args:
            base_prompt: 基本プロンプト
            motion_strength: 動きの強さ (0.0-1.0)
            guidance_scale: プロンプトへの忠実度

        Returns:
            強化されたプロンプト
        """
        # 動きの強さに応じた修飾子
        if motion_strength >= 0.8:
            motion_modifiers = [
                "continuous fluid motion throughout",
                "dynamic camera movement",
                "constant subtle motion in all elements",
                "realistic physics-based movement",
                "natural swaying and flowing motion",
                "parallax effect with depth layers moving at different speeds",
            ]
        elif motion_strength >= 0.5:
            motion_modifiers = [
                "smooth gradual motion",
                "gentle camera pan",
                "subtle environmental movement",
                "soft swaying elements",
            ]
        else:
            motion_modifiers = [
                "minimal subtle motion",
                "slow gentle movement",
            ]

        # カメラワークの指示（重要: Veoが静止画っぽくならないようにする）
        camera_instructions = [
            "camera slowly pushes forward creating depth",
            "slight camera drift to the right",
            "gentle zoom progression",
            "handheld camera feel with subtle shake",
            "cinematic dolly movement",
        ]

        # 環境の動きの指示
        environment_motion = [
            "wind gently moving particles and elements",
            "light rays shifting slowly",
            "atmospheric haze drifting",
            "reflections rippling subtly",
            "shadows slowly shifting with light source",
            "floating dust particles catching light",
        ]

        # 動きの強さに応じて要素を選択
        import random
        num_motion = min(3, int(motion_strength * 4))
        num_camera = min(2, int(motion_strength * 3))
        num_env = min(2, int(motion_strength * 3))

        selected_motion = random.sample(motion_modifiers, min(num_motion, len(motion_modifiers)))
        selected_camera = random.sample(camera_instructions, min(num_camera, len(camera_instructions)))
        selected_env = random.sample(environment_motion, min(num_env, len(environment_motion)))

        # 品質とリアリズムの指示
        quality_suffix = (
            "photorealistic rendering, natural motion blur on moving elements, "
            "broadcast quality cinematography, film-like color grading, "
            "seamless 30fps fluid motion, professional videography"
        )

        # 絶対に避けるべきことの明示（ネガティブプロンプト的に使う）
        # Note: これは実際のネガティブプロンプトではなく、指示として含める
        anti_static_instruction = (
            "NOT a static image, NOT a slideshow, this is a REAL moving video, "
            "everything should have natural motion"
        )

        # 最終プロンプト構築
        enhanced_parts = [
            base_prompt,
            "IMPORTANT: " + anti_static_instruction,
            "Motion: " + ", ".join(selected_motion),
            "Camera: " + ", ".join(selected_camera),
            "Environment: " + ", ".join(selected_env),
            quality_suffix,
        ]

        enhanced_prompt = ". ".join(enhanced_parts)

        return enhanced_prompt

    def generate_from_image(
        self,
        image_path: str,
        output_path: str = None,
        prompt: str = "",
        duration: int = 8,
        aspect_ratio: str = "16:9",
        resolution: str = "1080p",
        include_audio: bool = True,
        motion_strength: float = 0.9,
        guidance_scale: float = 8.0,
    ) -> VeoVideoResult:
        """画像から超ダイナミックな動画を生成（Veo 3.1 Image-to-Video API）

        Args:
            image_path: 入力画像のパス
            output_path: 出力動画のパス
            prompt: 動画生成のプロンプト（カメラワークなど）
            duration: 動画の長さ（秒）5-8秒推奨
            aspect_ratio: アスペクト比 ("16:9", "9:16", "1:1")
            resolution: 解像度 ("720p", "1080p")
            include_audio: 音響効果を自動追加するか
            motion_strength: 動きの強さ (0.0-1.0) 高いほど大きく動く
            guidance_scale: プロンプトへの忠実度 (1.0-20.0) 高いほどプロンプト通り

        Returns:
            VeoVideoResult
        """
        start_time = time.time()

        if not Path(image_path).exists():
            return VeoVideoResult(
                success=False,
                error_message=f"Image not found: {image_path}",
            )

        if output_path is None:
            stem = Path(image_path).stem
            output_path = str(self.output_dir / f"{stem}_veo.mp4")

        self._wait_for_rate_limit()

        try:
            # 詳細なデバッグログ
            logger.info("=" * 60)
            logger.info("🎬 VEO 3.1 DYNAMIC VIDEO GENERATION")
            logger.info("=" * 60)
            logger.info(f"Model: {self.model}")
            logger.info(f"Image: {Path(image_path).name}")
            logger.info(f"Duration: {duration}s | Resolution: {resolution}")
            logger.info(f"Aspect Ratio: {aspect_ratio} | Audio: {include_audio}")
            logger.info(f"Motion Strength: {motion_strength} | Guidance: {guidance_scale}")
            logger.info("-" * 60)
            logger.info(f"PROMPT:\n{prompt}")
            logger.info("=" * 60)

            # 画像ファイルを読み込み
            with open(image_path, "rb") as f:
                image_data = f.read()

            image_size_kb = len(image_data) / 1024
            logger.info(f"Image size: {image_size_kb:.1f} KB")

            # MIMEタイプを判定
            image_suffix = Path(image_path).suffix.lower()
            mime_type = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }.get(image_suffix, "image/png")

            # プロンプトをさらに強化（動きを最大限に引き出す）
            enhanced_prompt = self._enhance_prompt_for_maximum_motion(
                prompt, motion_strength, guidance_scale
            )
            logger.info(f"Enhanced prompt length: {len(enhanced_prompt)} chars")

            # Veo 3.1 Image-to-Video API（非同期操作）
            logger.info("Calling Veo 3.1 API...")
            operation = self.client.models.generate_video(
                model=self.model,
                prompt=enhanced_prompt,
                config=types.GenerateVideoConfig(
                    image=types.Image(
                        image_bytes=image_data,
                        mime_type=mime_type,
                    ),
                    aspect_ratio=aspect_ratio,
                    # Note: Veo API の利用可能なパラメータは限定的
                    # プロンプトで動きを制御することが主な手法
                ),
            )

            logger.info("⏳ Waiting for Veo 3.1 video generation to complete...")
            logger.info("   (This typically takes 2-5 minutes for high-quality video)")

            # 操作の完了を待機（ポーリング）
            poll_count = 0
            poll_start = time.time()
            while not operation.done:
                poll_count += 1
                elapsed_mins = (time.time() - poll_start) / 60
                logger.info(f"   Processing... (poll #{poll_count}, {elapsed_mins:.1f} min elapsed)")
                time.sleep(10)
                operation = self.client.operations.get(operation)

            total_wait = time.time() - poll_start
            logger.info(f"✅ Veo API responded after {total_wait:.1f}s ({poll_count} polls)")

            # 結果を取得
            if operation.error:
                logger.error(f"❌ Veo API returned error: {operation.error}")
                raise ValueError(f"Generation failed: {operation.error}")

            response = operation.response

            # レスポンス構造をデバッグ出力
            logger.debug(f"Response type: {type(response)}")
            logger.debug(f"Response attributes: {dir(response)}")

            # 動画データを取得
            video_data = None
            video_source = "unknown"

            if hasattr(response, 'generated_videos') and response.generated_videos:
                logger.info(f"📹 Found {len(response.generated_videos)} generated video(s)")
                video = response.generated_videos[0]
                logger.debug(f"Video object attributes: {dir(video)}")

                if hasattr(video, 'video'):
                    video_data = video.video
                    video_source = "generated_videos[0].video"
                elif hasattr(video, 'video_bytes'):
                    video_data = video.video_bytes
                    video_source = "generated_videos[0].video_bytes"

            if not video_data:
                logger.warning("⚠️ No video in primary response format, checking alternatives...")
                # 代替フォーマットを確認
                if hasattr(response, 'video'):
                    video_data = response.video
                    video_source = "response.video"
                    logger.info("Found video in response.video")
                elif hasattr(response, 'candidates') and response.candidates:
                    logger.info(f"Checking {len(response.candidates)} candidates...")
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'inline_data') and part.inline_data:
                            mime = getattr(part.inline_data, 'mime_type', '')
                            logger.debug(f"Part mime_type: {mime}")
                            if 'video' in mime:
                                video_data = part.inline_data.data
                                video_source = f"candidates[0].content.parts (mime: {mime})"
                                break

            if not video_data:
                logger.error("❌ No video data in any response format")
                logger.error("   Response structure inspection:")
                logger.error(f"   - has generated_videos: {hasattr(response, 'generated_videos')}")
                logger.error(f"   - has video: {hasattr(response, 'video')}")
                logger.error(f"   - has candidates: {hasattr(response, 'candidates')}")
                return VeoVideoResult(
                    success=False,
                    error_message="No video generated - Veo API returned empty response",
                    generation_time=time.time() - start_time,
                )

            logger.info(f"✅ Video data extracted from: {video_source}")

            # 動画を保存
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            if isinstance(video_data, bytes):
                video_size_mb = len(video_data) / (1024 * 1024)
                logger.info(f"💾 Saving video ({video_size_mb:.2f} MB) as bytes...")
                with open(output_path, "wb") as f:
                    f.write(video_data)
            else:
                # base64の場合
                import base64
                logger.info("💾 Saving video (base64 encoded)...")
                decoded_data = base64.b64decode(video_data)
                video_size_mb = len(decoded_data) / (1024 * 1024)
                logger.info(f"   Decoded size: {video_size_mb:.2f} MB")
                with open(output_path, "wb") as f:
                    f.write(decoded_data)

            generation_time = time.time() - start_time

            # 最終確認
            if Path(output_path).exists():
                final_size = Path(output_path).stat().st_size / (1024 * 1024)
                logger.info("=" * 60)
                logger.info("🎉 VEO 3.1 VIDEO GENERATION SUCCESS")
                logger.info("=" * 60)
                logger.info(f"   Output: {output_path}")
                logger.info(f"   Size: {final_size:.2f} MB")
                logger.info(f"   Generation time: {generation_time:.1f}s")
                logger.info("=" * 60)
            else:
                logger.error(f"❌ File not created: {output_path}")

            return VeoVideoResult(
                success=True,
                output_path=output_path,
                duration=duration,
                generation_time=generation_time,
            )

        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())

            return VeoVideoResult(
                success=False,
                error_message=str(e),
                generation_time=time.time() - start_time,
            )

    def generate_from_prompt(
        self,
        prompt: str,
        output_path: str = None,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        resolution: str = "1080p",
    ) -> VeoVideoResult:
        """プロンプトのみから動画を生成（Text-to-Video）

        Args:
            prompt: 動画生成のプロンプト
            output_path: 出力動画のパス
            duration: 動画の長さ（秒）
            aspect_ratio: アスペクト比
            resolution: 解像度

        Returns:
            VeoVideoResult
        """
        start_time = time.time()

        if output_path is None:
            timestamp = int(time.time())
            output_path = str(self.output_dir / f"veo_{timestamp}.mp4")

        self._wait_for_rate_limit()

        try:
            logger.info(f"Generating video from prompt: {prompt[:100]}...")

            # Veo 3.1 Text-to-Video API（非同期操作）
            operation = self.client.models.generate_video(
                model=self.model,
                prompt=prompt,
                config=types.GenerateVideoConfig(
                    aspect_ratio=aspect_ratio,
                ),
            )

            logger.info("Waiting for video generation to complete...")

            # 操作の完了を待機
            while not operation.done:
                logger.debug("Still processing...")
                time.sleep(10)
                operation = self.client.operations.get(operation)

            if operation.error:
                raise ValueError(f"Generation failed: {operation.error}")

            response = operation.response

            # 動画データを取得
            video_data = None
            if hasattr(response, 'generated_videos') and response.generated_videos:
                video = response.generated_videos[0]
                if hasattr(video, 'video'):
                    video_data = video.video
                elif hasattr(video, 'video_bytes'):
                    video_data = video.video_bytes

            if not video_data:
                if hasattr(response, 'video'):
                    video_data = response.video

            if not video_data:
                return VeoVideoResult(
                    success=False,
                    error_message="No video generated",
                    generation_time=time.time() - start_time,
                )

            # 動画を保存
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            if isinstance(video_data, bytes):
                with open(output_path, "wb") as f:
                    f.write(video_data)
            else:
                import base64
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(video_data))

            generation_time = time.time() - start_time
            logger.info(f"Video saved: {output_path} ({generation_time:.1f}s)")

            return VeoVideoResult(
                success=True,
                output_path=output_path,
                duration=duration,
                generation_time=generation_time,
            )

        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            return VeoVideoResult(
                success=False,
                error_message=str(e),
                generation_time=time.time() - start_time,
            )

    def create_dynamic_prompt(
        self,
        news_category: str,
        scene_type: str = "intro",
        news_title: str = "",
        additional_context: str = "",
    ) -> str:
        """ニュースカテゴリに応じた超ダイナミックなプロンプトを生成

        Args:
            news_category: ニュースカテゴリ
            scene_type: シーンタイプ（intro, detail, outro）
            news_title: ニュースタイトル（追加コンテキスト用）
            additional_context: その他の追加コンテキスト

        Returns:
            動画生成用の超ダイナミックなプロンプト
        """
        import random

        # カテゴリのプロンプトを取得
        category_prompts = self.MOVEMENT_PROMPTS.get(
            news_category, self.MOVEMENT_PROMPTS["default"]
        )

        # シーンタイプのプロンプトを取得
        base_prompt = category_prompts.get(scene_type, category_prompts["intro"])

        # ランダムな動的要素を3-4個選択
        num_elements = random.randint(3, 4)
        selected_elements = random.sample(self.DYNAMIC_ELEMENTS, num_elements)
        dynamic_suffix = ", ".join(selected_elements)

        # 品質タグ
        quality_tags = (
            "high production value, broadcast quality, photorealistic rendering, "
            "8K cinematic quality, professional videography, seamless motion"
        )

        # 最終プロンプト構築
        final_prompt = f"{base_prompt}. {dynamic_suffix}. {quality_tags}"

        # 追加コンテキストがあれば追加
        if additional_context:
            final_prompt = f"{final_prompt}. {additional_context}"

        logger.info(f"Generated dynamic prompt for [{news_category}/{scene_type}]")
        logger.debug(f"Full prompt: {final_prompt}")

        return final_prompt

    def detect_category(self, title: str) -> str:
        """ニュースタイトルからカテゴリを判定

        Args:
            title: ニュースタイトル

        Returns:
            カテゴリ名
        """
        category_keywords = {
            "政治": ["政治", "選挙", "国会", "首相", "政府", "法案", "与党", "野党"],
            "経済": ["経済", "株", "円", "企業", "市場", "金融", "投資", "景気"],
            "テクノロジー": ["AI", "テクノロジー", "IT", "デジタル", "ロボット", "技術", "開発"],
            "国際": ["国際", "世界", "海外", "外交", "米国", "中国", "EU"],
            "科学": ["科学", "研究", "発見", "宇宙", "医療", "実験"],
            "スポーツ": ["スポーツ", "五輪", "サッカー", "野球", "優勝", "試合"],
        }

        for category, keywords in category_keywords.items():
            if any(kw in title for kw in keywords):
                return category

        return "default"


if __name__ == "__main__":
    # テスト実行
    try:
        generator = VeoVideoGenerator()
        print("VeoVideoGenerator initialized successfully")

        # プロンプトテスト
        test_title = "AI技術が変える未来の働き方"
        category = generator.detect_category(test_title)
        print(f"Category: {category}")

        prompt = generator.create_dynamic_prompt(category, "intro")
        print(f"Prompt: {prompt}")

    except Exception as e:
        print(f"Error: {e}")
