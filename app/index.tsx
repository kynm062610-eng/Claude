import React from 'react';
import { Redirect, router } from 'expo-router';
import { useSession } from '../src/lib/session';
import { BigButton, Body, Loading, Screen, Title } from '../src/components/ui';

/**
 * 起動時の振り分け。
 * 端末は「子ども用」か「保護者用」のどちらかとして紐づく。
 */
export default function Index() {
  const { loading, role } = useSession();

  if (loading) return <Loading />;
  if (role === 'child') return <Redirect href="/home" />;
  if (role === 'guardian') return <Redirect href="/guardian/console" />;

  return (
    <Screen>
      <Title>こうかんノート</Title>
      <Body>ともだちと 1さつの ノートを じゅんばんに まわして かくアプリだよ。</Body>
      <Body muted>
        はじめて つかうときは、おうちの人が とうろくしてから、子ども用の たんまつで
        「コードを いれる」を えらんでね。
      </Body>

      <BigButton label="子ども用：コードを いれる" onPress={() => router.push('/onboarding/child')} />
      <BigButton
        label="おうちの人：とうろくする"
        variant="secondary"
        onPress={() => router.push('/onboarding/guardian')}
      />
    </Screen>
  );
}
