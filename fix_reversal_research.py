#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 FXフィキシング後のドル安反転の検証エンジン
================================================================================

【検証する仮説】

台帳の検証待ち「ロンドン・NYオーバーラップ逆張り」を、構造的な裏付けのある
形に具体化したもの。オーバーラップの終わりにはロンドン16時フィキシングがある。

  Krohn, Mueller & Whelan, "Foreign Exchange Fixings and Returns around the
  Clock", Journal of Finance (2024)
    - 東京9:55・フランクフルト14:15(ECB)・ロンドン16:00の各フィキシングに
      向けてドルが買われ、フィキシング直後からドルが売り戻される
    - 大きさはそれぞれ約2bps。フィキシング後のドリフトは数時間続く
    - 1999〜2019年の20年間、毎年・毎曜日・毎月に存在する
    - 説明: フィキシングで執行したい実需のドル買い（時刻が決まっていて
      値段を選べない）をディーラーが仲介し、その在庫リスクのヘッジで
      事前にドルが買われ、事後に戻る

構造的な説明（誰が損をして、誰が得をするか）がある点で、台帳のテクニカル系の
候補とは性格が違う。損をするのはフィキシング執行を強制される実需側で、
得をするのは在庫リスクを引き受ける流動性の供給側（＝この戦略の側）。

【★事前に置いておく懸念★】

  - 1回あたり約2bps。Home/Away効果（0.5〜1bps）より大きいが、同じ桁の
    小ささでコストに負ける可能性がある。USDJPYの往復コスト約0.4bps、
    EURUSDは約0.55bps（スプレッド0.5+滑り0.1pips）
  - 論文の標本は2019年まで。公表（SSRN 2020年、JF 2024年）の後に
    薄れている可能性がある。2020年以降の年別推移を必ず見る
  - 論文の数字は9通貨のポートフォリオ。USDJPY・EURUSD単体での大きさは未確認
  - 東京の仲値は、日本の祝日には公示されない。ECB・ロンドンもそれぞれの休日がある。
    休日の判定は入れていない（入れない方が保守的：効果を薄める方向にしか働かない）

【売買ルール（すべて固定。CLIからは変えられない）】

  対象      : 3つのフィキシング（各市場の現地時間。夏時間は fx_data で正しく扱う）
                東京  09:55 Asia/Tokyo
                ECB   14:15 中央ヨーロッパ時間 = 13:15 Europe/London（両者は常に1時間差）
                ロンドン 16:00 Europe/London
  方向      : 無条件にドル売り（論文の主結果）。USDJPYは売り、EURUSDは買い
  エントリー: フィキシング時刻 + ENTRY_DELAY=5分 の時点で確定している1分足の終値。
              ロンドン16時のフィキシング計算窓（15:57:30〜16:02:30）が終わってから入る。
              ORBの教訓どおり「実際に取れる価格」で、かつ最も荒れる瞬間は避ける
  決済      : エントリーから HOLD=120分後の時点で確定している1分足の終値。
              損切り・利確は置かない（パラメータを増やさない）
  見送り    : その時刻から5分以内に1分足が無い日（週末・欠損）は取引しない

  3つのフィキシングは別々に集計する。スクリプト内の n_trials は3。

【参考として測るだけで、売買判定には使わないもの】

  - フィキシング前120分のドルの動き（仮説の前半「事前にドルが買われる」が
    このデータでも見えるか）
  - フィキシング時刻からエントリーまでの5分間に動いた分（取り逃している初動）

================================================================================
 使い方
================================================================================
    python fix_reversal_research.py --pair USDJPY --stress
    python fix_reversal_research.py --pair EURUSD --stress
================================================================================
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

import fx_data as fx
from cascade_research import Trade, compute_stats
from home_away_research import CostModel, pip_size, t_test_mean_zero
from orb_research import _split_is_oos

# =============================================================================
# 固定パラメータ（事前登録。変えたら台帳上の新しい試行）
# =============================================================================

ENTRY_DELAY = pd.Timedelta(minutes=5)
HOLD = pd.Timedelta(minutes=120)
PRE_WINDOW = pd.Timedelta(minutes=120)
TOLERANCE = pd.Timedelta(minutes=5)


@dataclass
class FixSpec:
    name: str
    market: str       # fx_data.MARKET_TZ のキー
    fix_hm: str       # その市場の現地時間
    rationale: str


