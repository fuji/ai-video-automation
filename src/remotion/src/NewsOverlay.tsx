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
      {/* チャンネルロゴ（右上）- 楕円罫線 + 白イタリックテキスト */}
      <div
        style={{
          position: 'absolute',
          top: height * 0.02,
          right: width * 0.03,
        }}
      >
        <svg
          width={width * 0.144}
          height={height * 0.048}
          viewBox="0 0 120 40"
        >
          {/* 2px の楕円罫線 */}
          <ellipse
            cx="60"
            cy="20"
            rx="56"
            ry="17"
            fill="none"
            stroke="rgba(255, 255, 255, 0.5)"
            strokeWidth="2"
          />
          {/* 白イタリックテキスト */}
          <text
            x="60"
            y="20"
            textAnchor="middle"
            dominantBaseline="central"
            fontSize="26"
            fontWeight="bold"
            fontStyle="italic"
            fontFamily="Helvetica Neue, Arial, sans-serif"
            fill="rgba(255, 255, 255, 0.5)"
          >
            {channelName}
          </text>
        </svg>
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
                display: 'inline-flex',
                alignItems: 'flex-end',
                justifyContent: 'center',
                height: breakingHeight,
                paddingLeft: breakingHeight * 0.5,
                paddingRight: breakingHeight * 0.5,
                paddingBottom: breakingHeight * 0.15,
                marginBottom: 0,
              }}
            >
              <span
                style={{
                  color: 'white',
                  fontSize: breakingHeight * 0.55,
                  fontWeight: 'bold',
                  fontFamily: '"Hiragino Sans", sans-serif',
                  lineHeight: 1,
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
