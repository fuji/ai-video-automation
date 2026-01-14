"""動画生成モジュール - KLING AI SDK"""

import os
import time
import asyncio
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import httpx

from ..config import config, VIDEOS_DIR
from ..logger import setup_logger

logger = setup_logger("video_generator")


@dataclass
class VideoResult:
    """動画生成結果"""
    success: bool
    file_path: Optional[str] = None
    video_url: Optional[str] = None
    task_id: Optional[str] = None
    error_message: Optional[str] = None
    generation_time: float = 0.0


class KlingVideoGenerator:
    """KLING AI SDKを使用した動画生成

    参考: https://github.com/yihong0618/klingCreator
    """

    API_BASE = "https://klingai.com/api"

    def __init__(self):
        self.cookie = config.kling.cookie
        self.mode = config.kling.mode  # "std" or "pro"
        self.duration = config.kling.duration
        self.timeout = config.kling.timeout
        self.poll_interval = config.kling.poll_interval

        if not self.cookie:
            logger.warning("KLING_COOKIE not set - video generation will fail")

        self.headers = {
            "Cookie": self.cookie,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        }

        logger.info(f"KlingVideoGenerator initialized (mode={self.mode})")

    def generate(
        self,
        prompt: str,
        output_name: str,
        first_frame: Optional[str] = None,
        end_frame: Optional[str] = None,
        duration: Optional[int] = None,
        retry_count: int = None,
    ) -> VideoResult:
        """動画を生成"""
        start_time = time.time()
        retries = retry_count or config.retry_count
        video_duration = duration or self.duration

        logger.info(f"Generating video: {output_name} ({video_duration}s)")
        logger.debug(f"Prompt: {prompt[:100]}...")

        for attempt in range(retries):
            try:
                # タスク作成
                task_id = self._create_task(
                    prompt=prompt,
                    first_frame=first_frame,
                    end_frame=end_frame,
                    duration=video_duration,
                )

                if not task_id:
                    raise Exception("Failed to create task")

                logger.info(f"Task created: {task_id}")

                # 完了を待機
                video_url = self._wait_for_completion(task_id)

                if video_url:
                    # 動画をダウンロード
                    output_path = VIDEOS_DIR / f"{output_name}.mp4"
                    if self._download_video(video_url, str(output_path)):
                        return VideoResult(
                            success=True,
                            file_path=str(output_path),
                            video_url=video_url,
                            task_id=task_id,
                            generation_time=time.time() - start_time,
                        )

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{retries} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(config.retry_delay)

        return VideoResult(
            success=False,
            error_message="All attempts failed",
            generation_time=time.time() - start_time,
        )

    def _create_task(
        self,
        prompt: str,
        first_frame: Optional[str] = None,
        end_frame: Optional[str] = None,
        duration: int = 5,
    ) -> Optional[str]:
        """KLING APIでタスク作成"""
        try:
            # 画像をBase64エンコード
            first_frame_data = None
            end_frame_data = None

            if first_frame and Path(first_frame).exists():
                first_frame_data = self._encode_image(first_frame)

            if end_frame and Path(end_frame).exists():
                end_frame_data = self._encode_image(end_frame)

            # リクエストペイロード
            payload = {
                "prompt": prompt,
                "mode": self.mode,
                "duration": str(duration),
                "aspect_ratio": config.kling.aspect_ratio,
            }

            if first_frame_data:
                payload["first_frame"] = first_frame_data

            if end_frame_data:
                payload["end_frame"] = end_frame_data

            # API呼び出し
            with httpx.Client(timeout=60) as client:
                response = client.post(
                    f"{self.API_BASE}/task/submit",
                    json=payload,
                    headers=self.headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get("data", {}).get("task_id")
                else:
                    logger.error(f"API error: {response.status_code} - {response.text}")
                    return None

        except Exception as e:
            logger.error(f"Task creation failed: {e}")
            return None

    def _wait_for_completion(self, task_id: str) -> Optional[str]:
        """タスク完了を待機"""
        start_time = time.time()

        while time.time() - start_time < self.timeout:
            try:
                status = self._check_task_status(task_id)

                if status.get("status") == "completed":
                    return status.get("video_url")

                if status.get("status") == "failed":
                    logger.error(f"Task failed: {status.get('error')}")
                    return None

                progress = status.get("progress", 0)
                logger.debug(f"Task {task_id}: {progress}%")

                time.sleep(self.poll_interval)

            except Exception as e:
                logger.warning(f"Status check error: {e}")
                time.sleep(self.poll_interval)

        logger.error(f"Task timeout: {task_id}")
        return None

    def _check_task_status(self, task_id: str) -> dict:
        """タスクステータスを確認"""
        try:
            with httpx.Client(timeout=30) as client:
                response = client.get(
                    f"{self.API_BASE}/task/status/{task_id}",
                    headers=self.headers,
                )

                if response.status_code == 200:
                    return response.json().get("data", {})

        except Exception as e:
            logger.error(f"Status check failed: {e}")

        return {}

    def _download_video(self, url: str, output_path: str) -> bool:
        """動画をダウンロード"""
        try:
            with httpx.Client(timeout=120, follow_redirects=True) as client:
                response = client.get(url)

                if response.status_code == 200:
                    with open(output_path, "wb") as f:
                        f.write(response.content)
                    logger.info(f"Video downloaded: {output_path}")
                    return True

        except Exception as e:
            logger.error(f"Download failed: {e}")

        return False

    def _encode_image(self, image_path: str) -> str:
        """画像をBase64エンコード"""
        import base64

        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")


class VideoGenerator:
    """動画生成の統合インターフェース"""

    def __init__(self, provider: str = "kling"):
        self.provider = provider

        if provider == "kling":
            self._generator = KlingVideoGenerator()
        else:
            raise ValueError(f"Unknown provider: {provider}")

        logger.info(f"VideoGenerator initialized with {provider}")

    def generate(
        self,
        prompt: str,
        output_name: str,
        first_frame: Optional[str] = None,
        end_frame: Optional[str] = None,
        duration: int = 5,
    ) -> VideoResult:
        """動画を生成"""
        return self._generator.generate(
            prompt=prompt,
            output_name=output_name,
            first_frame=first_frame,
            end_frame=end_frame,
            duration=duration,
        )

    def generate_batch(
        self,
        tasks: list[dict],  # [{"prompt": str, "output_name": str, "first_frame": str}, ...]
    ) -> list[VideoResult]:
        """複数動画をバッチ生成"""
        results = []

        for i, task in enumerate(tasks):
            logger.info(f"Batch progress: {i + 1}/{len(tasks)}")
            result = self.generate(**task)
            results.append(result)

            # レート制限対策
            if i < len(tasks) - 1:
                time.sleep(5)

        return results


if __name__ == "__main__":
    # テスト実行
    generator = VideoGenerator()

    result = generator.generate(
        prompt="A cyberpunk city at night with neon lights, cinematic camera movement",
        output_name="test_video",
        duration=5,
    )

    print(f"Result: {result}")
