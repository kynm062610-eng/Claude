import React, { useMemo, useState } from 'react';
import { StyleSheet, View, type LayoutChangeEvent } from 'react-native';
import { Canvas, Circle, Path, Rect, Skia } from '@shopify/react-native-skia';
import {
  TREE_CANVAS_HEIGHT,
  TREE_CANVAS_WIDTH,
  TREE_GROUND_Y,
  buildTreeGeometry,
  seasonColors,
} from './treeGeometry';
import { radius } from '../../theme';
import type { Season } from './treeStage';

/**
 * みんなで育てた木を描く。画像素材は使わず、枝は線・葉と花は円で描く。
 * 形はノート ID から決定的に決まるので、開くたびに変わることはない。
 */
export function TreeView({
  level,
  season,
  seed,
}: {
  level: number;
  season: Season;
  seed: string;
}) {
  const [width, setWidth] = useState(0);

  const handleLayout = (event: LayoutChangeEvent) => {
    setWidth(event.nativeEvent.layout.width);
  };

  const geometry = useMemo(() => buildTreeGeometry(level, season, seed), [level, season, seed]);
  const colors = seasonColors[season];

  const scale = width > 0 ? width / TREE_CANVAS_WIDTH : 0;
  const height = TREE_CANVAS_HEIGHT * scale;

  return (
    <View onLayout={handleLayout} style={[styles.container, { height: height || undefined }]}>
      {scale > 0 && (
        <Canvas style={StyleSheet.absoluteFill}>
          {/* 空 */}
          <Rect x={0} y={0} width={width} height={height} color={colors.sky} />
          {/* 地面 */}
          <Rect
            x={0}
            y={TREE_GROUND_Y * scale}
            width={width}
            height={height - TREE_GROUND_Y * scale}
            color={colors.ground}
          />

          {/* 枝（太さが違うので 1 本ずつ描く） */}
          {geometry.branches.map((branch, index) => {
            const path = Skia.Path.Make();
            path.moveTo(branch.x1 * scale, branch.y1 * scale);
            path.lineTo(branch.x2 * scale, branch.y2 * scale);
            return (
              <Path
                key={`b-${index}`}
                path={path}
                color={colors.trunk}
                style="stroke"
                strokeWidth={Math.max(1, branch.width * scale)}
                strokeCap="round"
              />
            );
          })}

          {/* 葉と花 */}
          {geometry.foliage.map((item, index) => (
            <Circle
              key={`f-${index}`}
              cx={item.x * scale}
              cy={item.y * scale}
              r={item.r * scale}
              color={item.blossom ? colors.blossom : colors.leaf}
              opacity={0.9}
            />
          ))}
        </Canvas>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    width: '100%',
    borderRadius: radius.md,
    overflow: 'hidden',
  },
});
