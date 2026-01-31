"""YouTube Shorts Uploader using YouTube Data API v3."""
import os
import json
import pickle
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from rich.console import Console

console = Console()

# OAuth scopes for YouTube upload
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly',
]

# Token storage path
TOKEN_PATH = Path(__file__).parent.parent.parent / "youtube_token.pickle"
CLIENT_SECRETS_PATH = Path(__file__).parent.parent.parent / "youtube_client_secrets.json"


@dataclass
class UploadResult:
    success: bool
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    error_message: Optional[str] = None


class YouTubeUploader:
    """YouTube Shorts アップローダー"""
    
    def __init__(self):
        self.client_id = os.environ.get("YOUTUBE_CLIENT_ID")
        self.client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
        self.redirect_uri = os.environ.get("YOUTUBE_REDIRECT_URI", "https://sas-sigma.vercel.app/n1/youtube-callback")
        self.credentials = None
        self.youtube = None
    
    def _get_client_config(self) -> dict:
        """OAuth client config を生成"""
        return {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uris": [self.redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
    
    def authenticate(self, auth_code: Optional[str] = None) -> bool:
        """YouTube API 認証
        
        Args:
            auth_code: 認証コード（初回認証時に必要）
        
        Returns:
            認証成功したかどうか
        """
        # 保存済みトークンを確認
        if TOKEN_PATH.exists():
            with open(TOKEN_PATH, 'rb') as token:
                self.credentials = pickle.load(token)
        
        # トークンが有効か確認
        if self.credentials and self.credentials.valid:
            self._build_service()
            return True
        
        # トークンをリフレッシュ
        if self.credentials and self.credentials.expired and self.credentials.refresh_token:
            try:
                self.credentials.refresh(Request())
                self._save_token()
                self._build_service()
                return True
            except Exception as e:
                console.print(f"[yellow]トークンリフレッシュ失敗: {e}[/yellow]")
        
        # 認証コードがあれば交換
        if auth_code:
            return self._exchange_code(auth_code)
        
        # 認証が必要
        return False
    
    def get_auth_url(self) -> str:
        """認証URLを取得"""
        flow = InstalledAppFlow.from_client_config(
            self._get_client_config(),
            scopes=SCOPES,
            redirect_uri=self.redirect_uri
        )
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        return auth_url
    
    def _exchange_code(self, auth_code: str) -> bool:
        """認証コードをトークンに交換"""
        try:
            flow = InstalledAppFlow.from_client_config(
                self._get_client_config(),
                scopes=SCOPES,
                redirect_uri=self.redirect_uri
            )
            flow.fetch_token(code=auth_code)
            self.credentials = flow.credentials
            self._save_token()
            self._build_service()
            console.print("[green]✅ YouTube 認証成功[/green]")
            return True
        except Exception as e:
            console.print(f"[red]❌ 認証エラー: {e}[/red]")
            return False
    
    def _save_token(self):
        """トークンを保存"""
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(self.credentials, token)
        console.print(f"[green]トークンを保存: {TOKEN_PATH}[/green]")
    
    def _build_service(self):
        """YouTube API サービスを構築"""
        self.youtube = build('youtube', 'v3', credentials=self.credentials)
    
    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: list[str] = None,
        category_id: str = "25",  # News & Politics
        privacy_status: str = "public",
        is_shorts: bool = True,
    ) -> UploadResult:
        """動画をアップロード
        
        Args:
            video_path: 動画ファイルパス
            title: タイトル（最大100文字）
            description: 説明文
            tags: タグリスト
            category_id: カテゴリID (25=News & Politics, 22=People & Blogs, 24=Entertainment)
            privacy_status: public, private, unlisted
            is_shorts: Shorts として投稿するか
        
        Returns:
            UploadResult
        """
        if not self.youtube:
            if not self.authenticate():
                return UploadResult(
                    success=False,
                    error_message="認証が必要です。get_auth_url() で認証URLを取得してください。"
                )
        
        # Shorts用のタイトル調整
        if is_shorts and "#shorts" not in title.lower():
            if len(title) <= 93:  # 100 - len(" #Shorts")
                title = f"{title} #Shorts"
        
        # タグ調整
        if tags is None:
            tags = []
        if is_shorts and "Shorts" not in tags:
            tags.append("Shorts")
        
        body = {
            'snippet': {
                'title': title[:100],
                'description': description[:5000],
                'tags': tags[:500],
                'categoryId': category_id,
            },
            'status': {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': False,
            }
        }
        
        # 動画ファイル
        media = MediaFileUpload(
            video_path,
            mimetype='video/mp4',
            resumable=True,
            chunksize=1024*1024  # 1MB chunks
        )
        
        try:
            console.print(f"[cyan]📤 アップロード中: {video_path}[/cyan]")
            
            request = self.youtube.videos().insert(
                part='snippet,status',
                body=body,
                media_body=media
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    console.print(f"  進捗: {progress}%")
            
            video_id = response['id']
            video_url = f"https://www.youtube.com/shorts/{video_id}" if is_shorts else f"https://www.youtube.com/watch?v={video_id}"
            
            console.print(f"[green]✅ アップロード完了: {video_url}[/green]")
            
            return UploadResult(
                success=True,
                video_id=video_id,
                video_url=video_url,
            )
            
        except Exception as e:
            console.print(f"[red]❌ アップロードエラー: {e}[/red]")
            return UploadResult(
                success=False,
                error_message=str(e),
            )
    
    def get_channel_info(self) -> dict:
        """チャンネル情報を取得"""
        if not self.youtube:
            if not self.authenticate():
                return {}
        
        try:
            response = self.youtube.channels().list(
                part='snippet,statistics',
                mine=True
            ).execute()
            
            if response['items']:
                channel = response['items'][0]
                return {
                    'id': channel['id'],
                    'title': channel['snippet']['title'],
                    'subscribers': channel['statistics'].get('subscriberCount', 'N/A'),
                    'videos': channel['statistics'].get('videoCount', 'N/A'),
                }
        except Exception as e:
            console.print(f"[red]チャンネル情報取得エラー: {e}[/red]")
        
        return {}


# CLI用関数
def authenticate_youtube():
    """YouTube認証フロー（CLI用）"""
    from dotenv import load_dotenv
    load_dotenv()
    
    uploader = YouTubeUploader()
    
    # 既存の認証を確認
    if uploader.authenticate():
        console.print("[green]✅ 既存の認証が有効です[/green]")
        info = uploader.get_channel_info()
        if info:
            console.print(f"チャンネル: {info['title']}")
        return uploader
    
    # 認証URLを表示
    auth_url = uploader.get_auth_url()
    console.print(f"\n[cyan]以下のURLにアクセスして認証してください:[/cyan]")
    console.print(f"[link]{auth_url}[/link]\n")
    
    # 認証コードを入力
    auth_code = input("認証コードを入力: ").strip()
    
    if uploader.authenticate(auth_code):
        info = uploader.get_channel_info()
        if info:
            console.print(f"チャンネル: {info['title']}")
        return uploader
    
    return None


if __name__ == "__main__":
    authenticate_youtube()
