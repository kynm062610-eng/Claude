#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 Home/Away効果の検証エンジン（USD/JPY、セッション別の方向バイアス）
================================================================================

【検証する仮説】

各国の実需筋（企業・機関投資家）は、自国の営業時間中に自国通貨を売って
外貨を調達する傾向がある。この日常的な資金フローが、時間帯ごとの需給の
偏りを生む、という仮説。AEA学会論文 "Intraday Patterns in FX returns and
Order Flow" が EUR/USD で Sharpe 1.3 / 0.9 を報告している。

USD/JPY に当てはめると、こうなる。

    東京時間（円のホーム） : 円が売られる → USD/JPY は上がりやすい
    NY時間  （ドルのホーム）: ドルが売られる → USD/JPY は下がりやすい

【★重要な但し書き★】

上記のAEA論文は、EUR/USD で有意な結果を報告する一方、
**USD/JPYを含む他の通貨ペアはコスト控除後に利益が消失した**と明記している。
つまり USD/JPY で機能するかどうかは「未確認の仮説」であって、
既に確認された事実ではない。このスクリプトはそれを確かめるためにある。

【このスクリプトの2段構え】

  Phase 1: バイアスの定量化（コストなし・売買ルールなし）
      セッション別の平均リターンが統計的にゼロと区別できるかをt検定で見る。
      年別にも出して、「昔は効いたが今は消えている」パターンを検出する。

  Phase 2: 売買ルール化（コストあり）
      セッション開始で入り、終了で出る単純ルールに落として、
      スプレッドを引いた上で PF / DSR / 必要トレード数を評価する。
      判定基準は他の戦略と同じ（DSR≥0.95で有意）。

【方向の決め方について（自己欺瞞を避けるための設計）】

  データを見てから「勝つほうの方向」を選ぶと、それは検証ではなく後付けになる。
  そこで既定では、上の仮説から**事前に決めた方向**でのみ検証する。
      東京セッション → ロング（USD/JPY買い）
      NYセッション   → ショート（USD/JPY売り）
  データが選んだ方向の結果も参考として出すが、必ず「後付け」と明示する。

================================================================================
 使い方
================================================================================
    python home_away_research.py --phase1                 # バイアスの定量化
    python home_away_research.py --phase2                 # 売買ルール化+コスト
    python home_away_research.py --phase1 --phase2        # 両方
    python home_away_research.py --phase2 --spread-pips 0.8
================================================================================
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import fx_data as fx
from cascade_research import Trade, compute_stats, print_stats, _norm_cdf

# =============================================================================
# 設定
# =============================================================================

@dataclass
class SessionSpec:
    """セッションの定義。時刻は必ず「その市場の現地時間」で指定する。

    ★データ上の固定時刻で切ってはいけない★
    HistDataのタイムスタンプは固定EST（夏時間なし）だが、ロンドンとNYの
    市場は現地の夏時間に従って動く。現地時間で切らないと、夏冬で1時間
    ずれた集計になる（fx_data.py 冒頭の解説を参照）。
    """
    name: str
    market: str          # fx_data.MARKET_TZ のキー
    start_hm: str        # "09:00"
    end_hm: str          # "15:00"
    hypothesis_side: str  # 事前に決めた方向 "long" / "short"
    rationale: str


# =============================================================================
# 通貨ペアごとの設定 — 事前予測はハードコードせず、仮説から機械的に導く
# =============================================================================

# 各セッションで「ホーム」になる通貨。
# 仮説: その通貨は自国の営業時間中に売られる（＝減価する）。
SESSION_HOME_CCY: Dict[str, Tuple[str, ...]] = {
    "tokyo": ("JPY",),
    "london": ("EUR", "GBP", "CHF"),
    "newyork": ("USD", "CAD"),
}

