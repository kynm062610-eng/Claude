#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_reversal_research.py の検証（合成データ・ネットワーク不要）。

バックテストの誠実さに直結する部分を重点的に確認する:
  - フィキシング時刻を各市場の現地時間（夏時間込み）で正しく置いているか
  - エントリー・決済は「その時刻に確定している1分足の終値」で、先の足を見ていないか
  - ドル売りの方向が通貨ペアごとに正しいか
  - 欠損日・週末を都合よく埋めずに見送っているか
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import fix_reversal_research as fr
from home_away_research import CostModel

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  [{'OK' if cond else 'NG'}] {name}" + (f"  {detail}" if detail else ""))


NOCOST_JPY = CostModel(pip=0.01, spread_pips=0.0, slippage_pips=0.0)
NOCOST_EUR = CostModel(pip=0.0001, spread_pips=0.0, slippage_pips=0.0)
LONDON = fr.FIXES[2]
TOKYO = fr.FIXES[0]
ECB = fr.FIXES[1]


def m1(day: str, base: float = 150.0, overrides: dict | None = None,
       drop: list | None = None) -> pd.DataFrame:
    """UTCで指定日の00:00から24時間分の1分足。overrides={"HH:MM": close}。"""
    idx = pd.date_range(f"{day} 00:00", periods=1440, freq="1min", tz="UTC")
    c = np.full(len(idx), base)
    for hm, v in (overrides or {}).items():
        c[idx.get_loc(pd.Timestamp(f"{day} {hm}", tz="UTC"))] = v
    df = pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 0}, index=idx)
    if drop:
        df = df.drop([pd.Timestamp(f"{day} {hm}", tz="UTC") for hm in drop])
    return df


def test_direction() -> None:
    print("\n[ドル売りの方向]")
    check("USDJPYは売り", fr.usd_short_side("USDJPY") == "short")
    check("EURUSDは買い", fr.usd_short_side("EURUSD") == "long")
    try:
        fr.usd_short_side("EURJPY")
        check("USDを含まないペアは拒否", False)
    except ValueError:
        check("USDを含まないペアは拒否", True)


def test_london_dst() -> None:
    print("\n[ロンドン16時: 夏時間でUTCがずれる]")
    # 夏(BST): 16:05 London = 15:05 UTC → エントリーは 15:04開始の足の終値
    s = m1("2024-07-15", overrides={"15:04": 151.0, "15:05": 999.0, "17:04": 150.5})
    tr = fr.run_fix(s, LONDON, "USDJPY", NOCOST_JPY).trades
    check("夏: 1件成立", len(tr) == 1)
    check("夏: エントリーは15:04UTC開始の足の終値", tr[0].ts_in == pd.Timestamp("2024-07-15 15:04", tz="UTC")
          and tr[0].entry == 151.0, f"{tr[0].ts_in} {tr[0].entry}")
    check("夏: 次の足(15:05)の値は使わない（先読みなし）", tr[0].entry != 999.0)
    check("夏: 決済は120分後(17:04UTC開始の足)", tr[0].ts_out == pd.Timestamp("2024-07-15 17:04", tz="UTC")
          and tr[0].exit == 150.5)
    check("夏: 売りで値下がり → プラス", tr[0].ret_bps > 0,
          f"{tr[0].ret_bps:.2f}bps")
    # 冬(GMT): 16:05 London = 16:05 UTC
    w = m1("2024-01-15", overrides={"16:04": 149.0})
    tr = fr.run_fix(w, LONDON, "USDJPY", NOCOST_JPY).trades
    check("冬: エントリーは16:04UTC開始の足", tr[0].ts_in == pd.Timestamp("2024-01-15 16:04", tz="UTC")
          and tr[0].entry == 149.0, f"{tr[0].ts_in}")


