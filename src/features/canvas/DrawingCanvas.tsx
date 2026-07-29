import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { runOnJS } from 'react-native-reanimated';
import { CANVAS_WIDTH, type PageContent, type PageElement, type StrokeElement } from '../../types';
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

  // 確定した要素（ストローク・スタンプ）はいったんこのコンポーネント自身の state に
  // 持つ。ジェスチャー由来の更新をここで setElements するのは「自分の state を
  // 自分で更新する」だけなので常に安全。
  //
  // 親（NewPage）の content への反映は下の useEffect でのみ行う。
  // 以前はジェスチャーのコールバックから直接 onChange（親の setState）を呼んでいたため、
  // 親が別の場所を描画している最中に親の state を更新してしまい、React の
  // 「別のコンポーネントを描画中に更新しようとした」という警告が出ていた。
  // useEffect は必ず描画が確定したあとに実行されるので、この警告が構造的に起きなくなる。
  const [elements, setElements] = useState<PageElement[]>(content.elements);

  const contentRef = useRef(content);
  contentRef.current = content;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const isFirstRun = useRef(true);
  useEffect(() => {
    if (isFirstRun.current) {
      isFirstRun.current = false;
      return;
    }
    onChangeRef.current({ ...contentRef.current, elements });
  }, [elements]);

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
        setElements((els) => [...els, prev]);
      }
      return null;
    });
  }, []);

  const placeStamp = useCallback(
    (x: number, y: number) => {
      if (tool.kind !== 'stamp') return;
      const [cx, cy] = toCanvas(x, y);
      setElements((els) => [
        ...els,
        { type: 'stamp', key: tool.stampKey, x: cx - 48, y: cy - 48, scale: 1, rotation: 0 },
      ]);
    },
    [tool, toCanvas],
  );

  const eraseLast = useCallback(() => {
    setElements((els) => (els.length === 0 ? els : els.slice(0, -1)));
  }, []);

  const pan = useMemo(
    () =>
      Gesture.Pan()
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
        }),
    [beginStroke, extendStroke, commitStroke],
  );

  const tap = useMemo(
    () =>
      Gesture.Tap().onEnd((event) => {
        'worklet';
        if (tool.kind === 'stamp') {
          runOnJS(placeStamp)(event.x, event.y);
        } else {
          runOnJS(eraseLast)();
        }
      }),
    [tool, placeStamp, eraseLast],
  );

  const gesture = useMemo(() => (tool.kind === 'pen' ? pan : tap), [tool.kind, pan, tap]);

  // 表示用: 背景などは親の content（最新）から、要素はこのコンポーネントの
  // ローカル state（最新）から合成する。親への反映を待たずに描画へ即時反映できる。
  const displayContent = useMemo(() => ({ ...content, elements }), [content, elements]);

  return (
    <GestureDetector gesture={gesture}>
      <View>
        <PageCanvas
          content={displayContent}
          liveStroke={liveStroke}
          onLayoutSize={handleLayoutSize}
        />
      </View>
    </GestureDetector>
  );
}
