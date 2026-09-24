#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dow_mtf_research.py の検証（合成データ・ネットワーク不要）。

バックテストの誠実さに直結する部分を重点的に確認する:
  - スイングは右側k本が確定するまで使えない（先読みの排除）
  - 上位足は確定した足だけを使う
  - 損切り・利確・時間切れ・同じ足で両方に触れた場合の扱い
  - 窓で損切りを飛び越えたら始値で約定する（水準で約定したことにしない）
  - 未来のデータを削っても、過去のエントリーが変わらない（全体の先読みテスト）
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import dow_mtf_research as dm
from home_away_research import CostModel

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  [{'OK' if cond else 'NG'}] {name}" + (f"  {detail}" if detail else ""))


NOCOST = CostModel(pip=0.01, spread_pips=0.0, slippage_pips=0.0)


def m1_frame(close: np.ndarray, start: str = "2024-07-15 00:00",
             spread: float = 0.0) -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(close), freq="1min", tz="UTC")
    o = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, close) + spread,
                         "low": np.minimum(o, close) - spread, "close": close,
                         "volume": 0}, index=idx)


def test_find_swings() -> None:
    print("\n[スイングの判定]")
    h = np.array([1, 2, 3, 9, 3, 2, 1, 5, 5, 4, 3, 2, 1], dtype=float)
    l = h - 0.5
    sh, sl = dm.find_swings(h, l, k=3)
    check("左右3本より高い足がスイング高値", sh[3] and sh.sum() == 1,
          f"位置={np.nonzero(sh)[0].tolist()}")
    check("同値が並ぶ山(5,5)はスイング扱いしない", not sh[7] and not sh[8])
    check("端の3本は判定しない", not sh[:3].any() and not sh[-3:].any())
    v = np.array([5, 4, 3, 1, 3, 4, 5], dtype=float)
    _, sl2 = dm.find_swings(v + 0.5, v, k=3)
    check("谷はスイング安値", sl2[3])


def test_swing_state_no_lookahead() -> None:
    print("\n[スイングは右側k本の確定後にしか使えない]")
    h = np.array([1, 2, 3, 9, 3, 2, 1, 1, 1, 1], dtype=float)
    bars = pd.DataFrame({"high": h, "low": h - 0.5})
    st = dm.swing_state(bars, k=3)
    check("位置3のスイングは位置5の時点では未確定", np.isnan(st.sh_last[5]))
    check("位置6（=3+3）で確定して使える", st.sh_last[6] == 9 and st.sh_last_idx[6] == 3)
    h2 = np.array([1, 2, 3, 9, 3, 2, 1, 2, 3, 7, 3, 2, 1, 1], dtype=float)
    st2 = dm.swing_state(pd.DataFrame({"high": h2, "low": h2 - 0.5}), k=3)
    check("2つ目のスイング確定後、直近=7・前回=9",
          st2.sh_last[12] == 7 and st2.sh_prev[12] == 9)
    check("2つ目の確定前は、前回は未設定", np.isnan(st2.sh_prev[11]))


def test_htf_uses_closed_bars_only() -> None:
    print("\n[上位足は確定した足だけを使う]")
    idx = pd.date_range("2024-07-15 00:00", periods=16, freq="1h", tz="UTC")
    # スイング高値: 位置3(=9)・位置9(=10)  スイング安値: 位置5(=2)・位置12(=3.5)
    h = np.array([5, 5, 5, 9, 6, 5, 4, 6, 7, 10, 7, 6, 5, 5, 5, 5], dtype=float)
    l = np.array([3, 3, 3, 5, 4, 2, 3, 4, 5, 8, 6, 5, 3.5, 4, 4, 4], dtype=float)
    htf = pd.DataFrame({"open": l, "high": h, "low": l, "close": h}, index=idx)
    st = dm.swing_state(htf, k=3)
    # 位置9の高値が確定するのは位置12の足の確定時 = 12:00開始 → 13:00確定
    # 位置12の安値が確定するのは位置15の足の確定時 = 15:00開始 → 16:00確定
    q = pd.DatetimeIndex([pd.Timestamp(f"2024-07-15 {hm}", tz="UTC")
                          for hm in ("12:55", "13:00", "15:55", "16:00")])
    up, down, tl, _ = dm.htf_trend_at(htf, st, pd.Timedelta("1h"), q)
    check("確定前(12:55)は位置9の高値をまだ使わない", tl[0] == 9, f"target={tl[0]}")
    check("確定後(13:00)に使える", tl[1] == 10, f"target={tl[1]}")
    check("安値が1つしか確定していない間(15:55)は目線なし", not up[2] and not down[2])
    check("高値・安値とも切り上げ(16:00) → 上昇", up[3] and not down[3])


