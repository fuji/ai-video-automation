"""YouTube投稿モジュール - YouTube Data API v3"""

import os
import pickle
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from ..config import config, BASE_DIR
from ..logger import setup_logger

logger = setup_logger("youtube_uploader")


@dataclass
class UploadResult:
    """アップロード結果"""
    success: bool
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    error_message: Optional[str] = None


class YouTubeUploader:
    """YouTube Data API v3を使用した動画投稿"""

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    def __init__(self):
        self.client_secrets_file = config.youtube.client_secrets_file
        self.credentials_file = Path(BASE_DIR) / config.youtube.credentials_file
        self.youtube = None

        logger.info("YouTubeUploader initialized")

    def authenticate(self) -> bool:
        """OAuth認証を実行"""
        credentials = None

        # 保存された認証情報を読み込み
        if self.credentials_file.exists():
            with open(self.credentials_file, "rb") as f:
                credentials = pickle.load(f)

        # 認証情報の更新または新規取得
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                except Exception as e:
                    logger.warning(f"Token refresh failed: {e}")
                    credentials = None

            if not credentials:
                if not Path(self.client_secrets_file).exists():
                    logger.error(f"Client secrets file not found: {self.client_secrets_file}")
                    return False

                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secrets_file,
                    self.SCOPES,
                )
                credentials = flow.run_local_server(port=0)

            # 認証情報を保存
            with open(self.credentials_file, "wb") as f:
                pickle.dump(credentials, f)

        # YouTube APIクライアントを作成
        self.youtube = build("youtube", "v3", credentials=credentials)
        logger.info("YouTube API authenticated")
        return True

    def upload(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str] = None,
        category_id: str = "22",  # People & Blogs
        privacy_status: str = "private",
    ) -> UploadResult:
        """動画をアップロード"""
        if not Path(video_path).exists():
            return UploadResult(
                success=False,
                error_message=f"Video not found: {video_path}",
            )

        if not self.youtube:
            if not self.authenticate():
                return UploadResult(
                    success=False,
                    error_message="Authentication failed",
                )

        logger.info(f"Uploading video: {title}")

        try:
            # メタデータ
            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags or [],
                    "categoryId": category_id,
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": False,
                },
            }

            # メディアファイル
            media = MediaFileUpload(
                video_path,
                mimetype="video/mp4",
                resumable=True,
            )

            # アップロードリクエスト
            request = self.youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            # 実行
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.debug(f"Upload progress: {int(status.progress() * 100)}%")

            video_id = response["id"]
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            logger.info(f"Upload complete: {video_url}")

            return UploadResult(
                success=True,
                video_id=video_id,
                video_url=video_url,
            )

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return UploadResult(
                success=False,
                error_message=str(e),
            )

    def update_metadata(
        self,
        video_id: str,
        title: str = None,
        description: str = None,
        tags: list[str] = None,
    ) -> bool:
        """動画のメタデータを更新"""
        if not self.youtube:
            if not self.authenticate():
                return False

        try:
            # 現在のメタデータを取得
            response = self.youtube.videos().list(
                part="snippet",
                id=video_id,
            ).execute()

            if not response.get("items"):
                logger.error(f"Video not found: {video_id}")
                return False

            snippet = response["items"][0]["snippet"]

            # 更新
            if title:
                snippet["title"] = title
            if description:
                snippet["description"] = description
            if tags:
                snippet["tags"] = tags

            self.youtube.videos().update(
                part="snippet",
                body={
                    "id": video_id,
                    "snippet": snippet,
                },
            ).execute()

            logger.info(f"Metadata updated: {video_id}")
            return True

        except Exception as e:
            logger.error(f"Metadata update failed: {e}")
            return False

    def set_thumbnail(self, video_id: str, thumbnail_path: str) -> bool:
        """サムネイルを設定"""
        if not Path(thumbnail_path).exists():
            logger.error(f"Thumbnail not found: {thumbnail_path}")
            return False

        if not self.youtube:
            if not self.authenticate():
                return False

        try:
            media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")

            self.youtube.thumbnails().set(
                videoId=video_id,
                media_body=media,
            ).execute()

            logger.info(f"Thumbnail set for: {video_id}")
            return True

        except Exception as e:
            logger.error(f"Thumbnail set failed: {e}")
            return False

    def get_upload_status(self, video_id: str) -> dict:
        """アップロード状態を取得"""
        if not self.youtube:
            if not self.authenticate():
                return {}

        try:
            response = self.youtube.videos().list(
                part="status,processingDetails",
                id=video_id,
            ).execute()

            if response.get("items"):
                item = response["items"][0]
                return {
                    "privacy_status": item["status"]["privacyStatus"],
                    "upload_status": item["status"]["uploadStatus"],
                    "processing_status": item.get("processingDetails", {}).get("processingStatus"),
                }

        except Exception as e:
            logger.error(f"Failed to get status: {e}")

        return {}


if __name__ == "__main__":
    uploader = YouTubeUploader()

    if uploader.authenticate():
        print("YouTube API authentication successful")
    else:
        print("Authentication failed - check client_secrets.json")
