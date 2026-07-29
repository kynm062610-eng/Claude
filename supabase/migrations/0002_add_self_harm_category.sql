-- safety_alerts のカテゴリに self_harm を追加する。
--
-- 「死にたい」「消えたい」など、他人への攻撃ではなく本人の自傷リスクを示す表現を
-- violence とは別カテゴリとして扱うための変更。既存の制約を張り替える。

alter table public.safety_alerts drop constraint safety_alerts_category_check;

alter table public.safety_alerts
  add constraint safety_alerts_category_check
  check (category in ('violence', 'self_harm', 'exclusion', 'insult', 'personal_info'));
