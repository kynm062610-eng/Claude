import React from 'react';
import { Stack } from 'expo-router';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { SessionProvider } from '../src/lib/session';
import { colors } from '../src/theme';

export default function RootLayout() {
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
            <Stack.Screen name="guardian/console" options={{ title: '保護者メニュー' }} />
          </Stack>
        </SessionProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
