#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
orb_research.py の検証（合成データ・ネットワーク不要）。

バックテストの誠実さに直結する部分を重点的に確認する:
  - レンジが「セッション開始からrange_minutes分」だけで作られているか
  - ブレイク判定・約定価格・損切り・時間決済が仕様どおりか
  - 上下同時ブレイクを都合よく解釈せず、捨てているか
  - 損切り優先のタイブレークが効いているか
  - レンジ確定後の値動きだけを見ているか（先読みの排除）
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import orb_research as orb
from home_away_research import CostModel

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  [{'OK' if cond else 'NG'}] {name}" + (f"  {detail}" if detail else ""))


def _raises(fn) -> bool:
    try:
        fn()
    except Exception:
        return True
    return False


NY = orb.ORBSpec("NY", "newyork", "08:00", "17:00", "テスト用")
# コストゼロにして、値幅の計算そのものを検証する
NOCOST = CostModel(pip=0.01, spread_pips=0.0, slippage_pips=0.0)


def build_day(prices: dict, date: str = "2024-07-15", base: float = 150.0,
              n_min: int = 540) -> pd.DataFrame:
    """NYセッション(08:00-17:00 EDT = UTC 12:00-21:00)の1日分を作る。

    prices: {分オフセット: (high, low, close)} で任意の分だけ上書きする。
    """
    idx = pd.date_range(f"{date} 12:00", periods=n_min, freq="1min", tz="UTC")
    hi = np.full(n_min, base)
    lo = np.full(n_min, base)
    cl = np.full(n_min, base)
    for k, (h, l, c) in prices.items():
        hi[k], lo[k], cl[k] = h, l, c
    return pd.DataFrame({"open": cl, "high": hi, "low": lo, "close": cl,
                         "volume": 0}, index=idx)


