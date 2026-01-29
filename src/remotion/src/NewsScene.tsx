import React from 'react';
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Img,
  staticFile,
} from 'remotion';
import { NewsOverlay } from './NewsOverlay';

// シーンデータの型定義
export interface SceneData {
  sceneNumber: number;
  duration: number;
  // アニメーション進捗の範囲（0-1）。同じ画像グループで継続的なアニメーションを実現
  animationStart?: number;  // デフォルト 0
  animationEnd?: number;    // デフォルト 1
  background: {
    type: 'gradient' | 'solid' | 'image';
    colors?: string[];
    imagePath?: string;
  };
  elements: Array<{
    type: 'text' | 'emoji' | 'number';
    content: string;
    style: {
      size: 'sm' | 'md' | 'lg' | 'xl' | 'xxl';
      weight?: 'normal' | 'bold' | 'black';
      color?: string;
    };
    position: {
      x: 'left' | 'center' | 'right';
      y: 'top' | 'center' | 'bottom';
      offsetX?: number;
      offsetY?: number;
    };
    animation: {
      enter: string;
      delay?: number;
    };
  }>;
  // ニュースオーバーレイ設定
  newsOverlay?: {
    channelName?: string;
    headline?: string;
    subHeadline?: string;
    isBreaking?: boolean;
    showOverlay?: boolean;
  };
  narration?: {
    subtitle: string;
  };
}

export interface NewsSceneProps {
  scene: SceneData;
  width: number;
  height: number;
}

const FONT_SIZES = {
  sm: 32,
  md: 48,
  lg: 72,
  xl: 96,
  xxl: 128,
};

