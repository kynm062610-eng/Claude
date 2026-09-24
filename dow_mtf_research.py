#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 ダウ理論のマルチタイムフレーム押し目（候補T2）の検証エンジン
================================================================================

【検証する仮説】

note・YouTubeで最も多く見かける裁量手法の型:
「上位足（1時間足）で高値・安値の切り上げを確認して目線を決め、
 下位足（5分足）が押し目から上昇に転換したところで入る」。
裁量の手法をそのまま検証することはできないので、下の定義に固定した。
定義は research/technical_candidates.md の T2 と同じ。
**結果を見てから定義を変えたら、それは台帳上の新しい試行になる。**

【★事前に置いておく懸念★】

  - 学術的な先行結果は厳しい。Neely & Weller (2003) は、為替の日中テクニカル
    ルールは現実的なコストを入れ、活発な時間帯に限ると利益機会の証拠がない、
    と報告している
  - 台帳の暗号資産 #2（ブレイクアウト）と FX #8・#9（ORB）が却下済み。
    本手法の引き金も「直近高値の終値ブレイク」なので、同じ理由で負けうる
  - 構造的な説明（誰が損をして、こちらが得をするのか）は弱い。
    強いて言えば「押し目で逆張りした参加者の損切り注文」がフォロースルーの源泉

【売買ルール（すべて固定。CLIからは変えられない）】

  スイング（高値・安値）の定義
    左右 SWING_K=3 本のどれよりも高い（安い）足をスイング高値（安値）とする。
    等しい値は含めない（厳密な大小比較）。
    右側3本が確定するまで、そのスイングは存在しないものとして扱う（先読み防止）。

  上位足（1時間足）の目線
    確定済みの直近2つのスイング高値が切り上がり、かつ直近2つのスイング安値も
    切り上がっていれば上昇。両方切り下がりなら下降。それ以外は見送り。

  下位足（5分足）のエントリー（買いの場合。売りは対称）
    1. 1時間足の目線が上昇
    2. 5分足の直近2つのスイング高値が切り下がっている（＝押し目の途中）
    3. 5分足の終値が、直近の5分足スイング高値を初めて上抜けた
       （前の足の終値はその水準以下）
    4. 直近の5分足スイング安値が、その形成後一度も割られていない
    5. 利確目標（1時間足の直近スイング高値）までの距離が、
       損切りまでの距離の MIN_RR=1.0 倍以上

  約定・決済
    エントリー: シグナルが出た5分足の終値（＝その足の最後の1分足の終値）。
                ORBの却下で得た教訓どおり、足の確定後に取れる価格で評価する
    損切り    : 5分足の直近スイング安値 − STOP_BUFFER_PIPS=1pip
    利確      : 1時間足の直近スイング高値
    時間切れ  : エントリーから MAX_HOLD=24時間。週末をまたぐ場合は
                金曜最後の1分足の終値で手仕舞いになる
    建玉は1つまで。保有中のシグナルは見送る

【バックテストの誠実さのために決めていること】

  - 損切り・利確のヒットは1分足の高値・安値で判定する
  - 同じ1分足で損切りと利確の両方に触れた場合は、損切りを優先する。件数は報告する
  - 損切り水準を窓で飛び越えた場合は、その足の始値で約定したとみなす
    （水準ちょうどで約定したことにしない）
  - 利確は指値なので水準ちょうどで約定（有利な窓は取らない）
  - コストはHome/Away・ORBと同じCostModel。既定はスプレッド0.5pips+滑り0.1pips

================================================================================
 使い方
================================================================================
    python dow_mtf_research.py --pair USDJPY --stress
    python dow_mtf_research.py --pair EURUSD --stress
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

HTF = "1h"
LTF = "5min"
SWING_K = 3
MIN_RR = 1.0
STOP_BUFFER_PIPS = 1.0
MAX_HOLD = pd.Timedelta(hours=24)


def _ns(idx: pd.DatetimeIndex) -> np.ndarray:
    """時刻をナノ秒の整数にそろえる。

    pandasのバージョンやデータの作り方によって、DatetimeIndex の内部単位が
    ns だったり us だったりする。asi8 をそのまま Timedelta.value(ns) と
    足し引きすると、保有期限などが1000倍ずれて黙って壊れるため、必ずここを通す。
    """
    return idx.as_unit("ns").asi8


