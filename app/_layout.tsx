import React, { useEffect } from 'react';
import { Stack, router } from 'expo-router';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import * as Notifications from 'expo-notifications';
import { SessionProvider } from '../src/lib/session';
import { configureNotificationHandler } from '../src/lib/push';
import { colors } from '../src/theme';

configureNotificationHandler();

export default function RootLayout() {
  // 通知をタップしたら、該当のノートを開く
  useEffect(() => {
    const subscription = Notifications.addNotificationResponseReceivedListener((response) => {
      const notebookId = response.notification.request.content.data?.notebookId;
      if (typeof notebookId === 'string' && notebookId.length > 0) {
        router.push(`/notebook/${notebookId}`);
      }
    });
    return () => subscription.remove();
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <SessionProvider>
          <StatusBar style="dark" />
          <Stack
            screenOptions={{
              headerStyle: { backgroundColor: colors.bg },
              headerTintColor: colors.text,
              headerTitleStyle: { fontWeight: '800' },
              contentStyle: { backgroundColor: colors.bg },
            }}
          >
            <Stack.Screen name="index" options={{ headerShown: false }} />
            <Stack.Screen name="onboarding/guardian" options={{ title: 'おうちの人の とうろく' }} />
            <Stack.Screen name="onboarding/child" options={{ title: 'はじめる' }} />
            <Stack.Screen name="home" options={{ title: 'こうかんノート' }} />
            <Stack.Screen name="group/join" options={{ title: 'グループに はいる' }} />
            <Stack.Screen name="group/[id]" options={{ title: 'グループ' }} />
            <Stack.Screen name="notebook/[id]" options={{ title: 'ノート' }} />
            <Stack.Screen name="page/new" options={{ title: 'ページを かく' }} />
            <Stack.Screen name="page/[id]" options={{ title: 'ページ' }} />
            <Stack.Screen name="settings" options={{ title: 'せってい' }} />
            <Stack.Screen name="profile/edit" options={{ title: 'プロフィール' }} />
            <Stack.Screen name="profile/[childId]" options={{ title: 'プロフィール' }} />
            <Stack.Screen name="guardian/console" options={{ title: '保護者メニュー' }} />
          </Stack>
        </SessionProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