def test_tokyo_and_ecb() -> None:
    print("\n[東京仲値・ECBの時刻]")
    d = m1("2024-07-16", overrides={"00:59": 152.0})
    tr = fr.run_fix(d, TOKYO, "USDJPY", NOCOST_JPY).trades
    check("東京: 9:55JST+5分 = 01:00UTC → 00:59開始の足", len(tr) == 1
          and tr[0].ts_in == pd.Timestamp("2024-07-16 00:59", tz="UTC") and tr[0].entry == 152.0)
    tr = fr.run_fix(d, ECB, "USDJPY", NOCOST_JPY).trades
    check("ECB(夏): 14:15CEST+5分 = 12:20UTC → 12:19開始の足",
          tr[0].ts_in == pd.Timestamp("2024-07-16 12:19", tz="UTC"), f"{tr[0].ts_in}")
    w = m1("2024-01-16")
    tr = fr.run_fix(w, ECB, "USDJPY", NOCOST_JPY).trades
    check("ECB(冬): 14:15CET+5分 = 13:20UTC → 13:19開始の足",
          tr[0].ts_in == pd.Timestamp("2024-01-16 13:19", tz="UTC"), f"{tr[0].ts_in}")


def test_eurusd_long() -> None:
    print("\n[EURUSDはドル売り=買い]")
    s = m1("2024-07-15", base=1.10, overrides={"15:04": 1.1000, "17:04": 1.1011})
    tr = fr.run_fix(s, LONDON, "EURUSD", NOCOST_EUR).trades
    check("買いで値上がり → +10bps", tr[0].side == "long" and abs(tr[0].ret_bps - 10.0) < 1e-6,
          f"{tr[0].ret_bps:.4f}")


def test_missing_and_tolerance() -> None:
    print("\n[欠損の扱い]")
    # エントリー直前の数分が欠けていても、5分以内に確定した足があれば使う
    s = m1("2024-07-15", overrides={"15:01": 151.0}, drop=["15:02", "15:03", "15:04"])
    tr = fr.run_fix(s, LONDON, "USDJPY", NOCOST_JPY).trades
    check("5分以内の直前の足で代用", len(tr) == 1 and tr[0].entry == 151.0)
    # 5分以上欠けていたら、その日は見送る
    gap = [f"15:{m:02d}" for m in range(0, 5)] + [f"14:{m:02d}" for m in range(55, 60)]
    s = m1("2024-07-15", drop=gap)
    res = fr.run_fix(s, LONDON, "USDJPY", NOCOST_JPY)
    # UTCの1日分でも、ロンドン現地では翌日の0時台が混ざるので対象日は2日になる
    check("5分以上の欠損は見送り", len(res.trades) == 0
          and res.days_missing == res.days_total, f"対象{res.days_total}日/見送り{res.days_missing}日")
    sat = m1("2024-07-13")
    res = fr.run_fix(sat, LONDON, "USDJPY", NOCOST_JPY)
    check("週末は対象外", res.days_total == 0 and len(res.trades) == 0)


def test_diagnostics() -> None:
    print("\n[参考指標の符号]")
    # 夏: ロンドン16:00 = 15:00UTC。事前120分(13:00UTC)に150.0、フィキシング時151.5 → ドル高
    s = m1("2024-07-15", overrides={"12:59": 150.0, "14:59": 151.5, "15:04": 151.0})
    res = fr.run_fix(s, LONDON, "USDJPY", NOCOST_JPY)
    check("事前のドル高はプラスで記録", res.pre_usd_bps[0] > 0, f"{res.pre_usd_bps[0]:.1f}")
    check("フィキシング後5分のドル安はマイナスで記録", res.skipped_usd_bps[0] < 0,
          f"{res.skipped_usd_bps[0]:.1f}")


def main() -> int:
    test_direction()
    test_london_dst()
    test_tokyo_and_ecb()
    test_eurusd_long()
    test_missing_and_tolerance()
    test_diagnostics()
    print(f"\n結果: {len(PASS)} OK / {len(FAIL)} NG")
    if FAIL:
        print("NG: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