FIXES: List[FixSpec] = [
    FixSpec("東京仲値", "tokyo", "09:55",
            "日本の銀行が対顧客レートを決める。輸入企業などの実需ドル買いが集中"),
    FixSpec("ECB", "london", "13:15",
            "ECB参照レート(フランクフルト14:15)。ロンドン時間では常に13:15"),
    FixSpec("ロンドン16時", "london", "16:00",
            "WM/Reuters。運用会社のリバランス・ヘッジの執行が集中する最大のフィキシング"),
]


def usd_short_side(pair: str) -> str:
    """ドル売りになる売買方向。USDが基軸通貨なら売り、決済通貨なら買い。"""
    p = pair.upper().replace("/", "")
    if p.startswith("USD"):
        return "short"
    if p.endswith("USD"):
        return "long"
    raise ValueError(f"USDを含まない通貨ペアは対象外です: {pair}")


# =============================================================================
# バックテスト本体
# =============================================================================

def _close_asof(bar_close_ns: np.ndarray, close: np.ndarray,
                targets: pd.DatetimeIndex) -> Tuple[np.ndarray, np.ndarray]:
    """各目標時刻の時点で確定している最後の1分足の終値。

    1分足（始点t）の終値が確定するのは t+1分。目標時刻 T に対して
    t+1分 <= T を満たす最後の足を使う。その足が T から TOLERANCE より
    古ければ、その日は欠損とみなす（NaN）。
    戻り値: (価格, その足の始点のUTC ns。欠損なら-1)
    """
    ct = bar_close_ns
    tg = targets.as_unit("ns").asi8
    pos = np.searchsorted(ct, tg, side="right") - 1
    ok = pos >= 0
    p = np.where(ok, pos, 0)
    ok &= (tg - ct[p]) < TOLERANCE.value
    px = np.where(ok, close[p], np.nan)
    start_ns = np.where(ok, ct[p] - pd.Timedelta(minutes=1).value, -1)
    return px, start_ns


@dataclass
class FixResult:
    spec: FixSpec
    trades: List[Trade]
    days_total: int = 0
    days_missing: int = 0
    pre_usd_bps: List[float] = field(default_factory=list)     # 参考: 事前のドルの動き
    skipped_usd_bps: List[float] = field(default_factory=list)  # 参考: 取り逃した初動


