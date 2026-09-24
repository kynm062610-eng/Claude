#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 ORB（オープニング・レンジ・ブレイクアウト）の検証エンジン
================================================================================

【検証する仮説】

ロンドン・NYの各セッション開始直後は、機関投資家の注文フローが一気に
市場へ流入する。開始からしばらくの高値・安値（オープニングレンジ）は
その日の初期の合意価格帯を表しており、そこを抜けた方向には
フォロースルーが出やすい、という仮説。

  提唱: トビー・クベル『Day Trading with Short Term Price Patterns
        and Opening Range Breakout』(1990)
  他に: 指数先物を対象にした査読論文(IEEE Access, 2019)が存在する

【★事前に置いておく懸念★】

クベルの本は1990年出版で、公表から30年以上たっている。
このプロジェクトでは直前に、AEA論文(2009)が報告したHome/Away効果が
発表後の期間(2015-2026)では再現しないことを確認したばかりである。
「公表されたアノマリーは裁定されて薄くなる」という現象を目撃した直後なので、
ORBにも同じことが起きている可能性は高いと見ておくべきである。

【Home/Away効果の失敗から設計に反映したこと】

Home/Away効果は1回あたりの粗利が0.5〜1 bpsしかなく、コストに埋もれた上、
有意性の確認に約200年分のデータが必要という結果になった。
値幅そのものが小さすぎたことが根本的な問題だった。

ORBは「ボラティリティが出た瞬間だけ」を狙うため、1回あたりの値幅が
構造的に大きくなる。したがってコスト比率と必要トレード数の両方が
現実的な水準に落ちることが期待できる。ここが今回の検証の要点。

【売買ルール（パラメータを増やさない設計）】

  1. セッション開始から range_minutes 分間の高値H・安値Lをレンジとする
  2. レンジ確定後、セッション終了までを監視する
  3. 最初に H を上抜けたらロング、L を下抜けたらショート（1日1回だけ）
  4. 損切り: レンジの反対側（ロングならL、ショートならH）
  5. 利確: 置かない。セッション終了で時間決済する

  利確目標を置かないのは、パラメータを増やすと多重検定の補正が重くなり、
  「どれかが当たるまで振る」ことになりかねないため。
  まず素の形で検証し、箸にも棒にもかからなければ調整しても無駄と判断する。

【バックテストの誠実さのために決めていること】

  - 約定はブレイクした水準ちょうどとし、有利な滑りは一切想定しない
  - 同じ1分足の中で上下ともブレイクした場合、どちらが先か判別できないため
    そのセッションは**捨てる**（都合よく解釈しない）。件数は報告する
  - 建玉保有中、同じ足で損切り水準と決済時刻の両方に触れた場合は
    損切りを優先する（暗号資産の検証と同じ約束事）
  - ブレイクアウトは板が薄い瞬間に飛び込むため、スリッページの既定値を
    Home/Away検証(0.1pips)より厳しい 0.3pips にしている

================================================================================
 使い方
================================================================================
    python orb_research.py --pair USDJPY
    python orb_research.py --pair EURUSD --range-min 30
    python orb_research.py --pair USDJPY --spread-pips 0.3 --slippage-pips 0.2
================================================================================
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import fx_data as fx
from cascade_research import Trade, compute_stats
from home_away_research import CostModel, pip_size, t_test_mean_zero

# =============================================================================
# セッション定義
# =============================================================================

@dataclass
class ORBSpec:
    """ORBの対象セッション。時刻は必ずその市場の現地時間で指定する。

    現地時間で切る理由は fx_data.py 冒頭のとおり。データ上の固定時刻で
    区切ると、ロンドンとNYは夏冬で1時間ずれた集計になる。
    """
    name: str
    market: str
    open_hm: str        # セッション開始（レンジの起点）
    close_hm: str       # セッション終了（時間決済の時刻）
    rationale: str


DEFAULT_SPECS: List[ORBSpec] = [
    ORBSpec("ロンドン", "london", "08:00", "16:00",
            "FXで最も出来高が増える時間帯。欧州勢のフローが一気に入る"),
    ORBSpec("NY", "newyork", "08:00", "17:00",
            "米国勢の参入時間。8:30 ETの重要指標がレンジ確定直後に来る"),
]


