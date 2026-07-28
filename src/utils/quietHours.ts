/**
 * 夜間の書き込み制限。
 * 既定は 21:00〜翌 6:00。保護者コンソールから変更できる。
 */
export function isQuietHours(
  now: Date,
  startHour: number,
  endHour: number,
): boolean {
  const hour = now.getHours();

  if (startHour === endHour) {
    return false; // 制限なし
  }
  if (startHour < endHour) {
    // 日をまたがない（例: 1 時〜6 時）
    return hour >= startHour && hour < endHour;
  }
  // 日をまたぐ（例: 21 時〜6 時）
  return hour >= startHour || hour < endHour;
}

export function quietHoursMessage(startHour: number, endHour: number): string {
  return `いまは おやすみの じかんだよ。${endHour}じ から また かけるよ。（${startHour}じ〜${endHour}じ）`;
}