SESSION_HOURS: Dict[str, Tuple[str, str, str]] = {
    # market: (開始, 終了, 表示名)
    "tokyo": ("09:00", "15:00", "東京"),
    "london": ("08:00", "16:00", "ロンドン"),
    "newyork": ("08:00", "17:00", "NY"),
}


def build_sessions(pair: str) -> List[SessionSpec]:
    """通貨ペアから、各セッションの事前予測を機械的に導出する。

    ★方向を手で書かない理由★
    ペアごとに手作業で「東京はロング」などと書くと、書き間違いや、
    結果を見てからの書き換え（後付け）が起きやすい。仮説そのもの
    （ホーム通貨は自国時間に売られる）から演繹すれば、その余地がなくなる。

      ホーム通貨 == BASE  → BASEが減価 → ペアは下落 → short
      ホーム通貨 == QUOTE → QUOTEが減価 → ペアは上昇 → long
      どちらでもない       → 事前予測なし（計測のみ）

    例) USDJPY: 東京(JPY=QUOTE)→long / NY(USD=BASE)→short
        EURUSD: ロンドン(EUR=BASE)→short / NY(USD=QUOTE)→long
    """
    p = pair.upper().replace("/", "")
    base, quote = p[:3], p[3:6]
    out: List[SessionSpec] = []
    for market, (start, end, label) in SESSION_HOURS.items():
        homes = SESSION_HOME_CCY[market]
        if base in homes:
            side = "short"
            why = (f"{base}のホーム時間。{base}が売られる→{p}は下がりやすい")
        elif quote in homes:
            side = "long"
            why = (f"{quote}のホーム時間。{quote}が売られる→{p}は上がりやすい")
        else:
            side = ""
            why = f"{p}にとってはどちらもアウェイ。事前予測なし（参考として計測）"
        out.append(SessionSpec(label, market, start, end, side, why))
    return out


def pip_size(pair: str) -> float:
    """1pipの大きさ。JPYクロスだけ桁が違う。"""
    p = pair.upper().replace("/", "")
    return 0.01 if p.endswith("JPY") else 0.0001


@dataclass
class CostModel:
    """コスト前提。

    HistDataのM1はBIDのみなので、ASKは観測できない。そこでスプレッドを
    想定値として置く。往復で1スプレッド分を負担する計算にしている
    （ロングなら ask で買って bid で売る＝ bid同士の差からスプレッド1回分を引く）。
    """
    pip: float                   # 通貨ペアの1pip（JPYクロスは0.01、他は0.0001）
    spread_pips: float = 0.5     # 想定スプレッド（往復で1回分負担）
    slippage_pips: float = 0.1   # 成行執行のずれ

    def cost_bps(self, price: float) -> float:
        if price <= 0:
            return 0.0
        cost_price = (self.spread_pips + self.slippage_pips) * self.pip
        return cost_price / price * 1e4


# =============================================================================
# セッション区切り
# =============================================================================

