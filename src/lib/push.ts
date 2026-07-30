import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import { setMyPushToken } from '../api';

/**
 * プッシュ通知の登録。
 *
 * 通知が必要なのは「自分の番が来たこと」を知らせるためだけ。回覧制で自分の番は
 * 数回に 1 回しか来ないので、アプリを開かないと気づけないのが継続の一番の障害になる。
 *
 * 送る側（サーバー）は Postgres のトリガーから直接 Expo の API を叩く
 * （supabase/migrations/0004_push_notifications.sql）。トークンを
 * クライアントに配らずに済むため。
 */

/** 通知の受け取り方。アプリを開いている間もバナーを出す。 */
export function configureNotificationHandler() {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
}

export type PushRegistrationResult =
  | { status: 'registered'; token: string }
  | { status: 'denied' }
  | { status: 'unsupported'; reason: string };

/**
 * 通知の許可を求め、取得したトークンを保存する。
 * 子どものプロフィールが確定したあとに一度だけ呼ぶ。
 */
export async function registerForPushNotifications(): Promise<PushRegistrationResult> {
  // エミュレータ・シミュレータでは実機トークンが発行されない
  if (!Device.isDevice) {
    return { status: 'unsupported', reason: 'not_a_physical_device' };
  }

  if (Platform.OS === 'android') {
    // Android は通知チャンネルが必須。作らないと通知が表示されない。
    await Notifications.setNotificationChannelAsync('default', {
      name: 'おしらせ',
      importance: Notifications.AndroidImportance.DEFAULT,
      vibrationPattern: [0, 250, 250, 250],
    });
  }

  const existing = await Notifications.getPermissionsAsync();
  let granted = existing.granted;

  if (!granted && existing.canAskAgain) {
    const asked = await Notifications.requestPermissionsAsync();
    granted = asked.granted;
  }

  if (!granted) {
    return { status: 'denied' };
  }

  const projectId =
    Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;

  if (!projectId) {
    // EAS のプロジェクト ID が無いと Expo のプッシュトークンを発行できない
    return { status: 'unsupported', reason: 'missing_project_id' };
  }

  const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
  await setMyPushToken(token);

  return { status: 'registered', token };
}