@dataclass
class ORBResult:
    """1セッション分の結果と、その内訳。"""
    spec: ORBSpec
    trades: List[Trade]
    sessions_total: int
    sessions_no_break: int
    sessions_ambiguous: int
    n_long: int
    n_short: int
    # 除外した「上下同時ブレイク」セッションのレンジ幅(bps)。
    # 除外が結果を良く見せていないかを検証するために保持する。
    ambiguous_range_bps: List[float] = field(default_factory=list)
    # 各トレードの「レンジ確定から何分後に約定したか」。
    # エッジが指標発表の瞬間に集中していないかを見るために保持する。
    entry_delay_min: List[int] = field(default_factory=list)
    # min_delay_min によって見送ったセッション数
    sessions_skipped_delay: int = 0


# =============================================================================
# バックテスト本体
# =============================================================================

def _to_minutes(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


def run_orb(df_utc: pd.DataFrame, spec: ORBSpec, cost: CostModel,
            range_minutes: int = 30, min_bars: int = 60,
            entry_mode: str = "level", min_delay_min: int = 0) -> ORBResult:
    """1セッション分のORBを通しで検証する。

    df_utc: UTCインデックスのM1

    entry_mode: 約定価格の前提。ここが結論を左右する。
      "level" — ブレイクした水準ちょうどで約定したと仮定する。
                ティックを常時監視し、指値が即座に約定する環境が前提。
      "close" — ブレイクした1分足の**終値**で約定したと仮定する。
                ★実際にボットを作った場合はこちらが現実★
                1分足をポーリングして判断する以上、足が確定してからしか
                発注できない。発表直後の大きな足では、終値はブレイク水準から
                大きく離れており、その差がそのまま不利になる。

    min_delay_min: レンジ確定からこの分数以内のブレイクは見送る。
      指標発表の瞬間（スプレッドが最も開く瞬間）を避けた場合に
      何が残るかを見るための設定。
    """
    if entry_mode not in ("level", "close"):
        raise ValueError(f"entry_mode は level か close: {entry_mode}")
    local = fx.to_market_local(df_utc, spec.market)
    hhmm = local.index.hour * 60 + local.index.minute
    o_min, c_min = _to_minutes(spec.open_hm), _to_minutes(spec.close_hm)
    r_end = o_min + range_minutes

    in_session = (hhmm >= o_min) & (hhmm < c_min)
    sub = local[in_session]
    if sub.empty:
        return ORBResult(spec, [], 0, 0, 0, 0, 0)
    sub_min = hhmm[in_session]

    trades: List[Trade] = []
    total = no_break = ambiguous = n_long = n_short = 0
    skipped_delay = 0
    amb_range: List[float] = []
    delays: List[int] = []

    day_key = sub.index.normalize()
    for _, idx in sub.groupby(day_key).indices.items():
        g = sub.iloc[idx]
        gm = sub_min[idx]
        if len(g) < min_bars:
            continue
        total += 1

        in_range = gm < r_end
        if not in_range.any() or in_range.all():
            no_break += 1
            continue

        rng = g[in_range]
        H = float(rng["high"].max())
        L = float(rng["low"].min())
        if not (np.isfinite(H) and np.isfinite(L)) or H <= L:
            no_break += 1
            continue

        after = g[~in_range]
        highs = after["high"].to_numpy(dtype=float)
        lows = after["low"].to_numpy(dtype=float)

        up = highs >= H
        dn = lows <= L
        i_up = int(np.argmax(up)) if up.any() else None
        i_dn = int(np.argmax(dn)) if dn.any() else None

        if i_up is None and i_dn is None:
            no_break += 1
            continue

        # 同じ足で上下ともブレイク＝先後が判別できないので、そのセッションは捨てる。
        # ただし「捨てたことで結果が良くなっていないか」を後で検証できるよう、
        # そのセッションのレンジ幅（＝最悪の場合に被る損失幅）を記録しておく。
        if i_up is not None and i_dn is not None and i_up == i_dn:
            ambiguous += 1
            amb_range.append((H / L - 1.0) * 1e4)
            continue

        if i_dn is None or (i_up is not None and i_up < i_dn):
            side, level, stop, i0 = "long", H, L, i_up
        else:
            side, level, stop, i0 = "short", L, H, i_dn

        delay = int(gm[~in_range][i0] - r_end)
        if delay < min_delay_min:
            skipped_delay += 1
            continue

        # ★約定価格の前提★
        #   level: ブレイク水準ちょうど（ティック監視・即時約定を前提）
        #   close: ブレイクした足の終値（1分足ポーリングの実装で現実に起きること）
        entry = level if entry_mode == "level" \
            else float(after["close"].iloc[i0])

        if side == "long":
            n_long += 1
        else:
            n_short += 1

        # --- 建玉保有中の推移 ---
        # 損切り優先。同じ足で損切りと時間決済の両方に該当したら損切りとする。
        hi_after = highs[i0 + 1:]
        lo_after = lows[i0 + 1:]
        if side == "long":
            hit = np.nonzero(lo_after <= stop)[0]
        else:
            hit = np.nonzero(hi_after >= stop)[0]

        if len(hit):
            j = int(hit[0]) + i0 + 1
            exit_px, reason = stop, "stop"
        else:
            j = len(after) - 1
            exit_px, reason = float(after["close"].iloc[-1]), "time"

        gross = ((exit_px / entry - 1.0) * 1e4) if side == "long" \
            else ((entry / exit_px - 1.0) * 1e4)
        net = gross - cost.cost_bps(entry)

        trades.append(Trade(
            ts_in=after.index[i0].tz_convert("UTC"),
            ts_out=after.index[j].tz_convert("UTC"),
            side=side, entry=entry, exit=exit_px, reason=reason,
            ret_bps=net, bars_held=int(j - i0),
        ))
        delays.append(delay)

    return ORBResult(spec, trades, total, no_break, ambiguous, n_long, n_short,
                     amb_range, delays, skipped_delay)


# =============================================================================
# 出力
# =============================================================================

def _split_is_oos(trades: List[Trade], oos_from_year: int
                  ) -> Tuple[List[Trade], List[Trade]]:
    is_ = [t for t in trades if t.ts_in.year < oos_from_year]
    oos = [t for t in trades if t.ts_in.year >= oos_from_year]
    return is_, oos


def report(res: ORBResult, oos_from_year: int, n_trials: int,
           range_minutes: int) -> None:
    s = res.spec
    print(f"\n{'-'*70}")
    print(f"  [{s.name}] {s.open_hm}-{s.close_hm} ({fx.MARKET_TZ[s.market]})  "
          f"レンジ{range_minutes}分")
    print(f"  {s.rationale}")
    print(f"{'-'*70}")
    print(f"    対象セッション数: {res.sessions_total:,}")
    print(f"      ブレイクなし  : {res.sessions_no_break:,}")
    print(f"      上下同時(除外): {res.sessions_ambiguous:,}"
          f"  ※先後が判別できないため捨てている")
    if res.sessions_skipped_delay:
        print(f"      早すぎ(見送り): {res.sessions_skipped_delay:,}"
              f"  ※指標発表の瞬間を避ける設定による")
    print(f"      成立トレード  : {len(res.trades):,} "
          f"(ロング {res.n_long:,} / ショート {res.n_short:,})")

    if not res.trades:
        print("    トレードが成立しませんでした")
        return

    r = np.array([t.ret_bps for t in res.trades])
    t_val, p_val = t_test_mean_zero(r)
    print(f"    平均(コスト後)  : {r.mean():+.3f} bps   "
          f"t={t_val:+.2f}  p={p_val:.4f}")

    for label, subset, nt in (("全期間", res.trades, n_trials),
                              ("IS(検証用)", _split_is_oos(res.trades, oos_from_year)[0], 1),
                              ("OOS(検証外)", _split_is_oos(res.trades, oos_from_year)[1], 1)):
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
        print(f"       決済内訳      : 損切 {st.stop_rate*100:.1f}% / "
              f"時間切れ {st.time_rate*100:.1f}%")
        print(f"       平均保有      : {st.avg_bars:.0f} 分")
        print(f"       DSR           : {st.dsr:.4f}", end="")
        if st.dsr >= 0.95:
            print("  → 有意")
        elif st.dsr >= 0.80:
            print("  → 要追加検証")
        else:
            print("  → 有意でない")
        if np.isfinite(st.n_required):
            short = max(0, int(st.n_required) - st.n)
            years = st.n_required / 250.0
            print(f"       必要トレード数: {int(st.n_required):,} (≈{years:.0f}年分)", end="")
            print("  → 充足" if short == 0 else f"  → あと {short:,} 件必要")
        else:
            print("       必要トレード数: 算出不能（平均がマイナス）")


# =============================================================================
# ストレステスト ── 「通ってしまった結果」を疑うための検査
# =============================================================================

def stress(res: ORBResult, df_utc: pd.DataFrame, cost: CostModel,
           range_minutes: int, oos_from_year: int, ledger_trials: int) -> None:
    """DSRを通過した結果に対して、都合の良い作りになっていないかを検査する。

    通過した候補ほど厳しく見るべき、という考えでまとめてある。
    ここで崩れるようなら、DSRが1.0でも採用してはいけない。
    """
    s = res.spec
    if not res.trades:
        return
    r = np.array([t.ret_bps for t in res.trades])

    print(f"\n{'='*70}")
    print(f" ストレステスト: [{s.name}]")
    print(f"{'='*70}")

    # --- ① 除外した「上下同時ブレイク」を最悪ケースで戻す -------------------
    print("\n  ① 除外セッションを最悪ケースで戻した場合")
    print("     上下同時ブレイクの日を『入った直後に反対側で損切り』とみなして加算する。")
    print("     除外が結果を良く見せていないかの検査。")
    if res.sessions_ambiguous == 0:
        print("     除外セッションなし。影響なし")
    else:
        amb = np.array(res.ambiguous_range_bps)
        # 最悪ケース: レンジ幅ぶん逆行して損切り＋コスト
        avg_price = float(np.mean([t.entry for t in res.trades]))
        penalty = -(amb + cost.cost_bps(avg_price))
        merged = np.concatenate([r, penalty])
        st_m = compute_stats(
            [Trade(ts_in=res.trades[0].ts_in, ts_out=res.trades[0].ts_out,
                   side="long", entry=1.0, exit=1.0, reason="stop",
                   ret_bps=float(x), bars_held=1) for x in merged],
            n_trials=1)
        print(f"     除外していた件数  : {res.sessions_ambiguous:,} "
              f"(平均レンジ幅 {amb.mean():.1f} bps)")
        print(f"     元の平均          : {r.mean():+.3f} bps  PF={compute_stats(res.trades).profit_factor:.3f}")
        print(f"     最悪ケース込み平均: {merged.mean():+.3f} bps  PF={st_m.profit_factor:.3f}")
        print(f"     DSR               : {st_m.dsr:.4f}", end="")
        print("  → 耐えた" if st_m.dsr >= 0.95 else "  → ★崩れた★")

    # --- ② ロング／ショートの内訳 ------------------------------------------
    print("\n  ② ロング／ショートの損益内訳")
    print("     片側だけで稼いでいるなら、トレンドを拾っただけの疑いが残る。")
    for sd in ("long", "short"):
        sub = [t for t in res.trades if t.side == sd]
        if not sub:
            continue
        st = compute_stats(sub, n_trials=1)
        rr = np.array([t.ret_bps for t in sub])
        tv, pv = t_test_mean_zero(rr)
        label = "ロング" if sd == "long" else "ショート"
        print(f"     {label:6s}: {st.n:,}件  平均{st.avg_bps:+.3f} bps  "
              f"PF={st.profit_factor:.3f}  t={tv:+.2f}  p={pv:.4f}")
    lo = np.array([t.ret_bps for t in res.trades if t.side == "long"])
    sh = np.array([t.ret_bps for t in res.trades if t.side == "short"])
    both_pos = (len(lo) and lo.mean() > 0) and (len(sh) and sh.mean() > 0)
    print(f"     → 両方向とも黒字か: {'○' if both_pos else '× 片側のみ'}")

    # --- ③ 年別の推移 -------------------------------------------------------
    print("\n  ③ 年別の推移（特定の年に依存していないか）")
    ser = pd.Series(r, index=[t.ts_in.year for t in res.trades])
    by_year = ser.groupby(level=0).agg(["count", "mean"])
    for y, row in by_year.iterrows():
        bar = "+" if row["mean"] > 0 else "-"
        print(f"     {y}: {int(row['count']):4d}件  平均{row['mean']:+7.3f} bps  {bar}")
    pos = int((by_year["mean"] > 0).sum())
    print(f"     → プラスの年 {pos}/{len(by_year)}")

    # --- ④ コスト感応度 -----------------------------------------------------
    print("\n  ④ コスト感応度（指標発表時のスプレッド拡大への耐性）")
    print("     レンジ確定直後は重要指標の発表時刻にあたり、実際のスプレッドは")
    print("     平常時の数倍〜十数倍に開くことがある。どこまで耐えるかを見る。")
    base_cost = cost.spread_pips + cost.slippage_pips
    avg_price = float(np.mean([t.entry for t in res.trades]))
    gross = r + cost.cost_bps(avg_price)   # コストを戻した粗利
    print(f"     {'総コスト(pips)':>16s} {'平均(bps)':>12s} {'PF':>8s} {'DSR':>8s}")
    for mult in (1.0, 2.0, 3.0, 5.0, 10.0):
        c_pips = base_cost * mult
        c_bps = c_pips * cost.pip / avg_price * 1e4
        net = gross - c_bps
        st = compute_stats(
            [Trade(ts_in=t.ts_in, ts_out=t.ts_out, side=t.side, entry=t.entry,
                   exit=t.exit, reason=t.reason, ret_bps=float(x),
                   bars_held=t.bars_held)
             for t, x in zip(res.trades, net)], n_trials=1)
        mark = "" if st.profit_factor > 1.0 else "   ← 赤字"
        print(f"     {c_pips:>16.1f} {net.mean():>12.3f} "
              f"{st.profit_factor:>8.3f} {st.dsr:>8.4f}{mark}")

    # --- ⑤ 約定タイミングの分布 --------------------------------------------
    print("\n  ⑤ レンジ確定から約定までの時間分布")
    print("     最初の数分に集中しているなら、指標発表の初動を取る戦略ということ。")
    print("     筋は通るが、その瞬間こそ執行が最も難しいという意味でもある。")
    d = np.array(res.entry_delay_min)
    for lo_, hi_ in ((0, 1), (1, 5), (5, 15), (15, 60), (60, 10**6)):
        sel = (d >= lo_) & (d < hi_)
        if not sel.any():
            continue
        rr = r[sel]
        rng_lbl = f"{lo_}〜{hi_}分" if hi_ < 10**6 else f"{lo_}分以降"
        print(f"     {rng_lbl:>10s}: {int(sel.sum()):5d}件 "
              f"({sel.mean()*100:4.1f}%)  平均{rr.mean():+7.3f} bps")

    # --- ⑥ 台帳の累積試行数で補正 ------------------------------------------
    print(f"\n  ⑥ 台帳の累積試行数({ledger_trials})で補正したDSR")
    print("     このプロジェクト全体で何通り試したかを踏まえた、最も厳しい基準。")
    for label, subset in (("全期間", res.trades),
                          ("IS", _split_is_oos(res.trades, oos_from_year)[0]),
                          ("OOS", _split_is_oos(res.trades, oos_from_year)[1])):
        if not subset:
            continue
        st = compute_stats(subset, n_trials=ledger_trials)
        verdict = "有意" if st.dsr >= 0.95 else \
                  ("要追加検証" if st.dsr >= 0.80 else "有意でない")
        print(f"     {label:8s}: DSR={st.dsr:.4f}  → {verdict}")


# =============================================================================
# CLI
# =============================================================================

def main() -> None:
    ap = argparse.ArgumentParser(description="ORBの検証")
    ap.add_argument("--pair", default="USDJPY")
    ap.add_argument("--data-dir", default=fx.DEFAULT_DATA_DIR)
    ap.add_argument("--range-min", type=int, default=30,
                    help="オープニングレンジの長さ（分）。既定30")
    ap.add_argument("--spread-pips", type=float, default=0.5)
    ap.add_argument("--slippage-pips", type=float, default=0.3,
                    help="既定0.3。ブレイクアウトは滑りやすいため厳しめに置く")
    ap.add_argument("--oos-from", type=int, default=2023)
    ap.add_argument("--min-bars", type=int, default=60)
    ap.add_argument("--n-trials", type=int, default=None)
    ap.add_argument("--entry-mode", choices=("level", "close"), default="level",
                    help="約定価格の前提。level=ブレイク水準ちょうど / "
                         "close=ブレイクした足の終値（1分足ポーリング実装の現実）")
    ap.add_argument("--min-delay-min", type=int, default=0,
                    help="レンジ確定からこの分数以内のブレイクを見送る。"
                         "指標発表の瞬間を避けた場合に何が残るかを見る")
    ap.add_argument("--stress", action="store_true",
                    help="通過した結果を疑うための追加検査を行う")
    ap.add_argument("--ledger-trials", type=int, default=9,
                    help="台帳の累積試行数。ストレステストの最終判定に使う")
    a = ap.parse_args()

    print(f"[読み込み] {a.pair} …")
    df = fx.load(a.pair, a.data_dir)
    print(f"  {len(df):,}本  ({df.index[0]} 〜 {df.index[-1]})")

    v = fx.verify_timezone_convention(df, verbose=False)
    if not v["passed"]:
        print("\n★タイムゾーンの検証に失敗しました。分析を中止します。★")
        print(f"   検出={v['detected']} / 設定={v['configured']}")
        sys.exit(1)
    print(f"  タイムゾーン検証: OK（{v['detected']}、金曜{v['fridays_checked']:,}週分で確認）")

    specs = DEFAULT_SPECS
    n_trials = a.n_trials if a.n_trials is not None else len(specs)
    cost = CostModel(pip=pip_size(a.pair), spread_pips=a.spread_pips,
                     slippage_pips=a.slippage_pips)

    print("\n" + "=" * 70)
    print(f" ORB検証: {a.pair}  レンジ{a.range_min}分")
    print("=" * 70)
    print(f"  コスト前提: スプレッド{a.spread_pips}pips + "
          f"スリッページ{a.slippage_pips}pips（往復1回分）")
    print(f"  損切り    : レンジの反対側 / 利確: 置かずセッション終了で時間決済")
    mode_note = ("ブレイク水準ちょうど（ティック監視・即時約定が前提）"
                 if a.entry_mode == "level"
                 else "★ブレイクした足の終値（1分足ポーリング実装の現実）★")
    print(f"  約定前提  : {mode_note}")
    if a.min_delay_min:
        print(f"  見送り設定: レンジ確定から{a.min_delay_min}分以内のブレイクは取らない")
    print(f"  IS/OOS分割: 〜{a.oos_from-1}年 = IS / {a.oos_from}年〜 = OOS")
    print(f"  DSR補正   : n_trials={n_trials}（検証したセッション数）")

    for spec in specs:
        res = run_orb(df, spec, cost, range_minutes=a.range_min,
                      min_bars=a.min_bars, entry_mode=a.entry_mode,
                      min_delay_min=a.min_delay_min)
        report(res, a.oos_from, n_trials, a.range_min)
        if a.stress:
            stress(res, df, cost, a.range_min, a.oos_from, a.ledger_trials)

    print("\n" + "=" * 70)
    print(" 判定の目安: DSR≥0.95=有意 / 0.80〜0.95=要追加検証 / <0.80=却下")
    print(" ※台帳(research_ledger.md)の累積試行数は現在7。")
    print("   この結果を採用する場合、その補正込みで判断すること。")
    print("=" * 70)


if __name__ == "__main__":
    main()