# =============================================================================
# スイング（フラクタル）
# =============================================================================

def find_swings(high: np.ndarray, low: np.ndarray, k: int = SWING_K
                ) -> Tuple[np.ndarray, np.ndarray]:
    """左右k本より厳密に高い（安い）足を返す。端のk本は判定できないのでFalse。"""
    n = len(high)
    is_sh = np.zeros(n, dtype=bool)
    is_sl = np.zeros(n, dtype=bool)
    if n < 2 * k + 1:
        return is_sh, is_sl
    win_h = np.lib.stride_tricks.sliding_window_view(high, 2 * k + 1)
    win_l = np.lib.stride_tricks.sliding_window_view(low, 2 * k + 1)
    ch, cl = win_h[:, k], win_l[:, k]
    others_h = np.delete(win_h, k, axis=1)
    others_l = np.delete(win_l, k, axis=1)
    is_sh[k:n - k] = ch > others_h.max(axis=1)
    is_sl[k:n - k] = cl < others_l.min(axis=1)
    return is_sh, is_sl


@dataclass
class SwingState:
    """各足の確定時点で「使える」直近2つのスイング。

    b 本目の足が確定した時点で使えるのは、i + k <= b のスイング i だけ。
    （スイング i の右側 k 本が確定するのは i + k 本目の確定時）
    """
    sh_last: np.ndarray
    sh_prev: np.ndarray
    sl_last: np.ndarray
    sl_prev: np.ndarray
    sl_last_idx: np.ndarray    # 直近スイング安値の足の位置（-1=なし）
    sh_last_idx: np.ndarray    # 直近スイング高値の足の位置（-1=なし）