def test_simulate_exit() -> None:
    print("\n[1分足での決済判定]")
    ts = pd.date_range("2024-07-15 00:00", periods=6, freq="1min", tz="UTC").as_unit("ns").asi8
    hold = pd.Timedelta(hours=24).value

    def run(o, h, l, c, side="long", stop=99.0, tgt=102.0, hold_ns=hold):
        return dm.simulate_exit(ts, np.array(o, float), np.array(h, float),
                                np.array(l, float), np.array(c, float), 0, side,
                                stop, tgt, hold_ns)

    base = [100] * 6
    j, px, why, amb = run(base, [100, 100, 102.5, 100, 100, 100], base, base)
    check("利確は水準ちょうど", (j, px, why) == (2, 102.0, "target"))
    j, px, why, amb = run(base, base, [100, 100, 98.5, 100, 100, 100], base)
    check("損切りは水準で約定", (j, px, why) == (2, 99.0, "stop"))
    j, px, why, amb = run(base, [100, 102.5, 100, 100, 100, 100],
                          [100, 98.5, 100, 100, 100, 100], base)
    check("同じ足で両方 → 損切り優先", why == "stop" and amb, f"{why} amb={amb}")
    j, px, why, amb = run([100, 100, 97, 97, 97, 97], [100, 100, 97.5, 97, 97, 97],
                          [100, 100, 96.5, 97, 97, 97], base)
    check("窓で損切りを飛び越えたら始値で約定", why == "stop" and px == 97.0, f"px={px}")
    j, px, why, amb = run(base, [100, 100, 100, 100, 100, 100], base,
                          [100, 100.1, 100.2, 100.3, 100.4, 100.5],
                          hold_ns=pd.Timedelta(minutes=3).value)
    check("時間切れは期限内最後の足の終値", (j, why) == (2, "time") and px == 100.2,
          f"j={j} px={px}")
    j, px, why, amb = run(base, [100, 101, 100, 100, 100, 100],
                          [100, 97, 100, 100, 100, 100], base, side="short",
                          stop=101.0, tgt=98.0)
    check("売り: 同じ足で両方 → 損切り優先", why == "stop" and px == 101.0 and amb)
    j, px, why, amb = run(base, [100, 100, 100.5, 100, 100, 100],
                          [100, 101.5, 100, 100, 100, 100], base, side="long",
                          stop=99.0, tgt=102.0)
    check("エントリー足そのものは判定に使わない", why == "time")


def _random_walk(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    steps = rng.standard_t(4, size=n) * 0.004
    close = 150.0 + np.cumsum(steps)
    df = m1_frame(close, start="2024-01-01 00:00", spread=0.002)
    # 週末（土日）を落として、実データと同じ欠損を作る
    return df[df.index.dayofweek < 5]


def test_end_to_end_invariants() -> None:
    print("\n[合成データでの通し実行と不変条件]")
    df = _random_walk(60 * 24 * 60, seed=7)
    res = dm.run_dow_mtf(df, NOCOST)
    tr = res.trades
    check("トレードが発生する", len(tr) > 20, f"{len(tr)}件")
    ok_order = all(t.ts_out >= t.ts_in for t in tr)
    no_overlap = all(tr[i + 1].ts_in > tr[i].ts_out for i in range(len(tr) - 1))
    check("決済はエントリー以降", ok_order)
    check("建玉は同時に1つまで", no_overlap)
    check("エントリーは5分足の最後の1分足（分が4,9,…）",
          all(t.ts_in.minute % 5 == 4 for t in tr))
    check("保有は24時間以内", all(t.ts_out - t.ts_in <= pd.Timedelta(hours=24) for t in tr))
    no_weekend = all(t.ts_out.dayofweek < 5 for t in tr)
    check("週末をまたいで保有しない（金曜の最後の足で手仕舞い）", no_weekend)
    check("ロング・ショートの両方が出る", res.n_long > 0 and res.n_short > 0,
          f"L={res.n_long} S={res.n_short}")


def test_no_future_dependence() -> None:
    print("\n[先読みテスト: 未来を削っても過去のエントリーは変わらない]")
    df = _random_walk(60 * 24 * 60, seed=11)
    full = dm.run_dow_mtf(df, NOCOST).trades
    cut = df.index[len(df) // 2]
    part = dm.run_dow_mtf(df[df.index < cut], NOCOST).trades
    # 途中で切ったデータ側で「決済まで完了した」トレードまでは完全一致するはず
    part_done = [t for t in part if t.ts_out < cut - pd.Timedelta(hours=24)]
    full_keys = [(t.ts_in, t.side, t.entry, t.ts_out, t.exit) for t in full]
    part_keys = [(t.ts_in, t.side, t.entry, t.ts_out, t.exit) for t in part_done]
    check("比較対象が十分ある", len(part_keys) > 10, f"{len(part_keys)}件")
    check("エントリー・決済とも完全一致", full_keys[:len(part_keys)] == part_keys)


def main() -> int:
    test_find_swings()
    test_swing_state_no_lookahead()
    test_htf_uses_closed_bars_only()
    test_simulate_exit()
    test_end_to_end_invariants()
    test_no_future_dependence()
    print(f"\n結果: {len(PASS)} OK / {len(FAIL)} NG")
    if FAIL:
        print("NG: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
