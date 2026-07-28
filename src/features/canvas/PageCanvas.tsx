import React, { useMemo } from 'react';
import { StyleSheet, Text, View, type LayoutChangeEvent } from 'react-native';
import { Canvas, Path, Skia } from '@shopify/react-native-skia';
import { backgroundColor } from '../../data/assets';
import { stampEmoji } from '../../data/assets';
import { CANVAS_HEIGHT, CANVAS_WIDTH, type PageContent, type StrokeElement } from '../../types';
import { colors, radius } from '../../theme';

export function strokeToPath(stroke: StrokeElement) {
  const path = Skia.Path.Make();
  if (stroke.points.length === 0) return path;

  path.moveTo(stroke.points[0][0], stroke.points[0][1]);
  for (let i = 1; i < stroke.points.length; i += 1) {
    path.lineTo(stroke.points[i][0], stroke.points[i][1]);
  }
  // 1 点だけのタップも見えるように、ごく短い線分を足す
  if (stroke.points.length === 1) {
    path.lineTo(stroke.points[0][0] + 0.1, stroke.points[0][1] + 0.1);
  }
  return path;
}

/**
 * ページの描画。
 *
 * ストロークは Skia、テキストとスタンプは通常の RN View を重ねて描く。
 * Skia でテキストを描くにはフォントの読み込みが必要で、絵文字も扱いにくいため、
 * MVP では表示レイヤーを分ける。座標系はどちらも 1080x1440 の固定キャンバス。
 */
export function PageCanvas({
  content,
  liveStroke,
  onLayoutSize,
  children,
}: {
  content: PageContent;
  /** 描画中のストローク（確定前） */
  liveStroke?: StrokeElement | null;
  onLayoutSize?: (width: number, height: number) => void;
  children?: React.ReactNode;
}) {
  const [size, setSize] = React.useState({ width: 0, height: 0 });

  const handleLayout = (event: LayoutChangeEvent) => {
    const { width } = event.nativeEvent.layout;
    const height = (width * CANVAS_HEIGHT) / CANVAS_WIDTH;
    setSize({ width, height });
    onLayoutSize?.(width, height);
  };

  const scale = size.width > 0 ? size.width / CANVAS_WIDTH : 0;

  const strokes = useMemo(
    () => content.elements.filter((el): el is StrokeElement => el.type === 'stroke'),
    [content.elements],
  );

  return (
    <View
      onLayout={handleLayout}
      style={[
        styles.page,
        { backgroundColor: backgroundColor(content.background), height: size.height || undefined },
      ]}
    >
      {scale > 0 && (
        <>
          <Canvas style={StyleSheet.absoluteFill}>
            {[...strokes, ...(liveStroke ? [liveStroke] : [])].map((stroke, index) => (
              <Path
                key={index}
                path={strokeToPath(stroke)}
                color={stroke.color}
                style="stroke"
                strokeWidth={stroke.width * scale}
                strokeCap="round"
                strokeJoin="round"
                transform={[{ scale }]}
              />
            ))}
          </Canvas>

          {content.elements.map((element, index) => {
            if (element.type === 'text') {
              return (
                <Text
                  key={`t-${index}`}
                  style={[
                    styles.overlay,
                    {
                      left: element.x * scale,
                      top: element.y * scale,
                      fontSize: element.size * scale,
                      color: element.color,
                    },
                  ]}
                >
                  {element.text}
                </Text>
              );
            }
            if (element.type === 'stamp') {
              return (
                <Text
                  key={`s-${index}`}
                  style={[
                    styles.overlay,
                    {
                      left: element.x * scale,
                      top: element.y * scale,
                      fontSize: 96 * element.scale * scale,
                      transform: [{ rotate: `${element.rotation}rad` }],
                    },
                  ]}
                >
                  {stampEmoji(element.key)}
                </Text>
              );
            }
            return null;
          })}
        </>
      )}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  page: {
    width: '100%',
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: 'hidden',
  },
  overlay: { position: 'absolute' },
});