def _last_two(values: np.ndarray, is_pt: np.ndarray, k: int
              ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(values)
    pts = np.nonzero(is_pt)[0]
    last = np.full(n, np.nan)
    prev = np.full(n, np.nan)
    last_idx = np.full(n, -1, dtype=np.int64)
    avail = pts + k
    ok = avail < n
    pts, avail = pts[ok], avail[ok]
    last[avail] = values[pts]
    last_idx[avail] = pts
    if len(pts) > 1:
        prev[avail[1:]] = values[pts[:-1]]
    last = pd.Series(last).ffill().to_numpy()
    prev = pd.Series(prev).ffill().to_numpy()
    li = pd.Series(np.where(last_idx >= 0, last_idx, np.nan)).ffill()
    last_idx = li.fillna(-1).to_numpy(dtype=np.int64)
    return last, prev, last_idx


def swing_state(bars: pd.DataFrame, k: int = SWING_K) -> SwingState:
    h = bars["high"].to_numpy(dtype=float)
    l = bars["low"].to_numpy(dtype=float)
    is_sh, is_sl = find_swings(h, l, k)
    sh_last, sh_prev, sh_idx = _last_two(h, is_sh, k)
    sl_last, sl_prev, sl_idx = _last_two(l, is_sl, k)
    return SwingState(sh_last, sh_prev, sl_last, sl_prev, sl_idx, sh_idx)


def htf_trend_at(htf_bars: pd.DataFrame, htf_state: SwingState,
                 htf_delta: pd.Timedelta, query_close: pd.DatetimeIndex
                 ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """下位足の各確定時刻に、確定済みの上位足から見た目線と利確目標を返す。

    上位足 b が使えるのは、その確定時刻（始点 + htf_delta）が
    問い合わせ時刻以下のときだけ。
    戻り値: (up, down, target_long, target_short)
    """
    htf_close = htf_bars.index + htf_delta
    pos = np.searchsorted(_ns(htf_close), _ns(query_close), side="right") - 1
    valid = pos >= 0
    p = np.where(valid, pos, 0)
    shl, shp = htf_state.sh_last[p], htf_state.sh_prev[p]
    sll, slp = htf_state.sl_last[p], htf_state.sl_prev[p]
    with np.errstate(invalid="ignore"):
        up = valid & (shl > shp) & (sll > slp)
        down = valid & (shl < shp) & (sll < slp)
    tgt_long = np.where(valid, shl, np.nan)
    tgt_short = np.where(valid, sll, np.nan)
    return up, down, tgt_long, tgt_short


# =============================================================================
# 1分足での決済シミュレーション
# =============================================================================

def simulate_exit(m1_ts: np.ndarray, m1_open: np.ndarray, m1_high: np.ndarray,
                  m1_low: np.ndarray, m1_close: np.ndarray, k_entry: int,
                  side: str, stop: float, target: float,
                  max_hold_ns: int) -> Tuple[int, float, str, bool]:
    """エントリーの次の1分足から、損切り・利確・時間切れを判定する。

    戻り値: (決済した1分足の位置, 決済価格, 理由, 同じ足で両方に触れたか)
    """
    deadline = m1_ts[k_entry] + max_hold_ns
    end = int(np.searchsorted(m1_ts, deadline, side="left"))  # deadline未満の足まで
    lo, hi = k_entry + 1, end
    if hi <= lo:
        return k_entry, float(m1_close[k_entry]), "time", False
    if side == "long":
        hit_s = m1_low[lo:hi] <= stop
        hit_t = m1_high[lo:hi] >= target
    else:
        hit_s = m1_high[lo:hi] >= stop
        hit_t = m1_low[lo:hi] <= target
    i_s = int(np.argmax(hit_s)) if hit_s.any() else None
    i_t = int(np.argmax(hit_t)) if hit_t.any() else None

    if i_s is not None and (i_t is None or i_s <= i_t):
        j = lo + i_s
        o = float(m1_open[j])
        # 窓で損切り水準を飛び越えたら、始値で約定（水準では約定しない）
        px = min(stop, o) if side == "long" else max(stop, o)
        return j, px, "stop", (i_t is not None and i_t == i_s)
    if i_t is not None:
        return lo + i_t, float(target), "target", False
    j = hi - 1
    return j, float(m1_close[j]), "time", False


# =============================================================================
# バックテスト本体
# =============================================================================

@dataclass
class DowResult:
    trades: List[Trade]
    signals: int = 0
    skipped_rr: int = 0
    skipped_in_position: int = 0
    skipped_swing_broken: int = 0
    ambiguous_same_bar: int = 0
    n_long: int = 0
    n_short: int = 0
    reasons: dict = field(default_factory=dict)


def run_dow_mtf(df_utc: pd.DataFrame, cost: CostModel) -> DowResult:
    """df_utc: UTCインデックスの1分足（fx_data.load の戻り値）。"""
    ltf = fx.resample_ohlc(df_utc, LTF)
    htf = fx.resample_ohlc(df_utc, HTF)
    ltf_delta = pd.Timedelta(LTF)
    htf_delta = pd.Timedelta(HTF)

    lst = swing_state(ltf)
    hst = swing_state(htf)
    ltf_close_t = ltf.index + ltf_delta
    up, down, tgt_l, tgt_s = htf_trend_at(htf, hst, htf_delta, ltf_close_t)

    m1_ts = _ns(df_utc.index)
    m1_o = df_utc["open"].to_numpy(dtype=float)
    m1_h = df_utc["high"].to_numpy(dtype=float)
    m1_l = df_utc["low"].to_numpy(dtype=float)
    m1_c = df_utc["close"].to_numpy(dtype=float)
    # 各5分足の最後の1分足の位置（＝シグナル足の終値が付いた1分足）
    k_last = np.searchsorted(m1_ts, _ns(ltf_close_t), side="left") - 1

    c = ltf["close"].to_numpy(dtype=float)
    lo5 = ltf["low"].to_numpy(dtype=float)
    hi5 = ltf["high"].to_numpy(dtype=float)
    buf = STOP_BUFFER_PIPS * cost.pip
    max_hold_ns = MAX_HOLD.value

    res = DowResult(trades=[])
    busy_until = np.iinfo(np.int64).min   # 保有中の建玉の決済時刻(ns)

    with np.errstate(invalid="ignore"):
        cross_up = np.zeros(len(c), dtype=bool)
        cross_dn = np.zeros(len(c), dtype=bool)
        cross_up[1:] = (c[1:] > lst.sh_last[1:]) & (c[:-1] <= lst.sh_last[1:])
        cross_dn[1:] = (c[1:] < lst.sl_last[1:]) & (c[:-1] >= lst.sl_last[1:])
        long_c = up & (lst.sh_last < lst.sh_prev) & cross_up
        short_c = down & (lst.sl_last > lst.sl_prev) & cross_dn

    for t in np.nonzero(long_c | short_c)[0]:
        side = "long" if long_c[t] else "short"
        res.signals += 1
        k = int(k_last[t])
        if m1_ts[k] <= busy_until:
            res.skipped_in_position += 1
            continue
        entry = float(c[t])
        if side == "long":
            i_sw = int(lst.sl_last_idx[t])
            if i_sw < 0 or lo5[i_sw + 1:t + 1].min(initial=np.inf) < lst.sl_last[t]:
                res.skipped_swing_broken += 1
                continue
            stop = float(lst.sl_last[t]) - buf
            target = float(tgt_l[t])
            risk, reward = entry - stop, target - entry
        else:
            i_sw = int(lst.sh_last_idx[t])
            if i_sw < 0 or hi5[i_sw + 1:t + 1].max(initial=-np.inf) > lst.sh_last[t]:
                res.skipped_swing_broken += 1
                continue
            stop = float(lst.sh_last[t]) + buf
            target = float(tgt_s[t])
            risk, reward = stop - entry, entry - target
        if not (np.isfinite(target) and risk > 0 and reward >= MIN_RR * risk):
            res.skipped_rr += 1
            continue

        j, exit_px, reason, amb = simulate_exit(
            m1_ts, m1_o, m1_h, m1_l, m1_c, k, side, stop, target, max_hold_ns)
        res.ambiguous_same_bar += int(amb)
        res.reasons[reason] = res.reasons.get(reason, 0) + 1
        if side == "long":
            res.n_long += 1
            gross = (exit_px / entry - 1.0) * 1e4
        else:
            res.n_short += 1
            gross = (entry / exit_px - 1.0) * 1e4
        res.trades.append(Trade(
            ts_in=df_utc.index[k], ts_out=df_utc.index[j], side=side,
            entry=entry, exit=exit_px, reason=reason,
            ret_bps=gross - cost.cost_bps(entry), bars_held=int(j - k)))
        busy_until = m1_ts[j]
    return res


# =============================================================================
# 出力
# =============================================================================

def _verdict(dsr: float) -> str:
    return "有意" if dsr >= 0.95 else ("要追加検証" if dsr >= 0.80 else "有意でない")


def report(res: DowResult, oos_from_year: int, n_trials: int) -> None:
    print(f"    シグナル        : {res.signals:,}")
    print(f"      保有中で見送り: {res.skipped_in_position:,}")
    print(f"      スイング割れ  : {res.skipped_swing_broken:,}")
    print(f"      RR不足で見送り: {res.skipped_rr:,}")
    print(f"      成立トレード  : {len(res.trades):,} "
          f"(ロング {res.n_long:,} / ショート {res.n_short:,})")
    print(f"      決済理由      : {res.reasons}")
    print(f"      同じ1分足で損切りと利確の両方に触れた件数: {res.ambiguous_same_bar:,}"
          f"（損切りとして計上）")
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
        print(f"       ペイオフ比    : {st.payoff:.3f}")
        print(f"       PF            : {st.profit_factor:.3f}")
        print(f"       トレードSharpe: {st.sharpe_trade:.4f}")
        print(f"       最大DD        : {st.max_dd_bps:.1f} bps")
        print(f"       平均保有      : {st.avg_bars:.0f} 分")
        print(f"       DSR           : {st.dsr:.4f}  → {_verdict(st.dsr)}")
        if np.isfinite(st.n_required):
            short = max(0, int(st.n_required) - st.n)
            print(f"       必要トレード数: {int(st.n_required):,}", end="")
            print("  → 充足" if short == 0 else f"  → あと {short:,} 件必要")
        else:
            print("       必要トレード数: 算出不能（平均がマイナス）")


def stress(res: DowResult, cost: CostModel, oos_from_year: int,
           ledger_trials: int) -> None:
    if not res.trades:
        return
    r = np.array([t.ret_bps for t in res.trades])
    print(f"\n{'='*70}\n ストレステスト\n{'='*70}")

    print("\n  ① ロング／ショートの損益内訳（片側だけならトレンドを拾っただけの疑い）")
    means = {}
    for sd, label in (("long", "ロング"), ("short", "ショート")):
        rr = np.array([t.ret_bps for t in res.trades if t.side == sd])
        if len(rr) < 2:
            continue
        tv, pv = t_test_mean_zero(rr)
        st = compute_stats([t for t in res.trades if t.side == sd], n_trials=1)
        means[sd] = rr.mean()
        print(f"     {label:6s}: {len(rr):,}件  平均{rr.mean():+.3f} bps  "
              f"PF={st.profit_factor:.3f}  t={tv:+.2f}  p={pv:.4f}")
    both = len(means) == 2 and all(m > 0 for m in means.values())
    print(f"     → 両方向とも黒字か: {'○' if both else '×'}")

    print("\n  ② 年別の推移（特定の年に依存していないか）")
    ser = pd.Series(r, index=[t.ts_in.year for t in res.trades])
    by_year = ser.groupby(level=0).agg(["count", "mean"])
    for y, row in by_year.iterrows():
        print(f"     {y}: {int(row['count']):5d}件  平均{row['mean']:+7.3f} bps  "
              f"{'+' if row['mean'] > 0 else '-'}")
    print(f"     → プラスの年 {int((by_year['mean'] > 0).sum())}/{len(by_year)}")

    print("\n  ③ エントリー時刻（UTC）の分布（ORBの教訓: 特定の瞬間への集中は警告）")
    hours = np.array([t.ts_in.hour for t in res.trades])
    total_pnl = r.sum()
    for h in range(24):
        sel = hours == h
        if not sel.any():
            continue
        share = r[sel].sum() / total_pnl * 100 if total_pnl > 0 else float("nan")
        print(f"     {h:02d}時: {int(sel.sum()):5d}件  平均{r[sel].mean():+7.3f} bps"
              + (f"  損益寄与{share:+6.1f}%" if np.isfinite(share) else ""))

    print("\n  ④ コスト感応度")
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

    print(f"\n  ⑤ 台帳の累積試行数({ledger_trials})で補正したDSR")
    is_, oos = _split_is_oos(res.trades, oos_from_year)
    for label, subset in (("全期間", res.trades), ("IS", is_), ("OOS", oos)):
        if subset:
            st = compute_stats(subset, n_trials=ledger_trials)
            print(f"     {label:8s}: DSR={st.dsr:.4f}  → {_verdict(st.dsr)}")


# =============================================================================
# CLI
# =============================================================================

def main() -> None:
    ap = argparse.ArgumentParser(description="ダウ理論MTF押し目(T2)の検証")
    ap.add_argument("--pair", default="USDJPY")
    ap.add_argument("--data-dir", default=fx.DEFAULT_DATA_DIR)
    ap.add_argument("--spread-pips", type=float, default=0.5)
    ap.add_argument("--slippage-pips", type=float, default=0.1)
    ap.add_argument("--oos-from", type=int, default=2023)
    ap.add_argument("--stress", action="store_true")
    ap.add_argument("--ledger-trials", type=int, default=11,
                    help="台帳の累積試行数。既定11 = 既存9 + 本候補のUSDJPY・EURUSD")
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
    print("\n" + "=" * 70)
    print(f" ダウ理論MTF押し目(T2): {a.pair}  上位{HTF} / 下位{LTF} / スイング左右{SWING_K}本")
    print("=" * 70)
    print(f"  コスト前提: スプレッド{a.spread_pips}pips + 滑り{a.slippage_pips}pips")
    print(f"  約定前提  : シグナル5分足の終値 / 損切り・利確は1分足で判定")
    print(f"  IS/OOS分割: 〜{a.oos_from-1}年 = IS / {a.oos_from}年〜 = OOS")

    res = run_dow_mtf(df, cost)
    report(res, a.oos_from, n_trials=1)
    if a.stress:
        stress(res, cost, a.oos_from, a.ledger_trials)
    print("\n" + "=" * 70)
    print(" 判定の目安: DSR≥0.95=有意 / 0.80〜0.95=要追加検証 / <0.80=却下")
    print(" 結果にかかわらず research_ledger.md に記録すること")
    print("=" * 70)


if __name__ == "__main__":
    main()