def _hm_to_minutes(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


@dataclass
class SessionBar:
    """1セッション＝1本、という粒度に集約したもの。"""
    date_local: pd.Timestamp
    ts_in: pd.Timestamp     # UTC
    ts_out: pd.Timestamp    # UTC
    open: float
    close: float
    high: float
    low: float
    bars: int
    ret_bps: float


def extract_sessions(df_utc: pd.DataFrame, spec: SessionSpec,
                     min_bars: int = 60) -> List[SessionBar]:
    """UTCインデックスのM1から、セッション単位のバーを切り出す。

    min_bars: この本数に満たないセッションは、祝日・短縮取引・データ欠損と
              みなして捨てる。中途半端な日を混ぜると平均が歪む。
    """
    local = fx.to_market_local(df_utc, spec.market)
    hhmm = local.index.hour * 60 + local.index.minute
    lo, hi = _hm_to_minutes(spec.start_hm), _hm_to_minutes(spec.end_hm)
    mask = (hhmm >= lo) & (hhmm < hi)
    sub = local[mask]
    if sub.empty:
        return []

    day = sub.index.normalize()
    grouped = sub.groupby(day)

    out: List[SessionBar] = []
    for d, g in grouped:
        if len(g) < min_bars:
            continue
        o = float(g["open"].iloc[0])
        c = float(g["close"].iloc[-1])
        if not (np.isfinite(o) and np.isfinite(c)) or o <= 0:
            continue
        out.append(SessionBar(
            date_local=pd.Timestamp(d),
            ts_in=g.index[0].tz_convert("UTC"),
            ts_out=g.index[-1].tz_convert("UTC"),
            open=o, close=c,
            high=float(g["high"].max()), low=float(g["low"].min()),
            bars=len(g),
            ret_bps=(c / o - 1.0) * 1e4,
        ))
    return out


# =============================================================================
# Phase 1: バイアスの定量化（コストなし）
# =============================================================================

def t_test_mean_zero(x: np.ndarray) -> Tuple[float, float]:
    """平均がゼロと区別できるかの片側でないt検定（両側p値）。

    nが数百〜数千あるので、t分布は正規分布で近似できる。
    scipy依存を増やさないため、既存の_norm_cdfを使う。
    """
    n = len(x)
    if n < 3:
        return float("nan"), float("nan")
    sd = float(np.std(x, ddof=1))
    if sd <= 0:
        return float("nan"), float("nan")
    t = float(np.mean(x)) / (sd / math.sqrt(n))
    p = 2.0 * (1.0 - _norm_cdf(abs(t)))
    return t, p


def phase1(df: pd.DataFrame, sessions: List[SessionSpec],
           min_bars: int = 60) -> Dict[str, List[SessionBar]]:
    """セッション別の平均リターンが、統計的にゼロと区別できるかを見る。

    ここではコストも売買ルールも入れない。「そもそも偏りが存在するのか」
    という一点だけを確かめる段階。
    """
    print("\n" + "=" * 70)
    print(" Phase 1: セッション別の方向バイアス（コスト控除なし）")
    print("=" * 70)
    print("  ここでは『偏りが存在するか』だけを見る。売買可能かはPhase 2で判断する。")

    results: Dict[str, List[SessionBar]] = {}
    for spec in sessions:
        bars = extract_sessions(df, spec, min_bars=min_bars)
        results[spec.name] = bars
        if not bars:
            print(f"\n  [{spec.name}] データなし")
            continue

        r = np.array([b.ret_bps for b in bars])
        t, p = t_test_mean_zero(r)
        up = float((r > 0).mean())
        pred = {"long": "上昇", "short": "下落", "": "予測なし"}[spec.hypothesis_side]

        print(f"\n  [{spec.name}セッション] {spec.start_hm}-{spec.end_hm} "
              f"({fx.MARKET_TZ[spec.market]})")
        print(f"    仮説            : {spec.rationale}")
        print(f"    事前予測        : {pred}")
        print(f"    日数            : {len(r):,}")
        print(f"    平均リターン    : {r.mean():+.3f} bps")
        print(f"    中央値          : {np.median(r):+.3f} bps")
        print(f"    標準偏差        : {r.std(ddof=1):.2f} bps")
        print(f"    上昇した日の割合: {up*100:.2f} %")
        print(f"    t値 / p値       : {t:+.2f} / {p:.4f}", end="")
        if p < 0.01:
            print("   → 1%水準で有意")
        elif p < 0.05:
            print("   → 5%水準で有意")
        else:
            print("   → 有意でない")

        if spec.hypothesis_side:
            aligned = (r.mean() > 0) == (spec.hypothesis_side == "long")
            print(f"    事前予測との一致: {'○ 一致' if aligned else '× 逆方向'}")

        # --- 年別の推移（裁定されて消えていないかを見る） ---
        ser = pd.Series(r, index=[b.date_local for b in bars])
        by_year = ser.groupby(ser.index.year).agg(["count", "mean"])
        print("    年別平均(bps)   : ", end="")
        print("  ".join(f"{y}:{row['mean']:+.2f}" for y, row in by_year.iterrows()))
        pos_years = int((by_year["mean"] > 0).sum())
        print(f"                      プラスの年 {pos_years}/{len(by_year)}")

    return results


# =============================================================================
# Phase 2: 売買ルール化（コストあり）
# =============================================================================

def sessions_to_trades(bars: List[SessionBar], side: str,
                       cost: CostModel) -> List[Trade]:
    """セッション開始で入り、終了で出る単純ルールをトレードに落とす。"""
    trades: List[Trade] = []
    for b in bars:
        gross = b.ret_bps if side == "long" else -b.ret_bps
        net = gross - cost.cost_bps(b.open)
        trades.append(Trade(
            ts_in=b.ts_in, ts_out=b.ts_out, side=side,
            entry=b.open, exit=b.close, reason="time",
            ret_bps=net, bars_held=b.bars,
        ))
    return trades


def _split_is_oos(bars: List[SessionBar], oos_from_year: int
                  ) -> Tuple[List[SessionBar], List[SessionBar]]:
    is_ = [b for b in bars if b.date_local.year < oos_from_year]
    oos = [b for b in bars if b.date_local.year >= oos_from_year]
    return is_, oos


def phase2(results: Dict[str, List[SessionBar]], sessions: List[SessionSpec],
           cost: CostModel, oos_from_year: int, n_trials: int) -> None:
    """コストを引いた上で、PF / DSR / 必要トレード数を評価する。"""
    print("\n" + "=" * 70)
    print(" Phase 2: 売買ルール化（コスト控除あり）")
    print("=" * 70)
    print(f"  想定スプレッド: {cost.spread_pips} pips / スリッページ: "
          f"{cost.slippage_pips} pips （往復で1回分を負担）")
    print(f"  イン/アウトサンプル分割: 〜{oos_from_year-1}年 = IS / "
          f"{oos_from_year}年〜 = OOS")
    print(f"  DSRの多重検定補正: n_trials={n_trials}")

    for spec in sessions:
        bars = results.get(spec.name) or []
        if not bars:
            continue
        if not spec.hypothesis_side:
            print(f"\n  [{spec.name}] 事前予測が無いためPhase 2は行いません"
                  f"（後付けで方向を選ばないため）")
            continue

        side = spec.hypothesis_side
        is_bars, oos_bars = _split_is_oos(bars, oos_from_year)

        print(f"\n{'-'*70}")
        print(f"  [{spec.name}セッション] 事前予測の方向 = "
              f"{'ロング' if side == 'long' else 'ショート'}")
        print(f"{'-'*70}")

        for label, subset, nt in (("全期間", bars, n_trials),
                                  ("IS(検証用)", is_bars, 1),
                                  ("OOS(検証外)", oos_bars, 1)):
            if not subset:
                continue
            tr = sessions_to_trades(subset, side, cost)
            st = compute_stats(tr, n_trials=nt)
            gross = np.mean([b.ret_bps if side == "long" else -b.ret_bps
                             for b in subset])
            print(f"\n   ● {label}  ({subset[0].date_local.date()} 〜 "
                  f"{subset[-1].date_local.date()})")
            print(f"     トレード数      : {st.n:,}")
            print(f"     平均(コスト前)  : {gross:+.3f} bps")
            print(f"     平均(コスト後)  : {st.avg_bps:+.3f} bps")
            print(f"     勝率            : {st.win_rate*100:.2f} %")
            print(f"     PF              : {st.profit_factor:.3f}")
            print(f"     トレードSharpe  : {st.sharpe_trade:.4f}")
            print(f"     最大DD          : {st.max_dd_bps:.1f} bps")
            print(f"     DSR             : {st.dsr:.4f}", end="")
            if st.dsr >= 0.95:
                print("  → 有意")
            elif st.dsr >= 0.80:
                print("  → 要追加検証")
            else:
                print("  → 有意でない")
            if np.isfinite(st.n_required):
                short = max(0, int(st.n_required) - st.n)
                print(f"     必要トレード数  : {int(st.n_required):,}", end="")
                print("  → 充足" if short == 0 else f"  → あと {short:,} 件必要")
            else:
                print("     必要トレード数  : 算出不能（平均がマイナス）")

        # --- 参考: データが選んだ方向（後付けなので判断には使わない） ---
        best = max(("long", "short"),
                   key=lambda s: compute_stats(
                       sessions_to_trades(bars, s, cost)).profit_factor)
        if best != side:
            st_b = compute_stats(sessions_to_trades(bars, best, cost),
                                 n_trials=n_trials)
            print(f"\n     ※参考: データ上は{'ロング' if best=='long' else 'ショート'}"
                  f"のほうがPFは高い(PF={st_b.profit_factor:.3f})。ただしこれは"
                  f"結果を見てから選んだ後付けなので、判断材料にはしない。")


# =============================================================================
# CLI
# =============================================================================

def main() -> None:
    ap = argparse.ArgumentParser(description="Home/Away効果の検証（USD/JPY）")
    ap.add_argument("--pair", default="USDJPY")
    ap.add_argument("--data-dir", default=fx.DEFAULT_DATA_DIR)
    ap.add_argument("--phase1", action="store_true")
    ap.add_argument("--phase2", action="store_true")
    ap.add_argument("--spread-pips", type=float, default=0.5)
    ap.add_argument("--slippage-pips", type=float, default=0.1)
    ap.add_argument("--oos-from", type=int, default=2023,
                    help="この年以降をアウトオブサンプルとして分ける")
    ap.add_argument("--min-bars", type=int, default=60,
                    help="この本数未満のセッションは祝日等として除外")
    ap.add_argument("--n-trials", type=int, default=None,
                    help="DSRの多重検定補正。既定は事前予測を持つセッション数")
    a = ap.parse_args()

    if not (a.phase1 or a.phase2):
        a.phase1 = a.phase2 = True

    print(f"[読み込み] {a.pair} …")
    df = fx.load(a.pair, a.data_dir)
    print(f"  {len(df):,}本  ({df.index[0]} 〜 {df.index[-1]})")

    # 読み込んだ直後にタイムゾーンを実証チェックする。
    # ここが狂っているとセッション分析の結果は無意味になるため、素通りさせない。
    v = fx.verify_timezone_convention(df)
    if not v["passed"]:
        print("\n★タイムゾーンの検証に失敗しました。分析を中止します。★")
        sys.exit(1)

    sessions = build_sessions(a.pair)
    n_trials = a.n_trials if a.n_trials is not None else \
        max(1, sum(1 for s in sessions if s.hypothesis_side))

    print(f"\n[事前予測] {a.pair} — 仮説から機械的に導出（結果を見てからは変更しない）")
    for s in sessions:
        pred = {"long": "ロング", "short": "ショート", "": "予測なし"}[s.hypothesis_side]
        print(f"  {s.name:6s} {s.start_hm}-{s.end_hm}  → {pred}")

    results = phase1(df, sessions, min_bars=a.min_bars) if a.phase1 else \
        {s.name: extract_sessions(df, s, min_bars=a.min_bars) for s in sessions}

    if a.phase2:
        cost = CostModel(pip=pip_size(a.pair), spread_pips=a.spread_pips,
                         slippage_pips=a.slippage_pips)
        phase2(results, sessions, cost, a.oos_from, n_trials)

    print("\n" + "=" * 70)
    print(" 判定の目安: DSR≥0.95=有意 / 0.80〜0.95=要追加検証 / <0.80=却下")
    print(" PFが良くてもトレード数が必要数に届いていなければ『まだ判断できない』。")
    print(" 結果は research_ledger.md に追記すること。")
    print("=" * 70)


if __name__ == "__main__":
    main()
