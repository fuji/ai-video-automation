#!/usr/bin/env python3
"""
ニュース動画エージェント CLI

Clawdbotから呼び出し用:
  python news_cli.py fetch          # 候補取得
  python news_cli.py select 1       # 選択して生成
  python news_cli.py status         # ステータス確認
"""

import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.agents.news_agent import NewsVideoAgent


def main():
    if len(sys.argv) < 2:
        print("Usage: python news_cli.py [fetch|select <num>|status]")
        sys.exit(1)
    
    cmd = sys.argv[1].lower()
    agent = NewsVideoAgent()
    
    if cmd == "fetch":
        print(agent.fetch_candidates())
    
    elif cmd == "select":
        if len(sys.argv) < 3:
            print("Usage: python news_cli.py select <number|skip|auto|URL>")
            sys.exit(1)
        selection = " ".join(sys.argv[2:])
        print(agent.select_article(selection))
    
    elif cmd == "status":
        print(agent.get_status())
    
    else:
        print(f"Unknown command: {cmd}")
        print("Available: fetch, select, status")
        sys.exit(1)


if __name__ == "__main__":
    main()