// アニメーション付きテキストコンポーネント
const AnimatedElement: React.FC<{
  element: SceneData['elements'][0];
  width: number;
  height: number;
}> = ({ element, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  
  const delayFrames = (element.animation.delay || 0) * fps;
  const animFrame = Math.max(0, frame - delayFrames);
  
  // スプリングアニメーション
  const progress = spring({
    frame: animFrame,
    fps,
    config: { damping: 12, stiffness: 100 },
  });
  
  // 登場アニメーション
  const getAnimationStyle = (): React.CSSProperties => {
    switch (element.animation.enter) {
      case 'fade-in':
        return { opacity: progress };
      
      case 'fade-in-up':
        return {
          opacity: progress,
          transform: `translateY(${interpolate(progress, [0, 1], [50, 0])}px)`,
        };
      
      case 'slide-in-left':
        return {
          opacity: progress,
          transform: `translateX(${interpolate(progress, [0, 1], [-200, 0])}px)`,
        };
      
      case 'slide-in-right':
        return {
          opacity: progress,
          transform: `translateX(${interpolate(progress, [0, 1], [200, 0])}px)`,
        };
      
      case 'zoom-in':
        return {
          opacity: progress,
          transform: `scale(${interpolate(progress, [0, 1], [0.5, 1])})`,
        };
      
      case 'bounce-in':
        const bounceProgress = spring({
          frame: animFrame,
          fps,
          config: { damping: 8, stiffness: 200 },
        });
        return {
          opacity: Math.min(bounceProgress * 2, 1),
          transform: `scale(${bounceProgress})`,
        };
      
      case 'pop-in':
        const popProgress = spring({
          frame: animFrame,
          fps,
          config: { damping: 10, stiffness: 300 },
        });
        return {
          opacity: popProgress,
          transform: `scale(${popProgress})`,
        };
      
      case 'count-up':
        const num = parseFloat(element.content.replace(/[^0-9.]/g, ''));
        if (!isNaN(num)) {
          const countProgress = interpolate(animFrame, [0, fps * 1.5], [0, num], {
            extrapolateRight: 'clamp',
          });
          return {
            opacity: 1,
            '--content': `"${Math.floor(countProgress)}${element.content.replace(/[0-9.]/g, '')}"`,
          } as React.CSSProperties;
        }
        return { opacity: 1 };
      
      default:
        return { opacity: progress };
    }
  };
  
  // ポジション計算
  const getPosition = (): React.CSSProperties => {
    const pos: React.CSSProperties = { position: 'absolute' };
    
    const offsetX = element.position.offsetX || 0;
    const offsetY = element.position.offsetY || 0;
    
    switch (element.position.x) {
      case 'left':
        pos.left = 50 + offsetX;
        break;
      case 'center':
        pos.left = '50%';
        pos.transform = 'translateX(-50%)';
        break;
      case 'right':
        pos.right = 50 - offsetX;
        break;
    }
    
    switch (element.position.y) {
      case 'top':
        pos.top = 100 + offsetY;
        break;
      case 'center':
        pos.top = '50%';
        pos.transform = (pos.transform || '') + ' translateY(-50%)';
        break;
      case 'bottom':
        pos.bottom = 100 - offsetY;
        break;
    }
    
    return pos;
  };
  
  const fontSize = FONT_SIZES[element.style.size] || FONT_SIZES.md;
  const animStyle = getAnimationStyle();
  
  // count-up の場合は content を上書き
  const displayContent = element.animation.enter === 'count-up' 
    ? (() => {
        const num = parseFloat(element.content.replace(/[^0-9.]/g, ''));
        if (!isNaN(num)) {
          const countProgress = interpolate(animFrame, [0, fps * 1.5], [0, num], {
            extrapolateRight: 'clamp',
          });
          return Math.floor(countProgress) + element.content.replace(/[0-9.]/g, '');
        }
        return element.content;
      })()
    : element.content;
  
  const style: React.CSSProperties = {
    ...getPosition(),
    fontSize,
    fontWeight: element.style.weight === 'black' ? 900 : element.style.weight === 'bold' ? 700 : 400,
    color: element.style.color || '#FFFFFF',
    textAlign: 'center',
    textShadow: '2px 2px 8px rgba(0,0,0,0.5)',
    fontFamily: '"Hiragino Sans", "Hiragino Kaku Gothic ProN", sans-serif',
    ...animStyle,
  };
  
  return <div style={style}>{displayContent}</div>;
};

// Ken Burns アニメーションパターン
type KenBurnsPattern = 'zoom-in' | 'zoom-out' | 'pan-left' | 'pan-right' | 'pan-up' | 'pan-down' | 'zoom-pan-left' | 'zoom-pan-right';

const getKenBurnsTransform = (
  pattern: KenBurnsPattern,
  progress: number
): { scale: number; translateX: number; translateY: number } => {
  switch (pattern) {
    case 'zoom-in':
      return {
        scale: interpolate(progress, [0, 1], [1.0, 1.2]),
        translateX: 0,
        translateY: 0,
      };
    case 'zoom-out':
      return {
        scale: interpolate(progress, [0, 1], [1.2, 1.0]),
        translateX: 0,
        translateY: 0,
      };
    case 'pan-left':
      return {
        scale: 1.15,
        translateX: interpolate(progress, [0, 1], [30, -30]),
        translateY: 0,
      };
    case 'pan-right':
      return {
        scale: 1.15,
        translateX: interpolate(progress, [0, 1], [-30, 30]),
        translateY: 0,
      };
    case 'pan-up':
      return {
        scale: 1.15,
        translateX: 0,
        translateY: interpolate(progress, [0, 1], [20, -20]),
      };
    case 'pan-down':
      return {
        scale: 1.15,
        translateX: 0,
        translateY: interpolate(progress, [0, 1], [-20, 20]),
      };
    case 'zoom-pan-left':
      return {
        scale: interpolate(progress, [0, 1], [1.0, 1.15]),
        translateX: interpolate(progress, [0, 1], [20, -20]),
        translateY: interpolate(progress, [0, 1], [0, -10]),
      };
    case 'zoom-pan-right':
      return {
        scale: interpolate(progress, [0, 1], [1.0, 1.15]),
        translateX: interpolate(progress, [0, 1], [-20, 20]),
        translateY: interpolate(progress, [0, 1], [0, -10]),
      };
    default:
      return { scale: 1.1, translateX: 0, translateY: 0 };
  }
};

// シーン番号からアニメーションパターンを決定
const ANIMATION_PATTERNS: KenBurnsPattern[] = [
  'zoom-in',
  'pan-left',
  'zoom-out',
  'pan-right',
  'zoom-pan-left',
  'pan-up',
  'zoom-pan-right',
  'pan-down',
];

// 背景コンポーネント（Ken Burns エフェクト付き）
const Background: React.FC<{
  background: SceneData['background'];
  width: number;
  height: number;
  sceneNumber?: number;
  animationStart?: number;
  animationEnd?: number;
}> = ({ background, width, height, sceneNumber = 1, animationStart = 0, animationEnd = 1 }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const time = frame / fps;
  
  if (background.type === 'image' && background.imagePath) {
    // シーン番号に基づいてアニメーションパターンを選択
    const patternIndex = (sceneNumber - 1) % ANIMATION_PATTERNS.length;
    const pattern = ANIMATION_PATTERNS[patternIndex];
    
    // フレーム進捗を animationStart ~ animationEnd の範囲にマッピング
    const frameProgress = frame / durationInFrames;
    const progress = animationStart + frameProgress * (animationEnd - animationStart);
    const { scale, translateX, translateY } = getKenBurnsTransform(pattern, progress);
    
    // public ディレクトリからの相対パスとして処理
    const imageSrc = staticFile(background.imagePath);
    
    return (
      <div style={{ width, height, overflow: 'hidden' }}>
        <Img
          src={imageSrc}
          style={{
            width: width,
            height: height,
            objectFit: 'cover',
            transform: `scale(${scale}) translate(${translateX}px, ${translateY}px)`,
          }}
        />
      </div>
    );
  }
  
  // グラデーション背景
  const colors = background.colors || ['#667eea', '#764ba2'];
  const angle = 135 + Math.sin(time * 0.5) * 10; // 軽くアニメーション
  
  return (
    <div
      style={{
        width,
        height,
        background: `linear-gradient(${angle}deg, ${colors.join(', ')})`,
      }}
    />
  );
};

// メインのシーンコンポーネント
export const NewsScene: React.FC<NewsSceneProps> = ({ scene, width, height }) => {
  // newsOverlay オブジェクトがあれば常にオーバーレイを表示（ロゴ + 字幕）
  const hasNewsOverlay = !!scene.newsOverlay;
  
  return (
    <AbsoluteFill>
      {/* 背景 */}
      <Background 
        background={scene.background} 
        width={width} 
        height={height} 
        sceneNumber={scene.sceneNumber}
        animationStart={scene.animationStart}
        animationEnd={scene.animationEnd}
      />
      
      {/* 要素（ニュースオーバーレイがない場合のみ表示） */}
      {!hasNewsOverlay && scene.elements.map((element, index) => (
        <AnimatedElement
          key={index}
          element={element}
          width={width}
          height={height}
        />
      ))}
      
      {/* ニュースオーバーレイ（TV ニュース風） */}
      {hasNewsOverlay && (
        <NewsOverlay
          channelName={scene.newsOverlay?.channelName || 'FJ News 24'}
          headline={scene.newsOverlay?.headline || ''}
          subHeadline={scene.newsOverlay?.subHeadline}
          subtitle={scene.narration?.subtitle}
          isBreaking={scene.newsOverlay?.isBreaking ?? true}
          showBanner={scene.newsOverlay?.showOverlay ?? true}
        />
      )}
      
      {/* 字幕（ニュースオーバーレイがない場合） */}
      {!hasNewsOverlay && scene.narration?.subtitle && (
        <div
          style={{
            position: 'absolute',
            bottom: 150,
            left: 0,
            right: 0,
            textAlign: 'center',
            padding: '0 40px',
          }}
        >
          <div
            style={{
              display: 'inline-block',
              backgroundColor: 'rgba(0, 0, 0, 0.75)',
              padding: '12px 24px',
              borderRadius: 8,
              color: '#ffffff',
              fontSize: 36,
              fontWeight: 600,
              fontFamily: '"Hiragino Sans", sans-serif',
            }}
          >
            {scene.narration.subtitle}
          </div>
        </div>
      )}
    </AbsoluteFill>
  );
};
