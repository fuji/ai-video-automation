import React from 'react';
import { Composition } from 'remotion';
import { NewsScene, SceneData, NewsSceneProps } from './NewsScene';

// デフォルトのシーンデータ（テスト用）
const defaultScene: SceneData = {
  sceneNumber: 1,
  duration: 5,
  background: {
    type: 'gradient',
    colors: ['#FF6B6B', '#FF8E53'],
  },
  elements: [
    {
      type: 'emoji',
      content: '🐱',
      style: { size: 'xxl' },
      position: { x: 'center', y: 'top', offsetY: 300 },
      animation: { enter: 'bounce-in', delay: 0 },
    },
    {
      type: 'text',
      content: '250km',
      style: { size: 'xxl', weight: 'black', color: '#FFFFFF' },
      position: { x: 'center', y: 'center' },
      animation: { enter: 'count-up', delay: 0.3 },
    },
    {
      type: 'text',
      content: '歩いて帰った猫!?',
      style: { size: 'lg', weight: 'bold', color: '#FFFFFF' },
      position: { x: 'center', y: 'center', offsetY: 120 },
      animation: { enter: 'pop-in', delay: 1.0 },
    },
  ],
  narration: {
    subtitle: '250km歩いて帰った猫!?',
  },
};

const FPS = 30;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="NewsScene"
        component={NewsScene as unknown as React.FC<Record<string, unknown>>}
        fps={FPS}
        width={1080}
        height={1920}
        durationInFrames={300} // デフォルト10秒（calculateMetadataで上書き）
        defaultProps={{
          scene: defaultScene,
          width: 1080,
          height: 1920,
        }}
        calculateMetadata={({ props }: { props: Record<string, unknown> }) => {
          // props.scene.duration から動的にフレーム数を計算
          const scene = props.scene as SceneData | undefined;
          const duration = scene?.duration ?? 5;
          const durationInFrames = Math.ceil(duration * FPS);
          return {
            durationInFrames,
            width: (props.width as number) || 1080,
            height: (props.height as number) || 1920,
          };
        }}
      />
    </>
  );
};
