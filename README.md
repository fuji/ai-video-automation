# AI Video Automation

SDK-based AI video production pipeline using Gemini API, KLING AI, and YouTube Data API.

## Features

- **Content Planning**: AI-generated video concepts with Gemini API
- **Image Generation**: High-quality images with Gemini 2.5 Flash Image
- **Video Generation**: Dynamic videos with KLING AI SDK
- **Video Editing**: FFmpeg + MoviePy for professional editing
- **YouTube Upload**: Direct upload with YouTube Data API v3
- **News Automation**: Automatic news video generation with ElevenLabs narration

## System Architecture

```
src/
├── config.py                   # Configuration management
├── logger.py                   # Logging with progress bars
├── generators/
│   ├── content_planner.py      # Gemini concept generation
│   ├── image_generator.py      # Gemini image generation
│   ├── video_generator.py      # KLING video generation
│   ├── narration_generator.py  # ElevenLabs voice synthesis
│   └── news_explainer.py       # Gemini news explanation
├── editors/
│   ├── video_editor.py         # FFmpeg + MoviePy editing
│   ├── video_animator.py       # Ken Burns animation effects
│   └── subtitle_renderer.py    # FFmpeg subtitle burning
├── pipeline/
│   ├── automation.py           # Full automation pipeline
│   └── news_automation.py      # News video pipeline
├── utils/
│   ├── trend_detector.py       # Google Trends + RSS integration
│   ├── rss_fetcher.py          # Yahoo!/NHK RSS feeds
│   └── news_scraper.py         # Article scraping
└── monetization/
    └── uploader.py             # YouTube upload
```

## Quick Start

### 1. Installation

```bash
cd /Users/fuji/work/fuji/ai-video-automation

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install FFmpeg (macOS)
brew install ffmpeg
```

### 2. API Keys Setup

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

#### Gemini API (Required)

1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Click "Get API Key"
3. Create or select a project
4. Copy the API key to `GEMINI_API_KEY`

#### KLING AI (Required for video generation)