def main() -> int:
    print("=" * 66)
    print(" orb_research.py 検証（合成データ）")
    print("=" * 66)

    # ------------------------------------------------------------------
    print("\n[1] レンジがセッション開始30分だけで作られるか")
    # 0-29分でレンジを 150.0〜150.2 に作り、30分目に150.5へ上抜けさせる。
    # 60分目にさらに大きな高値を置いても、レンジ自体は変わらないこと。
    day = build_day({5: (150.20, 150.00, 150.10),     # レンジ内の高値
                     10: (150.10, 149.90, 150.00),    # レンジ内の安値 → L=149.90
                     30: (150.50, 150.15, 150.45),    # 上抜け
                     60: (155.00, 150.40, 154.90)})   # 後の大きな動き
    res = orb.run_orb(day, NY, NOCOST, range_minutes=30, min_bars=10)
    check("トレードが1件成立する", len(res.trades) == 1, f"{len(res.trades)}件")
    if res.trades:
        t = res.trades[0]
        check("ロングとして判定される", t.side == "long", t.side)
        check("約定はレンジ高値ちょうど(150.20)", abs(t.entry - 150.20) < 1e-9,
              f"entry={t.entry}")
        check("レンジ確定後の1本目(30分目)で入る",
              t.ts_in == pd.Timestamp("2024-07-15 12:30", tz="UTC"), str(t.ts_in))

    # ------------------------------------------------------------------
    print("\n[2] 時間決済（損切りに当たらず終了まで持つ）")
    check("決済理由が時間切れ", bool(res.trades) and res.trades[0].reason == "time",
          res.trades[0].reason if res.trades else "-")
    if res.trades:
        t = res.trades[0]
        # 最終足の終値は base=150.0。150.20で買って150.0で終了 → 約-13.3bps
        expected = (150.0 / 150.20 - 1.0) * 1e4
        check("損益が終値ベースで正しい", abs(t.ret_bps - expected) < 1e-6,
              f"実際={t.ret_bps:.3f} 期待={expected:.3f} bps")

    # ------------------------------------------------------------------
    print("\n[3] 損切りがレンジ反対側で執行されるか")
    day2 = build_day({5: (150.20, 150.00, 150.10),
                      10: (150.10, 149.90, 150.00),   # L=149.90
                      30: (150.50, 150.15, 150.45),   # 上抜けでロング
                      45: (150.10, 149.80, 149.85)})  # Lを割る → 損切り
    r2 = orb.run_orb(day2, NY, NOCOST, range_minutes=30, min_bars=10)
    check("損切りとして決済される", bool(r2.trades) and r2.trades[0].reason == "stop",
          r2.trades[0].reason if r2.trades else "-")
    if r2.trades:
        t = r2.trades[0]
        expected = (149.90 / 150.20 - 1.0) * 1e4
        check("損切り価格はレンジ安値ちょうど",
              abs(t.ret_bps - expected) < 1e-6,
              f"実際={t.ret_bps:.3f} 期待={expected:.3f} bps")
        check("約定より不利な価格で切れている", t.ret_bps < 0)

    # ------------------------------------------------------------------
    print("\n[4] ショート側も対称に動くか")
    day3 = build_day({5: (150.20, 150.00, 150.10),
                      10: (150.10, 149.90, 150.00),
                      30: (149.95, 149.70, 149.75)})  # Lを下抜け → ショート
    r3 = orb.run_orb(day3, NY, NOCOST, range_minutes=30, min_bars=10)
    check("ショートとして判定される",
          bool(r3.trades) and r3.trades[0].side == "short",
          r3.trades[0].side if r3.trades else "-")
    if r3.trades:
        t = r3.trades[0]
        check("約定はレンジ安値ちょうど(149.90)", abs(t.entry - 149.90) < 1e-9,
              f"entry={t.entry}")
        # 149.90で売って最終足150.0で買い戻し → マイナス
        expected = (149.90 / 150.0 - 1.0) * 1e4
        check("ショートの損益計算が正しい", abs(t.ret_bps - expected) < 1e-6,
              f"実際={t.ret_bps:.3f} 期待={expected:.3f} bps")

    # ------------------------------------------------------------------
    print("\n[5] 上下同時ブレイクは都合よく解釈せず捨てるか（最重要）")
    day4 = build_day({5: (150.20, 150.00, 150.10),
                      10: (150.10, 149.90, 150.00),
                      30: (150.60, 149.70, 150.40)})  # 同じ足でH上抜け・L下抜け
    r4 = orb.run_orb(day4, NY, NOCOST, range_minutes=30, min_bars=10)
    check("トレードを作らない", len(r4.trades) == 0, f"{len(r4.trades)}件")
    check("除外件数として計上される", r4.sessions_ambiguous == 1,
          f"{r4.sessions_ambiguous}件")

    # ------------------------------------------------------------------
    print("\n[6] ブレイクしない日はトレードしないか")
    day5 = build_day({5: (150.20, 150.00, 150.10),
                      10: (150.10, 149.90, 150.00)})  # 以降ずっとレンジ内
    r5 = orb.run_orb(day5, NY, NOCOST, range_minutes=30, min_bars=10)
    check("トレードを作らない", len(r5.trades) == 0, f"{len(r5.trades)}件")
    check("ブレイクなしとして計上される", r5.sessions_no_break == 1,
          f"{r5.sessions_no_break}件")

    # ------------------------------------------------------------------
    print("\n[7] 損切り優先のタイブレーク（同じ足で損切りと終了に該当）")
    # 最終足で L を割る。時間決済ではなく損切りとして扱われること。
    day6 = build_day({5: (150.20, 150.00, 150.10),
                      10: (150.10, 149.90, 150.00),
                      30: (150.50, 150.15, 150.45),
                      539: (150.00, 149.50, 149.60)})  # 最終足でLを割る
    r6 = orb.run_orb(day6, NY, NOCOST, range_minutes=30, min_bars=10)
    check("損切りが優先される", bool(r6.trades) and r6.trades[0].reason == "stop",
          r6.trades[0].reason if r6.trades else "-")

    # ------------------------------------------------------------------
    print("\n[8] 先読みの排除（レンジ形成中の値動きでは入らない）")
    # レンジ期間内(20分目)にHを超える動きを置いても、そこでは入らない。
    # その足はレンジの一部としてHを押し上げるだけ。
    day7 = build_day({5: (150.20, 150.00, 150.10),
                      10: (150.10, 149.90, 150.00),
                      20: (150.80, 150.30, 150.70),   # レンジ内の高値 → H=150.80
                      35: (150.90, 150.50, 150.85)})  # レンジ確定後に上抜け
    r7 = orb.run_orb(day7, NY, NOCOST, range_minutes=30, min_bars=10)
    check("約定価格が更新後のレンジ高値(150.80)になる",
          bool(r7.trades) and abs(r7.trades[0].entry - 150.80) < 1e-9,
          f"entry={r7.trades[0].entry if r7.trades else None}")
    check("レンジ形成中の足では約定しない",
          bool(r7.trades) and r7.trades[0].ts_in >= pd.Timestamp(
              "2024-07-15 12:30", tz="UTC"),
          str(r7.trades[0].ts_in) if r7.trades else "-")

    # ------------------------------------------------------------------
    print("\n[9] コストが必ず不利側に効くか")
    cost = CostModel(pip=0.01, spread_pips=0.5, slippage_pips=0.3)
    r8 = orb.run_orb(day, NY, cost, range_minutes=30, min_bars=10)
    if r8.trades and res.trades:
        diff = res.trades[0].ret_bps - r8.trades[0].ret_bps
        # 0.8pips / 150.20 * 1e4 = 0.5326 bps
        expected = 0.8 * 0.01 / 150.20 * 1e4
        check("コストぶんだけ損益が悪化する", abs(diff - expected) < 1e-6,
              f"差={diff:.4f} 期待={expected:.4f} bps")
        check("コスト後のほうが必ず不利", r8.trades[0].ret_bps < res.trades[0].ret_bps)

    # ------------------------------------------------------------------
    print("\n[10] 短すぎるセッション（祝日等）は除外されるか")
    short = build_day({5: (150.2, 150.0, 150.1)}, n_min=20)
    r9 = orb.run_orb(short, NY, NOCOST, range_minutes=30, min_bars=60)
    check("対象セッションとして数えない", r9.sessions_total == 0,
          f"{r9.sessions_total}件")

    # ------------------------------------------------------------------
    print("\n[11] 約定前提 entry_mode='close'（1分足ポーリング実装の現実）")
    # 30分目の足: 高値150.50でブレイク、終値150.45。
    #   level なら 150.20（レンジ高値）で約定
    #   close なら 150.45（その足の終値）で約定 ← 0.25円ぶん不利
    r_lv = orb.run_orb(day, NY, NOCOST, range_minutes=30, min_bars=10,
                       entry_mode="level")
    r_cl = orb.run_orb(day, NY, NOCOST, range_minutes=30, min_bars=10,
                       entry_mode="close")
    check("level約定はレンジ高値(150.20)",
          bool(r_lv.trades) and abs(r_lv.trades[0].entry - 150.20) < 1e-9,
          f"entry={r_lv.trades[0].entry if r_lv.trades else None}")
    check("close約定はブレイク足の終値(150.45)",
          bool(r_cl.trades) and abs(r_cl.trades[0].entry - 150.45) < 1e-9,
          f"entry={r_cl.trades[0].entry if r_cl.trades else None}")
    check("close約定のほうが必ず不利になる（買いなら高く買う）",
          bool(r_lv.trades) and bool(r_cl.trades)
          and r_cl.trades[0].ret_bps < r_lv.trades[0].ret_bps,
          f"level={r_lv.trades[0].ret_bps:.3f} close={r_cl.trades[0].ret_bps:.3f} bps")

    # ショートでも不利側になること（安く売ってしまう）
    r_lv_s = orb.run_orb(day3, NY, NOCOST, range_minutes=30, min_bars=10,
                         entry_mode="level")
    r_cl_s = orb.run_orb(day3, NY, NOCOST, range_minutes=30, min_bars=10,
                         entry_mode="close")
    check("ショートでもclose約定が不利側（149.90→149.75で売る）",
          bool(r_cl_s.trades) and abs(r_cl_s.trades[0].entry - 149.75) < 1e-9,
          f"entry={r_cl_s.trades[0].entry if r_cl_s.trades else None}")
    check("ショートでもclose約定のほうが損益が悪い",
          bool(r_lv_s.trades) and bool(r_cl_s.trades)
          and r_cl_s.trades[0].ret_bps < r_lv_s.trades[0].ret_bps,
          f"level={r_lv_s.trades[0].ret_bps:.3f} "
          f"close={r_cl_s.trades[0].ret_bps:.3f} bps")

    check("不正なentry_modeは例外にする",
          _raises(lambda: orb.run_orb(day, NY, NOCOST, entry_mode="market")))

    # ------------------------------------------------------------------
    print("\n[12] min_delay_min（指標発表の瞬間を避ける設定）")
    # day は30分目＝レンジ確定直後(delay=0)にブレイクする
    r_d0 = orb.run_orb(day, NY, NOCOST, range_minutes=30, min_bars=10,
                       min_delay_min=0)
    r_d1 = orb.run_orb(day, NY, NOCOST, range_minutes=30, min_bars=10,
                       min_delay_min=1)
    check("delay=0のブレイクは既定では採用される", len(r_d0.trades) == 1)
    check("min_delay_min=1 で見送られる", len(r_d1.trades) == 0,
          f"{len(r_d1.trades)}件")
    check("見送り件数として計上される", r_d1.sessions_skipped_delay == 1,
          f"{r_d1.sessions_skipped_delay}件")
    # 35分目にブレイクする day7 は delay=5 なので min_delay_min=1 でも残る
    r_d7 = orb.run_orb(day7, NY, NOCOST, range_minutes=30, min_bars=10,
                       min_delay_min=1)
    check("遅いブレイク(delay=5)は見送られない", len(r_d7.trades) == 1,
          f"{len(r_d7.trades)}件")

    print("\n" + "=" * 66)
    print(f" {len(PASS)}/{len(PASS)+len(FAIL)} 件成功")
    if FAIL:
        print(" 失敗:")
        for f in FAIL:
            print(f"   - {f}")
    print("=" * 66)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