def run_fix(df_utc: pd.DataFrame, spec: FixSpec, pair: str,
            cost: CostModel) -> FixResult:
    side = usd_short_side(pair)
    sign_usd = 1.0 if side == "short" else -1.0   # 価格の変化率をドルの強さに直す符号

    local = fx.to_market_local(df_utc, spec.market)
    days = local.index.normalize().unique()
    days = days[days.dayofweek < 5]
    h, m = (int(x) for x in spec.fix_hm.split(":"))
    # 現地の0時に時刻を足す。夏時間の切り替えは日曜未明なので平日には影響しない
    fix_u = (days + pd.Timedelta(hours=h, minutes=m)).tz_convert("UTC")

    close = df_utc["close"].to_numpy(dtype=float)
    bar_close_ns = (df_utc.index + pd.Timedelta(minutes=1)).as_unit("ns").asi8
    px_pre, _ = _close_asof(bar_close_ns, close, fix_u - PRE_WINDOW)
    px_fix, _ = _close_asof(bar_close_ns, close, fix_u)
    px_in, ns_in = _close_asof(bar_close_ns, close, fix_u + ENTRY_DELAY)
    px_out, ns_out = _close_asof(bar_close_ns, close, fix_u + ENTRY_DELAY + HOLD)

    res = FixResult(spec, [], days_total=len(days))
    for i in range(len(days)):
        if not (np.isfinite(px_in[i]) and np.isfinite(px_out[i])) or ns_out[i] <= ns_in[i]:
            res.days_missing += 1
            continue
        entry, exit_ = float(px_in[i]), float(px_out[i])
        gross = ((exit_ / entry - 1.0) * 1e4) if side == "long" \
            else ((entry / exit_ - 1.0) * 1e4)
        ts_in = pd.Timestamp(ns_in[i], tz="UTC")
        ts_out = pd.Timestamp(ns_out[i], tz="UTC")
        res.trades.append(Trade(ts_in=ts_in, ts_out=ts_out, side=side, entry=entry,
                                exit=exit_, reason="time",
                                ret_bps=gross - cost.cost_bps(entry),
                                bars_held=int((ns_out[i] - ns_in[i]) // 60_000_000_000)))
        if np.isfinite(px_pre[i]) and np.isfinite(px_fix[i]):
            res.pre_usd_bps.append(sign_usd * (px_fix[i] / px_pre[i] - 1.0) * 1e4)
        if np.isfinite(px_fix[i]):
            res.skipped_usd_bps.append(sign_usd * (entry / px_fix[i] - 1.0) * 1e4)
    return res


# =============================================================================
# 出力
# =============================================================================

def _verdict(dsr: float) -> str:
    return "有意" if dsr >= 0.95 else ("要追加検証" if dsr >= 0.80 else "有意でない")


def report(res: FixResult, oos_from_year: int, n_trials: int) -> None:
    s = res.spec
    print(f"\n{'-'*70}")
    print(f"  [{s.name}] {s.fix_hm} ({fx.MARKET_TZ[s.market]})  "
          f"エントリー+{int(ENTRY_DELAY.total_seconds()//60)}分 / 保有{int(HOLD.total_seconds()//60)}分")
    print(f"  {s.rationale}")
    print(f"{'-'*70}")
    print(f"    対象日数(平日): {res.days_total:,}  欠損で見送り: {res.days_missing:,}")

    pre = np.array(res.pre_usd_bps)
    if len(pre) > 1:
        tv, pv = t_test_mean_zero(pre)
        print(f"    [参考] フィキシング前120分のドルの動き: 平均{pre.mean():+.3f} bps  "
              f"t={tv:+.2f} p={pv:.4f}  （仮説どおりならプラス＝ドル高）")
    sk = np.array(res.skipped_usd_bps)
    if len(sk) > 1:
        print(f"    [参考] フィキシングから5分間のドルの動き: 平均{sk.mean():+.3f} bps"
              f"  （マイナスなら、取り逃した初動がある）")

    if not res.trades:
        print("    トレードが成立しませんでした")
        return
    r = np.array([t.ret_bps for t in res.trades])
    t_val, p_val = t_test_mean_zero(r)
    print(f"    平均(コスト後)  : {r.mean():+.3f} bps   t={t_val:+.2f}  p={p_val:.4f}")

    is_, oos = _split_is_oos(res.trades, oos_from_year)
    for label, subset, nt in (("全期間", res.trades, n_trials),
                              ("IS(検証用)", is_, 1), ("OOS(検証外)", oos, 1)):
        if not subset:
            continue
        st = compute_stats(subset, n_trials=nt)
        print(f"\n     ● {label}  ({subset[0].ts_in.date()} 〜 {subset[-1].ts_in.date()})")
        print(f"       トレード数    : {st.n:,}")
        print(f"       平均          : {st.avg_bps:+.3f} bps")
        print(f"       勝率          : {st.win_rate*100:.2f} %")
        print(f"       PF            : {st.profit_factor:.3f}")
        print(f"       トレードSharpe: {st.sharpe_trade:.4f}")
        print(f"       最大DD        : {st.max_dd_bps:.1f} bps")
        print(f"       DSR           : {st.dsr:.4f}  → {_verdict(st.dsr)}")
        if np.isfinite(st.n_required):
            short = max(0, int(st.n_required) - st.n)
            print(f"       必要トレード数: {int(st.n_required):,} (≈{st.n_required/250:.0f}年分)", end="")
            print("  → 充足" if short == 0 else f"  → あと {short:,} 件必要")
        else:
            print("       必要トレード数: 算出不能（平均がマイナス）")


def stress(res: FixResult, cost: CostModel, oos_from_year: int,
           ledger_trials: int) -> None:
    if not res.trades:
        return
    s = res.spec
    r = np.array([t.ret_bps for t in res.trades])
    print(f"\n{'='*70}\n ストレステスト: [{s.name}]\n{'='*70}")

    print("\n  ① 年別の推移（論文の標本は2019年まで。2020年以降に消えていないか）")
    ser = pd.Series(r, index=[t.ts_in.year for t in res.trades])
    by_year = ser.groupby(level=0).agg(["count", "mean"])
    for y, row in by_year.iterrows():
        tag = "  ← 論文の公表後" if y >= 2020 else ""
        print(f"     {y}: {int(row['count']):4d}件  平均{row['mean']:+7.3f} bps  "
              f"{'+' if row['mean'] > 0 else '-'}{tag}")
    print(f"     → プラスの年 {int((by_year['mean'] > 0).sum())}/{len(by_year)}")

    print("\n  ② 曜日別（論文は「毎曜日に存在」と報告）")
    names = ["月", "火", "水", "木", "金"]
    dow = np.array([t.ts_in.tz_convert(fx.MARKET_TZ[s.market]).dayofweek for t in res.trades])
    for d in range(5):
        sel = dow == d
        if sel.any():
            print(f"     {names[d]}: {int(sel.sum()):4d}件  平均{r[sel].mean():+7.3f} bps")

    print("\n  ③ コスト感応度")
    base = cost.spread_pips + cost.slippage_pips
    avg_price = float(np.mean([t.entry for t in res.trades]))
    gross = r + np.array([cost.cost_bps(t.entry) for t in res.trades])
    print(f"     {'総コスト(pips)':>16s} {'平均(bps)':>12s} {'PF':>8s} {'DSR':>8s}")
    for mult in (0.0, 0.5, 1.0, 2.0, 3.0):
        c_bps = base * mult * cost.pip / avg_price * 1e4
        net = gross - c_bps
        st = compute_stats([Trade(ts_in=t.ts_in, ts_out=t.ts_out, side=t.side,
                                  entry=t.entry, exit=t.exit, reason=t.reason,
                                  ret_bps=float(x), bars_held=t.bars_held)
                            for t, x in zip(res.trades, net)], n_trials=1)
        print(f"     {base*mult:>16.2f} {net.mean():>12.3f} {st.profit_factor:>8.3f} "
              f"{st.dsr:>8.4f}{'' if st.profit_factor > 1 else '   ← 赤字'}")

    print(f"\n  ④ 台帳の累積試行数({ledger_trials})で補正したDSR")
    is_, oos = _split_is_oos(res.trades, oos_from_year)
    for label, subset in (("全期間", res.trades), ("IS", is_), ("OOS", oos)):
        if subset:
            st = compute_stats(subset, n_trials=ledger_trials)
            print(f"     {label:8s}: DSR={st.dsr:.4f}  → {_verdict(st.dsr)}")


# =============================================================================
# CLI
# =============================================================================

def main() -> None:
    ap = argparse.ArgumentParser(description="フィキシング後のドル安反転の検証")
    ap.add_argument("--pair", default="USDJPY")
    ap.add_argument("--data-dir", default=fx.DEFAULT_DATA_DIR)
    ap.add_argument("--spread-pips", type=float, default=0.5)
    ap.add_argument("--slippage-pips", type=float, default=0.1)
    ap.add_argument("--oos-from", type=int, default=2023)
    ap.add_argument("--stress", action="store_true")
    ap.add_argument("--ledger-trials", type=int, default=13,
                    help="台帳の累積試行数。既定13 = 既存11 + 本候補のUSDJPY・EURUSD")
    a = ap.parse_args()

    print(f"[読み込み] {a.pair} …")
    df = fx.load(a.pair, a.data_dir)
    print(f"  {len(df):,}本  ({df.index[0]} 〜 {df.index[-1]})")
    v = fx.verify_timezone_convention(df, verbose=False)
    if not v["passed"]:
        print("\n★タイムゾーンの検証に失敗しました。分析を中止します。★")
        sys.exit(1)
    print(f"  タイムゾーン検証: OK（{v['detected']}）")

    cost = CostModel(pip=pip_size(a.pair), spread_pips=a.spread_pips,
                     slippage_pips=a.slippage_pips)
    side = usd_short_side(a.pair)
    print("\n" + "=" * 70)
    print(f" フィキシング後のドル安反転: {a.pair}（{'売り' if side == 'short' else '買い'}）")
    print("=" * 70)
    print(f"  コスト前提: スプレッド{a.spread_pips}pips + 滑り{a.slippage_pips}pips")
    print(f"  約定前提  : フィキシング+5分の時点の1分足終値 → 120分後の1分足終値")
    print(f"  IS/OOS分割: 〜{a.oos_from-1}年 = IS / {a.oos_from}年〜 = OOS")
    print(f"  DSR補正   : n_trials={len(FIXES)}（フィキシングの数）")

    for spec in FIXES:
        res = run_fix(df, spec, a.pair, cost)
        report(res, a.oos_from, n_trials=len(FIXES))
        if a.stress:
            stress(res, cost, a.oos_from, a.ledger_trials)
    print("\n" + "=" * 70)
    print(" 判定の目安: DSR≥0.95=有意 / 0.80〜0.95=要追加検証 / <0.80=却下")
    print(" 結果にかかわらず research_ledger.md に記録すること")
    print("=" * 70)


if __name__ == "__main__":
    main()