1. Go to [KLING AI](https://klingai.com/global/)
2. Create an account and login
3. Open DevTools (F12) → Application → Cookies
4. Copy all cookies as a string to `KLING_COOKIE`

#### YouTube API (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project
3. Enable YouTube Data API v3
4. Create OAuth 2.0 credentials
5. Download `client_secrets.json` to project root

#### ElevenLabs API (Required for News Narration)

1. Go to [ElevenLabs](https://elevenlabs.io/)
2. Create an account
3. Go to Profile → API Keys
4. Copy the API key to `ELEVENLABS_API_KEY`

#### NewsAPI (Optional - for trend detection)

1. Go to [NewsAPI](https://newsapi.org/)
2. Create an account
3. Copy the API key to `NEWSAPI_KEY`

### 3. Run

```bash
# Full pipeline
python main.py run --theme "サイバーパンク都市" --style cinematic --scenes 3

# Generate concept only
python main.py concept --theme "未来宇宙" --output project.json

# Upload to YouTube
python main.py upload --video output/final/video.mp4 --title "AI Video"

# Daily news video generation (2 videos)
python main.py daily --count 2

# Check configuration
python main.py config
```

## Usage Examples

### Basic Usage

```bash
# Create 3-scene cyberpunk video
python main.py run -t "サイバーパンク都市" -s cinematic -n 3

# Create video with background music
python main.py run -t "ファンタジー風景" -a bgm/epic.mp3

# Skip image generation (use existing images)
python main.py run -t "未来宇宙" --skip-images

# Create and upload to YouTube
python main.py run -t "和風モダン" --upload
```

### News Automation

```bash
# Generate 2 daily news videos automatically
python main.py daily --count 2

# Manual news selection
python main.py daily --count 2 --manual

# Generate from specific URL
python main.py news --url "https://example.com/news/article" --duration 60

# With different difficulty level
python main.py daily --difficulty 小学生 --voice Rachel

# Auto-upload to YouTube after generation
python main.py daily --count 2 --upload
```

### Voice Narration Quota Management

ElevenLabs フリープラン（月10,000文字）のクォータを自動追跡します。

```bash
# Check remaining quota
python -c "
from src.generators.narration_generator import NarrationGenerator
n = NarrationGenerator()
status = n.get_quota_status()
print(f'Month: {status[\"month\"]}')
print(f'Used: {status[\"used\"]:,}/{status[\"limit\"]:,} chars')
print(f'Remaining: {status[\"remaining\"]:,} chars')
print(f'Usage: {status[\"usage_percentage\"]:.1f}%')
"
```

### Trend Detection (Free)

Google Trends + Yahoo!/NHK RSS で完全無料のトレンド検知。

```bash
# Check current trending keywords
python -c "
from src.utils.trend_detector import TrendDetector
detector = TrendDetector()
keywords = detector.get_trending_keywords(5)
print('Trending Keywords:')
for i, kw in enumerate(keywords, 1):
    print(f'  {i}. {kw}')
"

# Get best news for video
python -c "
from src.utils.trend_detector import TrendDetector
detector = TrendDetector()
news = detector.get_best_news(3)
for n in news:
    print(f'[{n.score}pt] {n.title[:50]}...')
"
```

### Python API

```python
from src.pipeline import VideoPipeline

pipeline = VideoPipeline()
pipeline.initialize()

# Generate concept
project = pipeline.generate_project("サイバーパンク都市", "cinematic", 3)

# Generate images
images = pipeline.generate_images(project)

# Generate videos
videos = pipeline.generate_videos(project)

# Create final video
final = pipeline.create_final_video(project)
```

### News Automation API

```python
from src.pipeline.news_automation import NewsAutomationPipeline
from src.utils.trend_detector import TrendDetector

# Daily automated generation
pipeline = NewsAutomationPipeline()
results = pipeline.run_daily(count=2)

for result in results:
    if result.success:
        print(f"Created: {result.video_path}")

# Manual news selection
detector = TrendDetector()
news_list = detector.get_best_news(count=5)

for news in news_list:
    result = pipeline.run(
        news=news,
        difficulty="中学生",
        target_duration=60,
        voice="Rachel",
    )
```

## Configuration

All settings can be configured via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Gemini API key | (required) |
| `GEMINI_MODEL_IMAGE` | Image generation model | gemini-2.0-flash-exp-image-generation |
| `KLING_COOKIE` | KLING authentication cookie | (required for video) |
| `KLING_MODE` | Video quality (std/pro) | std |
| `KLING_DURATION` | Video duration (5/10) | 5 |
| `VIDEO_RESOLUTION` | Output resolution | 1920x1080 |
| `VIDEO_FPS` | Frame rate | 30 |
| `ELEVENLABS_API_KEY` | ElevenLabs API key | (required for news) |
| `NEWSAPI_KEY` | NewsAPI key | (optional) |

## Troubleshooting

### "GEMINI_API_KEY not set"

Set your Gemini API key in `.env`:
```
GEMINI_API_KEY=AIzaSyXXXXXXXXXXXX
```

### "KLING_COOKIE not set"

1. Login to [klingai.com](https://klingai.com)
2. Open DevTools → Application → Cookies
3. Copy cookies to `.env`

### "FFmpeg not found"

Install FFmpeg:
```bash
# macOS
brew install ffmpeg

# Ubuntu
sudo apt install ffmpeg
```

### Video generation timeout

Increase timeout in `.env`:
```
KLING_TIMEOUT=900
KLING_POLL_INTERVAL=60
```

### YouTube upload fails

1. Ensure `client_secrets.json` exists
2. Delete `youtube_credentials.json` and re-authenticate
3. Check API quota in Google Cloud Console

### "ELEVENLABS_API_KEY not set"

Set your ElevenLabs API key in `.env`:
```
ELEVENLABS_API_KEY=your_key_here
```

### News scraping fails

1. Ensure `beautifulsoup4` and `newspaper3k` are installed
2. Check if the news site blocks scraping
3. Try a different news source

## Project Structure

```
ai-video-automation/
├── main.py                 # CLI entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Environment template
├── .gitignore             # Git ignore rules
├── README.md              # This file
├── SETUP.md               # Detailed setup guide
├── src/                   # Source code
│   ├── __init__.py
│   ├── config.py
│   ├── logger.py
│   ├── generators/
│   ├── editors/
│   ├── pipeline/
│   └── monetization/
├── output/                # Generated content
│   ├── images/
│   ├── videos/
│   └── final/
└── logs/                  # Application logs
```

## License

MIT License

## See Also

- [SETUP.md](./SETUP.md) - Detailed setup guide
- [Google AI Studio](https://aistudio.google.com/)
- [KLING AI](https://klingai.com/)
- [YouTube Data API](https://developers.google.com/youtube/v3)
