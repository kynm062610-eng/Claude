import React, { useCallback, useRef, useState } from 'react';
import { View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { runOnJS } from 'react-native-reanimated';
import { CANVAS_WIDTH, type PageContent, type StrokeElement } from '../../types';
import { PageCanvas } from './PageCanvas';

export type Tool =
  | { kind: 'pen'; color: string; width: number }
  | { kind: 'eraser' }
  | { kind: 'stamp'; stampKey: string };

/**
 * 描けるキャンバス。
 *
 * ストロークは確定するまで state に持ち、指を離した時点で content に積む。
 * 消しゴムは「最後のストロークを消す」方式。小学生には部分消しより分かりやすく、
 * 誤操作からの復帰も速い。
 */
export function DrawingCanvas({
  content,
  onChange,
  tool,
}: {
  content: PageContent;
  onChange: (next: PageContent) => void;
  tool: Tool;
}) {
  const [liveStroke, setLiveStroke] = useState<StrokeElement | null>(null);
  const scaleRef = useRef(0);

  const handleLayoutSize = useCallback((width: number) => {
    scaleRef.current = width / CANVAS_WIDTH;
  }, []);

  const toCanvas = useCallback((x: number, y: number): [number, number] => {
    const scale = scaleRef.current || 1;
    return [x / scale, y / scale];
  }, []);

  const beginStroke = useCallback(
    (x: number, y: number) => {
      if (tool.kind !== 'pen') return;
      setLiveStroke({
        type: 'stroke',
        color: tool.color,
        width: tool.width,
        points: [toCanvas(x, y)],
      });
    },
    [tool, toCanvas],
  );

  const extendStroke = useCallback(
    (x: number, y: number) => {
      setLiveStroke((prev) =>
        prev ? { ...prev, points: [...prev.points, toCanvas(x, y)] } : prev,
      );
    },
    [toCanvas],
  );

  const commitStroke = useCallback(() => {
    setLiveStroke((prev) => {
      if (prev && prev.points.length > 0) {
        onChange({ ...content, elements: [...content.elements, prev] });
      }
      return null;
    });
  }, [content, onChange]);

  const placeStamp = useCallback(
    (x: number, y: number) => {
      if (tool.kind !== 'stamp') return;
      const [cx, cy] = toCanvas(x, y);
      onChange({
        ...content,
        elements: [
          ...content.elements,
          { type: 'stamp', key: tool.stampKey, x: cx - 48, y: cy - 48, scale: 1, rotation: 0 },
        ],
      });
    },
    [content, onChange, tool, toCanvas],
  );

  const eraseLast = useCallback(() => {
    if (content.elements.length === 0) return;
    onChange({ ...content, elements: content.elements.slice(0, -1) });
  }, [content, onChange]);

  const pan = Gesture.Pan()
    .minDistance(0)
    .onBegin((event) => {
      'worklet';
      runOnJS(beginStroke)(event.x, event.y);
    })
    .onUpdate((event) => {
      'worklet';
      runOnJS(extendStroke)(event.x, event.y);
    })
    .onFinalize(() => {
      'worklet';
      runOnJS(commitStroke)();
    });

  const tap = Gesture.Tap().onEnd((event) => {
    'worklet';
    if (tool.kind === 'stamp') {
      runOnJS(placeStamp)(event.x, event.y);
    } else {
      runOnJS(eraseLast)();
    }
  });

  const gesture = tool.kind === 'pen' ? pan : tap;

  return (
    <GestureDetector gesture={gesture}>
      <View>
        <PageCanvas
          content={content}
          liveStroke={liveStroke}
          onLayoutSize={handleLayoutSize}
        />
      </View>
    </GestureDetector>
  );
}
