#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fx_data.py の検証（ネットワーク不要・完全オフライン）。

最重要の確認事項:
  HistData.comのタイムスタンプは「固定EST(夏時間なし)」である。
  これを US/Eastern(夏時間あり) として扱う実装ミスは、エラーを出さずに
  1年の約半分で1時間ずれるため、テストで機械的に検出できる形にしておく。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd

import fx_data as fx

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  [{'OK' if cond else 'NG'}] {name}" + (f"  {detail}" if detail else ""))


def _naive_df(timestamps, price=150.0) -> pd.DataFrame:
    ts = pd.to_datetime(pd.Series(list(timestamps)))
    return pd.DataFrame({
        "ts": ts,
        "open": price, "high": price + 0.01, "low": price - 0.01,
        "close": price, "volume": 0,
    })


def main() -> int:
    print("=" * 66)
    print(" fx_data.py 検証（オフライン）")
    print("=" * 66)

    # ------------------------------------------------------------------
    print("\n[1] ファイル時計→UTC変換が、NY現地時間として行われるか（最重要）")
    # ★実データで判明したこと★
    #   HistDataの仕様書は「EST・夏時間なし」と書いているが、実際のファイルは
    #   NY現地時間（夏時間あり）で記録されている。USD/JPY 605週分の実測で、
    #   週末クローズが夏も冬も16:59（ズレ0分）だったことから確定した。
    #   したがって naive 12:00 は、冬=EST(UTC-5)→17:00 UTC、
    #   夏=EDT(UTC-4)→16:00 UTC になるのが正解。
    df = fx.to_utc_index(_naive_df(["2024-01-15 12:00:00", "2024-07-15 12:00:00"]))
    hours = list(df.index.hour)
    check("冬のバーが UTC 17時になる（EST=UTC-5）", hours[0] == 17, f"実際={hours[0]}時")
    check("夏のバーが UTC 16時になる（EDT=UTC-4）", hours[1] == 16, f"実際={hours[1]}時")
    check("インデックスがUTCのtz-aware", str(df.index.tz) == "UTC")

    # 対照: 仕様書どおりの固定+5時間で変換していたら、夏が1時間ずれる
    wrong = pd.to_datetime(["2024-01-15 12:00:00", "2024-07-15 12:00:00"]) \
        + pd.Timedelta(hours=5)
    check("（対照）仕様書どおりの固定オフセットだと夏が1時間ずれる",
          list(wrong.hour) == [17, 17],
          f"固定オフセット版={list(wrong.hour)} ← 夏が本来より1時間後ろにずれる")

    # ------------------------------------------------------------------
    print("\n[2] オフセットが夏冬で正しく切り替わるか（年間通してのスポットチェック）")
    stamps = [f"2024-{m:02d}-15 12:00:00" for m in range(1, 13)]
    d2 = fx.to_utc_index(_naive_df(stamps))
    naive_back = d2.index.tz_convert("UTC").tz_localize(None)
    deltas = sorted(set(naive_back - pd.to_datetime(stamps)))
    check("オフセットが2種類（冬+5時間 / 夏+4時間）検出される",
          deltas == [pd.Timedelta(hours=4), pd.Timedelta(hours=5)],
          f"検出={[str(d) for d in deltas]}")
    # 2024年の米国夏時間は 3/10〜11/3。3月と7月で切り替わっていること
    off = pd.Series((naive_back - pd.to_datetime(stamps)).values,
                    index=[int(s[5:7]) for s in stamps])
    check("1月は+5時間（標準時）", off.loc[1] == pd.Timedelta(hours=5))
    check("7月は+4時間（夏時間）", off.loc[7] == pd.Timedelta(hours=4))
    check("12月は+5時間（標準時に戻る）", off.loc[12] == pd.Timedelta(hours=5))

    # ------------------------------------------------------------------
    print("\n[3] CSVパース（HistDataのセミコロン区切り形式）")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "USDJPY_2024.csv"
        p.write_text(
            "20240115 000000;148.123;148.200;148.100;148.150;0\n"
            "20240115 000100;148.150;148.180;148.140;148.170;0\n"
            "こわれた行\n",
            encoding="utf-8")
        parsed = fx._parse_csv(p)
    check("正常な2行だけが読める（壊れた行は除外）", len(parsed) == 2, f"{len(parsed)}行")
    check("価格が数値になっている",
          abs(float(parsed["close"].iloc[0]) - 148.150) < 1e-9)

    # ------------------------------------------------------------------
    print("\n[4] 市場ごとの現地時間変換が、各市場の夏時間を正しく扱うか")
    # 2024-07-15 12:00 UTC の各市場現地時間
    #   東京   : UTC+9 固定           → 21:00
    #   ロンドン: 夏はBST(UTC+1)      → 13:00
    #   NY     : 夏はEDT(UTC-4)       → 08:00
    base = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]},
                        index=pd.DatetimeIndex(["2024-07-15 12:00:00"], tz="UTC"))
    check("東京(夏)=21時", fx.to_market_local(base, "tokyo").index[0].hour == 21)
    check("ロンドン(夏, BST)=13時", fx.to_market_local(base, "london").index[0].hour == 13)
    check("NY(夏, EDT)=8時", fx.to_market_local(base, "newyork").index[0].hour == 8)

    base_w = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]},
                          index=pd.DatetimeIndex(["2024-01-15 12:00:00"], tz="UTC"))
    check("東京(冬)=21時（夏時間なしなので不変）",
          fx.to_market_local(base_w, "tokyo").index[0].hour == 21)
    check("ロンドン(冬, GMT)=12時", fx.to_market_local(base_w, "london").index[0].hour == 12)
    check("NY(冬, EST)=7時", fx.to_market_local(base_w, "newyork").index[0].hour == 7)

    # ------------------------------------------------------------------
    print("\n[5] 判定が「NY現地時間のデータ」を正しく通すか（＝実データの姿）")
    # 実ファイルはNY現地時間で記録されている。つまり生ファイル上のクローズは
    # 夏も冬も17:00で一定。これを正しく変換したUTC列を作って検証する。
    fridays = pd.date_range("2024-01-05", "2024-12-27", freq="W-FRI")
    rows = []
    for d in fridays:
        # ファイル上17:00 → NY現地17:00として解釈 → UTCへ
        rows.append(pd.Timestamp(f"{d.date()} 17:00:00",
                                 tz="America/New_York").tz_convert("UTC"))
    good = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0},
                        index=pd.DatetimeIndex(rows, tz="UTC"))
    r_good = fx.verify_timezone_convention(good, verbose=False)
    check("NY現地時間のデータで passed=True", r_good["passed"] is True,
          f"検出={r_good['detected']}")
    check("夏冬のズレが0分と検出される", r_good["shift_minutes"] == 0,
          f"ズレ={r_good['shift_minutes']}分")
    check("検査した金曜の数が週数ぶんある（サンプル不足でない）",
          r_good["fridays_checked"] == len(fridays),
          f"{r_good['fridays_checked']}/{len(fridays)}")
    check("年別の内訳が出る", 2024 in r_good["by_year"])

    # ------------------------------------------------------------------
    print("\n[6] 判定が「固定オフセットのデータ」を弾くか（回帰の要）")
    # もし配信元が仕様書どおりの固定オフセットに変えた場合、生ファイル上の
    # クローズは夏16:00 / 冬17:00 と1時間ずれる。現在の実装のままでは
    # 夏が1時間ずれるので、検出して止める必要がある。
    bad_rows = []
    for d in fridays:
        # 生ファイル上で「夏16:00 / 冬17:00」になるデータを作る
        is_dst = bool(pd.Timestamp(f"{d.date()}").tz_localize(
            "America/New_York").dst().total_seconds())
        hh = 16 if is_dst else 17
        bad_rows.append(pd.Timestamp(f"{d.date()} {hh}:00:00",
                                     tz="America/New_York").tz_convert("UTC"))
    bad = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0},
                       index=pd.DatetimeIndex(bad_rows, tz="UTC"))
    r_bad = fx.verify_timezone_convention(bad, verbose=False)
    check("固定オフセットのデータを passed=False として検出できる",
          r_bad["passed"] is False, f"検出={r_bad['detected']}")
    check("ズレが60分として検出される", r_bad["shift_minutes"] == 60,
          f"ズレ={r_bad['shift_minutes']}分")

    # ------------------------------------------------------------------
    print("\n[6b] 日曜開場のバーがあっても判定が壊れないか（旧実装の欠陥の回帰）")
    # ★旧実装の欠陥★ 月曜始まりの週で「最終バー」を取ると、FX市場は
    # 日曜夜に開くため日曜のバーが拾われ、金曜終わりの週＝日曜データが
    # 欠けた異常な週しか検査されなかった（11年分から9週しか見ていなかった）。
    # 金曜のバーを直接見る現実装なら、日曜のバーが混ざっても影響を受けない。
    sundays = pd.date_range("2024-01-07", "2024-12-29", freq="W-SUN")
    sun_rows = [pd.Timestamp(f"{d.date()} 17:05:00",
                             tz="America/New_York").tz_convert("UTC")
                for d in sundays]
    mixed = pd.DataFrame(
        {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0},
        index=pd.DatetimeIndex(list(rows) + sun_rows, tz="UTC").sort_values())
    r_mixed = fx.verify_timezone_convention(mixed, verbose=False)
    check("日曜バーを混ぜても金曜の検査数が減らない",
          r_mixed["fridays_checked"] == len(fridays),
          f"{r_mixed['fridays_checked']}/{len(fridays)}")
    check("日曜バーを混ぜても判定結果が変わらない", r_mixed["passed"] is True,
          f"検出={r_mixed['detected']}")

    # ------------------------------------------------------------------
    print("\n[7] リサンプル（M1→上位足）")
    idx = pd.date_range("2024-01-15 00:00", periods=15, freq="1min", tz="UTC")
    m1 = pd.DataFrame({
        "open": range(15), "high": [x + 1 for x in range(15)],
        "low": [x - 1 for x in range(15)], "close": range(15), "volume": 0,
    }, index=idx).astype(float)
    m5 = fx.resample_ohlc(m1, "5min")
    check("5分足が3本になる", len(m5) == 3, f"{len(m5)}本")
    check("始値は区間の最初", float(m5["open"].iloc[0]) == 0.0)
    check("終値は区間の最後", float(m5["close"].iloc[0]) == 4.0)
    check("高値は区間の最大", float(m5["high"].iloc[0]) == 5.0)
    check("安値は区間の最小", float(m5["low"].iloc[0]) == -1.0)

    # ------------------------------------------------------------------
    print("\n[8] 空データでも落ちないか")
    empty = fx.to_utc_index(pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"]))
    check("空DataFrameを渡しても例外にならない", len(empty) == 0)

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
