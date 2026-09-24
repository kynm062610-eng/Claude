#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
home_away_research.py の検証（合成データ・ネットワーク不要）。

確認したいこと:
  - 事前予測の方向が、仮説から正しく導出されているか（手書きミス・後付けの排除）
  - セッションの切り出しが、各市場の現地時間（夏時間込み）で行われているか
  - コスト控除が仕様どおりか（往復1スプレッド、pip幅はペア依存）
  - セッションのリターンが、そのセッション内のバーだけから計算されているか
    （先読みの排除）
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import fx_data as fx
import home_away_research as ha

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  [{'OK' if cond else 'NG'}] {name}" + (f"  {detail}" if detail else ""))


def make_utc_frame(start: str, periods: int, price: float = 150.0,
                   freq: str = "1min") -> pd.DataFrame:
    idx = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    return pd.DataFrame({"open": price, "high": price, "low": price,
                         "close": price, "volume": 0}, index=idx)


def main() -> int:
    print("=" * 66)
    print(" home_away_research.py 検証（合成データ）")
    print("=" * 66)

    # ------------------------------------------------------------------
    print("\n[1] 事前予測が仮説から正しく導出されるか（USDJPY）")
    s = {x.market: x for x in ha.build_sessions("USDJPY")}
    check("東京はロング（円=QUOTEが売られる→USD/JPY上昇）",
          s["tokyo"].hypothesis_side == "long", s["tokyo"].hypothesis_side)
    check("NYはショート（ドル=BASEが売られる→USD/JPY下落）",
          s["newyork"].hypothesis_side == "short", s["newyork"].hypothesis_side)
    check("ロンドンは予測なし（どちらもアウェイ）",
          s["london"].hypothesis_side == "", repr(s["london"].hypothesis_side))

    print("\n[2] 事前予測が仮説から正しく導出されるか（EURUSD）")
    e = {x.market: x for x in ha.build_sessions("EURUSD")}
    check("ロンドンはショート（ユーロ=BASEが売られる→EUR/USD下落）",
          e["london"].hypothesis_side == "short", e["london"].hypothesis_side)
    check("NYはロング（ドル=QUOTEが売られる→EUR/USD上昇）",
          e["newyork"].hypothesis_side == "long", e["newyork"].hypothesis_side)
    check("東京は予測なし（円が絡まない）",
          e["tokyo"].hypothesis_side == "", repr(e["tokyo"].hypothesis_side))

    print("\n[2b] 逆方向のペアでも整合するか（JPYがBASEのケース）")
    j = {x.market: x for x in ha.build_sessions("JPYUSD")}  # 実在しないが論理の確認
    check("JPYがBASEなら東京はショート",
          j["tokyo"].hypothesis_side == "short", j["tokyo"].hypothesis_side)
    check("USDがQUOTEならNYはロング",
          j["newyork"].hypothesis_side == "long", j["newyork"].hypothesis_side)

    # ------------------------------------------------------------------
    print("\n[3] pip幅がペアごとに正しいか")
    check("USDJPYは0.01", ha.pip_size("USDJPY") == 0.01)
    check("EURUSDは0.0001", ha.pip_size("EURUSD") == 0.0001)
    check("EURJPYは0.01（JPYクロス）", ha.pip_size("EURJPY") == 0.01)

    # ------------------------------------------------------------------
    print("\n[4] セッションの切り出しが現地時間（夏時間込み）で行われるか")
    # 2024-07-15(月) はNYが夏時間(EDT=UTC-4)。NYセッション08:00-17:00 EDT は
    # UTC では 12:00-21:00 にあたる。
    df = make_utc_frame("2024-07-15 00:00", periods=60 * 24)
    spec_ny = {x.market: x for x in ha.build_sessions("USDJPY")}["newyork"]
    bars = ha.extract_sessions(df, spec_ny, min_bars=10)
    check("NYセッションが1本切り出される", len(bars) == 1, f"{len(bars)}本")
    if bars:
        b = bars[0]
        check("開始がUTC12:00（=NY 08:00 EDT）", b.ts_in.hour == 12,
              f"実際={b.ts_in.hour}時")
        check("終了がUTC20:59（=NY 16:59 EDT）", b.ts_out.hour == 20,
              f"実際={b.ts_out.hour}時")

    # 冬（2024-01-15）はEST=UTC-5なので、UTCでは13:00-22:00にずれる
    df_w = make_utc_frame("2024-01-15 00:00", periods=60 * 24)
    bars_w = ha.extract_sessions(df_w, spec_ny, min_bars=10)
    check("冬はUTC13:00開始にずれる（夏時間を正しく反映）",
          bool(bars_w) and bars_w[0].ts_in.hour == 13,
          f"実際={bars_w[0].ts_in.hour if bars_w else None}時")

    # 東京は夏時間が無いので、夏冬ともUTC00:00開始（=JST09:00）
    spec_tk = {x.market: x for x in ha.build_sessions("USDJPY")}["tokyo"]
    bt_s = ha.extract_sessions(make_utc_frame("2024-07-15 00:00", 60 * 24), spec_tk, 10)
    bt_w = ha.extract_sessions(make_utc_frame("2024-01-15 00:00", 60 * 24), spec_tk, 10)
    check("東京は夏冬とも同じUTC時刻で始まる（夏時間なし）",
          bool(bt_s) and bool(bt_w) and bt_s[0].ts_in.hour == bt_w[0].ts_in.hour == 0,
          f"夏={bt_s[0].ts_in.hour if bt_s else None}時 "
          f"冬={bt_w[0].ts_in.hour if bt_w else None}時")

    # ------------------------------------------------------------------
    print("\n[5] セッションのリターンが、そのセッション内だけで計算されるか（先読み排除）")
    # セッション外（NY時間の後）に大きな値動きを置いても、結果が変わらないこと
    idx = pd.date_range("2024-07-15 00:00", periods=60 * 24, freq="1min", tz="UTC")
    px = pd.Series(150.0, index=idx)
    # NYセッション(UTC12:00-20:59)の中だけ、150.00→150.90へ緩やかに上昇させる。
    # これで「セッション内だけの変動」による既知のリターンが作れる。
    sess = (idx >= pd.Timestamp("2024-07-15 12:00", tz="UTC")) & \
           (idx <= pd.Timestamp("2024-07-15 20:59", tz="UTC"))
    n_sess = int(sess.sum())
    px[sess] = np.linspace(150.0, 150.9, n_sess)
    base = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 0})
    b1 = ha.extract_sessions(base, spec_ny, min_bars=10)
    expected = (150.9 / 150.0 - 1.0) * 1e4   # ≈ +60 bps
    check("セッション内の変動が正しくリターンになる",
          bool(b1) and abs(b1[0].ret_bps - expected) < 1e-6,
          f"実際={b1[0].ret_bps:.3f} 期待={expected:.3f} bps")

    # 場外（セッション終了後）で急騰させても、結果が変わらないこと
    spiked = base.copy()
    spiked.loc["2024-07-15 21:30":, ["open", "high", "low", "close"]] = 200.0
    b2 = ha.extract_sessions(spiked, spec_ny, min_bars=10)
    check("セッション外の値動きはリターンに影響しない",
          bool(b1) and bool(b2) and abs(b1[0].ret_bps - b2[0].ret_bps) < 1e-9,
          f"{b1[0].ret_bps:.3f} vs {b2[0].ret_bps:.3f} bps")
    check("その比較が自明でない（リターンがゼロでない）",
          bool(b1) and abs(b1[0].ret_bps) > 1.0, f"{b1[0].ret_bps:.3f} bps")

    # ------------------------------------------------------------------
    print("\n[6] コスト控除が仕様どおりか")
    # 150円で 0.5+0.1=0.6pips → 0.6*0.01/150*1e4 = 0.4 bps
    cm = ha.CostModel(pip=0.01, spread_pips=0.5, slippage_pips=0.1)
    check("USDJPY 150円で往復コスト=0.4bps",
          abs(cm.cost_bps(150.0) - 0.4) < 1e-9, f"{cm.cost_bps(150.0):.4f} bps")
    # EURUSD 1.10で 0.6pips → 0.6*0.0001/1.10*1e4 = 0.545 bps
    cm_e = ha.CostModel(pip=0.0001, spread_pips=0.5, slippage_pips=0.1)
    check("EURUSD 1.10で往復コスト≈0.545bps",
          abs(cm_e.cost_bps(1.10) - 0.5454545) < 1e-6, f"{cm_e.cost_bps(1.10):.4f} bps")

    print("\n[7] ロング／ショートの符号とコストの向き")
    sb = ha.SessionBar(date_local=pd.Timestamp("2024-07-15"),
                       ts_in=pd.Timestamp("2024-07-15 12:00", tz="UTC"),
                       ts_out=pd.Timestamp("2024-07-15 20:59", tz="UTC"),
                       open=150.0, close=150.15, high=150.2, low=149.9,
                       bars=540, ret_bps=10.0)
    tl = ha.sessions_to_trades([sb], "long", cm)[0]
    ts_ = ha.sessions_to_trades([sb], "short", cm)[0]
    check("ロングは +10bps からコストを引く", abs(tl.ret_bps - (10.0 - 0.4)) < 1e-9,
          f"{tl.ret_bps:.3f}")
    check("ショートは -10bps からコストを引く", abs(ts_.ret_bps - (-10.0 - 0.4)) < 1e-9,
          f"{ts_.ret_bps:.3f}")
    check("どちらの向きでもコストは必ず不利側に効く",
          tl.ret_bps < 10.0 and ts_.ret_bps < -10.0)

    # ------------------------------------------------------------------
    print("\n[8] t検定の妥当性")
    rng = np.random.default_rng(12345)
    noise = rng.normal(0, 30, 5000)
    t0, p0 = ha.t_test_mean_zero(noise)
    check("平均ゼロのノイズは有意にならない", p0 > 0.20, f"p={p0:.3f}")
    shifted = noise + 5.0     # 5bpsの明確なバイアス
    t1, p1 = ha.t_test_mean_zero(shifted)
    check("明確なバイアスは有意として検出される", p1 < 0.001, f"p={p1:.2e}")
    check("t値の符号が平均の符号と一致", t1 > 0 and t0 == t0)

    # ------------------------------------------------------------------
    print("\n[9] 最小バー数に満たないセッションは除外されるか")
    short_df = make_utc_frame("2024-07-15 12:00", periods=5)   # NYセッション内5本だけ
    few = ha.extract_sessions(short_df, spec_ny, min_bars=60)
    check("短すぎるセッション（祝日等）は捨てる", len(few) == 0, f"{len(few)}本")

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
