import React from 'react';
import { AbsoluteFill, useVideoConfig } from 'remotion';

export interface NewsOverlayProps {
  channelName: string;
  headline: string;
  subHeadline?: string;
  subtitle?: string;
  isBreaking?: boolean;
  showBanner?: boolean; // 下部バナーを表示（最初のシーンのみ）
}

// FJ News 24 風のニュースオーバーレイ
export const NewsOverlay: React.FC<NewsOverlayProps> = ({
  channelName = 'FJ News 24',
  headline,
  subHeadline = '',
  subtitle = '',
  isBreaking = true,
  showBanner = true,
}) => {
  const { width, height } = useVideoConfig();
  
  const logoHeight = height * 0.045;
  const breakingHeight = height * 0.035;
  const headlineHeight = height * 0.11;
  const subHeadlineHeight = subHeadline ? height * 0.05 : 0;
  
  return (
    <AbsoluteFill>
      {/* チャンネルロゴ（上部）- 常時表示 */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: logoHeight,
          backgroundColor: 'rgba(200, 30, 30, 0.95)',
          display: 'flex',
          alignItems: 'center',
          paddingLeft: width * 0.05,
          opacity: 1,
        }}
      >
        <span
          style={{
            color: 'white',
            fontSize: logoHeight * 0.6,
            fontWeight: 'bold',
            fontFamily: '"Hiragino Sans", "Hiragino Kaku Gothic ProN", sans-serif',
            letterSpacing: '-0.02em',
          }}
        >
          {channelName}
        </span>
      </div>
      
      {/* 字幕（中央） */}
      {subtitle && (
        <div
          style={{
            position: 'absolute',
            top: '45%',
            left: 0,
            right: 0,
            transform: 'translateY(-50%)',
            textAlign: 'center',
            padding: '0 50px',
            opacity: 1,
          }}
        >
          <span
            style={{
              color: 'white',
              fontSize: height * 0.038,
              fontWeight: 600,
              fontFamily: '"Hiragino Sans", sans-serif',
              textShadow: '3px 3px 6px rgba(0,0,0,0.9), -1px -1px 3px rgba(0,0,0,0.6)',
              lineHeight: 1.5,
            }}
          >
            {subtitle}
          </span>
        </div>
      )}
      
      {/* 下部バナー - 右から左にスライドイン */}
      {showBanner && headline && (
        <div
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            opacity: 1,
          }}
        >
          {/* BREAKING NEWS ラベル */}
          {isBreaking && (
            <div
              style={{
                backgroundColor: 'rgba(200, 30, 30, 0.95)',
                display: 'inline-block',
                padding: `${breakingHeight * 0.15}px ${breakingHeight * 0.5}px`,
                marginBottom: 0,
              }}
            >
              <span
                style={{
                  color: 'white',
                  fontSize: breakingHeight * 0.65,
                  fontWeight: 'bold',
                  fontFamily: '"Hiragino Sans", sans-serif',
                }}
              >
                BREAKING NEWS
              </span>
            </div>
          )}
          
          {/* ヘッドライン（白背景 + 赤枠） */}
          <div
            style={{
              backgroundColor: 'rgba(200, 30, 30, 1)',
              padding: 6,
            }}
          >
            <div
              style={{
                backgroundColor: 'white',
                padding: `${headlineHeight * 0.08}px ${width * 0.05}px`,
                minHeight: headlineHeight - 12,
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <span
                style={{
                  color: 'black',
                  fontSize: headlineHeight * 0.38,
                  fontWeight: 'bold',
                  fontFamily: '"Hiragino Sans", "Hiragino Kaku Gothic ProN", sans-serif',
                  lineHeight: 1.3,
                }}
              >
                {headline}
              </span>
            </div>
          </div>
          
          {/* サブヘッドライン */}
          {subHeadline && (
            <div
              style={{
                backgroundColor: 'rgba(30, 30, 35, 0.9)',
                padding: `${subHeadlineHeight * 0.2}px ${width * 0.05}px`,
                height: subHeadlineHeight,
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <span
                style={{
                  color: 'rgba(230, 230, 230, 1)',
                  fontSize: subHeadlineHeight * 0.5,
                  fontFamily: '"Hiragino Sans", sans-serif',
                }}
              >
                {subHeadline}
              </span>
            </div>
          )}
        </div>
      )}
    </AbsoluteFill>
  );
};
