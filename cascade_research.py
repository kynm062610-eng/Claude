#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 清算カスケード追随（Liquidation Cascade Fade） — 検証エンジン
================================================================================

【この戦略の構造的エッジ】

  強制ロスカットは「人間の判断」ではない。取引所のリスクエンジンが、価格を
  一切見ずに成行で投げる機械的な執行である。相手は賢くなれないし、待てないし、
  止まれない。これが暗号資産市場で最も明快な「なぜ相手が負けるのか」の答え。

  レバレッジが存在する限りこの機構は消えない。競争が増えれば行き過ぎ幅は
  縮むが、機構そのものは消えない。パターンのエッジ（見つかったら消える）とは
  性質が違う。

【最大のリスクと、その判別方法】

  カスケードを逆張りする最大の危険は「本物の材料で下げている」場合に
  ナイフを掴むこと。これは判別できる:

    レバレッジ・フラッシュ（乗ってよい）:
      - 建玉(OI)が急減する          → ポジションが実際に強制決済されている
      - Perp が Spot より下に乖離   → 売り圧力が先物側だけに存在する
      - テイカー売り比率が極端に偏る → 板を叩き潰す一方向の成行
      - 清算レートがピーク後に減衰   → 投げが尽きた

    本物の材料による再評価（乗ってはいけない）:
      - OI が減らない/増える        → 新規の売り建てが入っている
      - Spot が先に下げている        → 現物側で実需の売りが出ている
      - ベーシス乖離が起きない

  この判別が戦略の心臓部。単なる「急落を買う」との差はここにある。

【なぜ清算ストリームを直接使わないのか】

  Binance の !forceOrder@arr は「1銘柄あたり1秒に1件のみ」のサンプリング配信
  であり、清算総額の正確な測定には使えない（公式ドキュメント記載）。さらに
  過去の清算データは公開アーカイブに存在しない。

  したがって本エンジンは、清算カスケードを「アーカイブに存在する痕跡」から
  再構成する:
      片側テイカーフロー / 出来高スパイク / 価格速度 / Perp-Spot ベーシス乖離 / OI 急減

  これはバックテストと本番で完全に同じ特徴量を使えるという利点がある
  （検証と実運用で入力が変わるのが、この種のシステムが壊れる最大の原因）。
  本番では清算ストリームを「追加の確認材料」としてのみ使う。

================================================================================
 事前準備
================================================================================
    pip install pandas numpy requests --break-system-packages

    ※ このスクリプトは data.binance.vision から公開アーカイブを
      ダウンロードします。APIキーは不要です。

 実行例:
    python cascade_research.py --symbol BTCUSDT --months 2025-01 2025-06
    python cascade_research.py --symbol ETHUSDT --months 2025-01 2025-06 --grid

================================================================================
"""

from __future__ import annotations

import argparse
import io
import math
import os
import sys
import time
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import requests

BASE = "https://data.binance.vision/data"
CACHE_DIR = os.path.expanduser("~/.cache/binance_vision")

KLINE_COLS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
]

METRIC_COLS = [
    "create_time", "symbol", "sum_open_interest", "sum_open_interest_value",
    "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
    "count_long_short_ratio", "sum_taker_long_short_vol_ratio",
]


# =============================================================================
# 1. 設定
# =============================================================================

@dataclass
class Params:
    """カスケード検知と売買の全パラメータ。"""

    # --- 検知 ---
    lookback_bars: int = 3          # 何本分の値動きをカスケードとみなすか
    atr_window: int = 120           # ATR算出期間（分）
    move_atr_mult: float = 2.2      # 逆行幅が ATR の何倍を超えたら異常とみなすか
    taker_skew: float = 0.68        # テイカー売り比率がこれ以上なら「片側フロー」
    vol_z_min: float = 2.5          # 出来高 z-score の下限
    basis_z_min: float = 1.8        # ベーシス乖離 z-score の下限（先物が先行して乖離）
    oi_drop_pct: float = 0.35       # OI減少率(%)の下限。OI欠損時は無視される
    oi_window_bars: int = 15        # OI変化を測る窓(分)。OIは5分粒度なので3分では常に0になる
    require_oi: bool = False        # True なら OI が無いイベントを捨てる

    # --- 執行 ---
    exhaust_bars: int = 2           # 投げが尽きるのを何本待つか（0=即入る）
    oi_confirm_bars: int = 6        # OI確認の遅延(分)。OIは5分粒度なので即時には判定できない
    retrace_frac: float = 0.5       # 利確: カスケードの行き過ぎ幅の何割を取りに行くか
    target_atr: float = 1.1         # 利確の下限（ATR倍）。retrace が小さすぎる時の床
    stop_atr: float = 1.3           # 損切り: カスケード極値からさらに ATR の何倍
    time_stop_bars: int = 30        # 時間切れ（分）。戻らなければ思惑外れとして撤退
    cooldown_bars: int = 60         # 同一イベントの重複エントリー防止
    min_edge_mult: float = 2.0      # 利確幅がコストの何倍以上ないとエントリーしないか

    # --- コスト（GMOコイン想定） ---
    spread_bps: float = 6.0         # 平常時の往復スプレッド(bps)
    stress_spread_mult: float = 3.0 # カスケード中のスプレッド拡大倍率
    fee_bps: float = 0.0            # GMOレバレッジは取引手数料無料。現物なら要変更
    slippage_bps: float = 2.0       # 成行決済時の滑り

    # --- 統計正規化窓（vol_z / basis_z のベースライン） ---
    # 既定値は 1分足を前提に「1日ぶん」に相当する本数。他の足では
    # scaled_for_interval() が分単位から自動換算する。
    stat_window_bars: int = 1440
    stat_min_periods: int = 240

    def key(self) -> tuple:
        return (self.lookback_bars, self.move_atr_mult, self.taker_skew,
                self.vol_z_min, self.basis_z_min, self.exhaust_bars,
                self.target_atr, self.stop_atr, self.time_stop_bars)

    @classmethod
    def scaled_for_interval(cls, interval_minutes: int) -> "Params":
        """1分足で校正した既定値を、他の足の時間軸に自動換算する。

        本数(bars)で持っているパラメータは全て「意味のある実時間」に
        換算し直さないと、5分足に1分足の設定をそのまま使う事故が起きる
        （例: atr_window=120本のつもりが、5分足だと10時間分になる）。
        比率(%やATR倍率などの無次元量)は換算しない。
        """
        base = cls()
        if interval_minutes <= 1:
            return base

        def mins_to_bars(minutes_at_1m: int, floor: int = 1) -> int:
            return max(floor, round(minutes_at_1m / interval_minutes))

        return cls(
            # floor=2: 1本のロウソクだけで完結する異常値ではなく、複数本にまたがる
            # カスケードの「unfold」という概念を粗い足でも残すための最低本数。
            # floor=1 のままだと 5分足で round(3/5)=1本 まで縮み、事実上
            # 「1本の巨大な足」しか拾えなくなる（実測: 11銘柄中5銘柄が半年で0件）。
            lookback_bars=mins_to_bars(base.lookback_bars, 2),
            atr_window=mins_to_bars(base.atr_window, 10),
            oi_window_bars=mins_to_bars(base.oi_window_bars, 2),
            exhaust_bars=mins_to_bars(base.exhaust_bars, 0),
            oi_confirm_bars=mins_to_bars(base.oi_confirm_bars, 1),
            time_stop_bars=mins_to_bars(base.time_stop_bars, 3),
            cooldown_bars=mins_to_bars(base.cooldown_bars, 3),
            stat_window_bars=mins_to_bars(base.stat_window_bars, 60),
            stat_min_periods=mins_to_bars(base.stat_min_periods, 20),
            # 無次元量はそのまま引き継ぐ
            move_atr_mult=base.move_atr_mult, taker_skew=base.taker_skew,
            vol_z_min=base.vol_z_min, basis_z_min=base.basis_z_min,
            oi_drop_pct=base.oi_drop_pct, require_oi=base.require_oi,
            retrace_frac=base.retrace_frac, target_atr=base.target_atr,
            stop_atr=base.stop_atr, min_edge_mult=base.min_edge_mult,
            spread_bps=base.spread_bps, stress_spread_mult=base.stress_spread_mult,
            fee_bps=base.fee_bps, slippage_bps=base.slippage_bps,
        )


# =============================================================================
# 2. データ取得（data.binance.vision 公開アーカイブ）
# =============================================================================

def _month_range(start: str, end: str) -> List[str]:
    s = datetime.strptime(start, "%Y-%m")
    e = datetime.strptime(end, "%Y-%m")
    out = []
    while s <= e:
        out.append(s.strftime("%Y-%m"))
        s = (s.replace(day=28) + timedelta(days=8)).replace(day=1)
    return out


def _day_range(start: str, end: str) -> List[str]:
    """月指定を日付リストへ展開（metrics は日次ファイルのみ）。"""
    s = datetime.strptime(start, "%Y-%m").date()
    e = datetime.strptime(end, "%Y-%m").date()
    e = (e.replace(day=28) + timedelta(days=8)).replace(day=1) - timedelta(days=1)
    out, d = [], s
    while d <= e:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


def _download(url: str, quiet: bool = False) -> Optional[bytes]:
    """キャッシュ付きダウンロード。存在しない場合は None（404は正常系）。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, url.replace("/", "_").replace(":", ""))
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            return f.read() or None
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 404:
                with open(cache, "wb") as f:
                    f.write(b"")           # 不在を記録して再取得を避ける
                return None
            r.raise_for_status()
            with open(cache, "wb") as f:
                f.write(r.content)
            if not quiet:
                print(f"    取得 {url.split('/')[-1]} ({len(r.content)/1e6:.1f}MB)")
            return r.content
        except Exception as exc:
            if attempt == 2:
                print(f"    [警告] 取得失敗 {url}: {exc}")
                return None
            time.sleep(2 * (attempt + 1))
    return None


def _read_zip_csv(blob: bytes, cols: Sequence[str]) -> Optional[pd.DataFrame]:
    """Binance の zip 内 CSV を読む。ヘッダ有無を自動判定する。"""
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            name = z.namelist()[0]
            raw = z.read(name).decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"    [警告] zip展開失敗: {exc}")
        return None
    if not raw.strip():
        return None
    first = raw.split("\n", 1)[0].split(",")[0].strip().strip('"')
    has_header = True
    try:
        float(first)
        has_header = False
    except ValueError:
        pass
    df = pd.read_csv(
        io.StringIO(raw),
        header=0 if has_header else None,
        names=None if has_header else list(cols),
    )
    if has_header:
        df.columns = [c.strip() for c in df.columns]
    return df


def _to_utc_ms(series: pd.Series) -> pd.Series:
    """ms / us どちらの epoch でも UTC datetime に正規化する。

    Binance の SPOT データは 2025-01 以降マイクロ秒になったため、
    桁数で自動判定する（README 記載の仕様変更に対応）。
    """
    s = pd.to_numeric(series, errors="coerce")
    med = s.dropna().median()
    unit = "us" if med > 1e14 else "ms"
    return pd.to_datetime(s, unit=unit, utc=True)



# Binance は列名を改訂したことがある（実データで確認: 2025年時点のアーカイブは
# open_time,open,high,low,close,volume,close_time,quote_volume,
# count,taker_buy_volume,taker_buy_quote_volume,ignore という表記）。
# 本コードの内部処理は旧来の trades/taker_buy_base/taker_buy_quote という
# 名前で統一しているため、読み込み直後に別名を正規名へ吸収する。
KLINE_COL_ALIASES = {
    "count": "trades",
    "number_of_trades": "trades",
    "taker_buy_volume": "taker_buy_base",
    "taker_buy_base_asset_volume": "taker_buy_base",
    "taker_buy_quote_volume": "taker_buy_quote",
    "taker_buy_quote_asset_volume": "taker_buy_quote",
}


def load_klines(symbol: str, months: List[str], market: str,
                interval: str = "1m") -> pd.DataFrame:
    """perp('futures/um') または spot の 1分足を月次アーカイブから読み込む。"""
    seg = "futures/um" if market == "perp" else "spot"
    frames = []
    for m in months:
        url = f"{BASE}/{seg}/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{m}.zip"
        blob = _download(url)
        if blob is None:
            continue
        df = _read_zip_csv(blob, KLINE_COLS)
        if df is None or df.empty:
            continue
        df = df.rename(columns=KLINE_COL_ALIASES)
        frames.append(df)
    if not frames:
        raise SystemExit(
            f"[致命的] {market} {symbol} のデータを1件も取得できませんでした。\n"
            f"        銘柄名・期間・ネットワーク接続を確認してください。"
        )
    df = pd.concat(frames, ignore_index=True)
    df["ts"] = _to_utc_ms(df["open_time"])
    num = ["open", "high", "low", "close", "volume", "quote_volume",
           "trades", "taker_buy_base", "taker_buy_quote"]
    for c in num:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = (df.dropna(subset=["ts", "close"])
            .drop_duplicates(subset="ts")
            .sort_values("ts")
            .set_index("ts"))
    return df[num]


def load_open_interest(symbol: str, months: List[str]) -> Optional[pd.DataFrame]:
    """建玉(OI)を日次 metrics アーカイブから読み込む。

    metrics は公開アーカイブの中でも提供期間が限られており、
    取得できない場合は None を返して OI 条件を自動的に無効化する。
    """
    frames = []
    days = _day_range(months[0], months[-1])
    print(f"  OI(metrics) を試行中… ({len(days)}日分)")
    misses = 0
    for d in days:
        url = f"{BASE}/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{d}.zip"
        blob = _download(url, quiet=True)
        if blob is None:
            misses += 1
            if misses >= 10 and not frames:
                print("  → metrics が取得できないため OI 条件は無効化します")
                return None
            continue
        df = _read_zip_csv(blob, METRIC_COLS)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        print("  → metrics 取得ゼロ。OI 条件は無効化します")
        return None
    df = pd.concat(frames, ignore_index=True)
    tcol = "create_time" if "create_time" in df.columns else df.columns[0]
    oicol = ("sum_open_interest" if "sum_open_interest" in df.columns
             else df.columns[2])
    df["ts"] = pd.to_datetime(df[tcol], utc=True, errors="coerce")
    df["oi"] = pd.to_numeric(df[oicol], errors="coerce")
    df = (df.dropna(subset=["ts", "oi"])
            .drop_duplicates(subset="ts")
            .sort_values("ts")
            .set_index("ts")[["oi"]])
    print(f"  OI 取得 OK ({len(df):,}点)")
    return df


# =============================================================================
# 3. 特徴量 — カスケードの痕跡を再構成する
# =============================================================================

def build_features(perp: pd.DataFrame, spot: pd.DataFrame,
                   oi: Optional[pd.DataFrame], p: Params) -> pd.DataFrame:
    df = perp.copy()

    # --- ATR（True Range の指数移動平均） ---
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(span=p.atr_window, adjust=False, min_periods=p.atr_window).mean()

    # --- 価格速度: lookback 本の値動きを ATR で正規化 ---
    df["move"] = df["close"] - df["close"].shift(p.lookback_bars)
    df["move_atr"] = df["move"] / df["atr"]

    # --- 片側テイカーフロー ---
    # taker_buy_base はテイカーが「買った」出来高。売り比率 = 1 - buy/total。
    # 強制ロングロスカット中は成行売り一色になり、この値が 1 に張り付く。
    vol = df["volume"].replace(0, np.nan)
    df["taker_sell_ratio"] = 1.0 - (df["taker_buy_base"] / vol)
    df["taker_buy_ratio"] = df["taker_buy_base"] / vol

    # --- 出来高スパイク（z-score） ---
    lv = np.log1p(df["volume"])
    df["vol_z"] = (lv - lv.rolling(p.stat_window_bars, min_periods=p.stat_min_periods).mean()) \
        / lv.rolling(p.stat_window_bars, min_periods=p.stat_min_periods).std(ddof=0)

    # --- Perp-Spot ベーシス ---
    # 先物側だけが叩き売られると perp < spot に乖離する。これが
    # 「強制フロー由来」と「現物の実需売り」を分ける決定的な指標。
    sp = spot["close"].reindex(df.index).ffill(limit=5)
    df["spot_close"] = sp
    df["basis"] = df["close"] / sp - 1.0
    bmu = df["basis"].rolling(p.stat_window_bars, min_periods=p.stat_min_periods).mean()
    bsd = df["basis"].rolling(p.stat_window_bars, min_periods=p.stat_min_periods).std(ddof=0)
    df["basis_z"] = (df["basis"] - bmu) / bsd

    # --- 建玉の変化 ---
    if oi is not None:
        o = oi["oi"].reindex(df.index.union(oi.index)).sort_index().ffill()
        o = o.reindex(df.index)
        df["oi"] = o
        # OI は 5分粒度でしか配信されない。lookback(=数分)で差分を取ると
        # 前方補完のせいで恒常的に 0 になるため、必ず粒度より長い窓で測る。
        w = max(p.oi_window_bars, p.lookback_bars, 6)
        df["oi_chg_pct"] = (o / o.shift(w) - 1.0) * 100.0
    else:
        df["oi"] = np.nan
        df["oi_chg_pct"] = np.nan

    return df


# =============================================================================
# 4. イベント検知
# =============================================================================

@dataclass
class Event:
    ts: pd.Timestamp
    side: str                # "long"=下落フラッシュを買う / "short"=上昇フラッシュを売る
    move_atr: float
    taker_skew: float
    vol_z: float
    basis_z: float
    oi_chg_pct: float
    atr: float
    ref_price: float         # カスケード直前の価格（戻り目標の基準）
    entry_offset: int = 1    # 検知バーから何本後に入るか（OI確認の遅延を含む）


def detect_events(df: pd.DataFrame, p: Params) -> List[Event]:
    """レバレッジ・フラッシュのみを抽出する（本物の材料による下げは除外）。

    ■ OI 確認の遅延について
      Binance の建玉(OI)は 5分粒度でしか配信されない。したがって 1分足の
      価格・フロー・ベーシスの異常は検知できても、「建玉が実際に減ったか」は
      最大 5分遅れてからしか分からない。

      そこで OI は検知バー i ではなく区間 [i, i+oi_confirm_bars] で評価し、
      エントリーをその区間より後ろ（i + 1 + oi_confirm_bars）に強制する。
      こうすればエントリー時点で既に判明している情報しか使わないため、
      先読みにはならない。OI を使わない場合は exhaust_bars だけ待つ。
    """
    ev: List[Event] = []
    last_idx = -10 ** 9
    use_oi = df["oi_chg_pct"].notna().any()
    oi_lag = p.oi_confirm_bars if use_oi else 0
    entry_off = 1 + max(p.exhaust_bars, oi_lag)

    move_atr = df["move_atr"].to_numpy()
    tsr = df["taker_sell_ratio"].to_numpy()
    tbr = df["taker_buy_ratio"].to_numpy()
    volz = df["vol_z"].to_numpy()
    basisz = df["basis_z"].to_numpy()
    oichg = df["oi_chg_pct"].to_numpy()
    atr = df["atr"].to_numpy()
    close = df["close"].to_numpy()
    idx = df.index

    n = len(df)
    for i in range(p.lookback_bars, n - entry_off - 1):
        if i - last_idx < p.cooldown_bars:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        if not np.isfinite(volz[i]) or volz[i] < p.vol_z_min:
            continue

        # --- OI は遅延窓で評価する（entry はこの窓より後ろに置かれる） ---
        oi_ok = True
        oi_val = float("nan")
        if use_oi:
            win = oichg[i:i + oi_lag + 1]
            if np.any(np.isfinite(win)):
                oi_val = float(np.nanmin(win))
                # フラッシュなら建玉が「減る」。増えるのは新規参入＝本物の売買。
                oi_ok = oi_val <= -p.oi_drop_pct
            elif p.require_oi:
                continue
        elif p.require_oi:
            continue
        oi_ok_long = oi_ok_short = oi_ok

        # ---- 下落フラッシュ（ロングが焼かれた）→ 買い ----
        if (np.isfinite(move_atr[i]) and move_atr[i] <= -p.move_atr_mult
                and np.isfinite(tsr[i]) and tsr[i] >= p.taker_skew
                and np.isfinite(basisz[i]) and basisz[i] <= -p.basis_z_min
                and oi_ok_long):
            ev.append(Event(idx[i], "long", move_atr[i], tsr[i], volz[i],
                            basisz[i], oi_val, a, close[i - p.lookback_bars],
                            entry_off))
            last_idx = i
            continue

        # ---- 上昇フラッシュ（ショートが焼かれた）→ 売り ----
        if (np.isfinite(move_atr[i]) and move_atr[i] >= p.move_atr_mult
                and np.isfinite(tbr[i]) and tbr[i] >= p.taker_skew
                and np.isfinite(basisz[i]) and basisz[i] >= p.basis_z_min
                and oi_ok_short):
            ev.append(Event(idx[i], "short", move_atr[i], tbr[i], volz[i],
                            basisz[i], oi_val, a, close[i - p.lookback_bars],
                            entry_off))
            last_idx = i

    return ev


# =============================================================================
# 5. バックテスト
# =============================================================================

@dataclass
class Trade:
    ts_in: pd.Timestamp
    ts_out: pd.Timestamp
    side: str
    entry: float
    exit: float
    reason: str
    ret_bps: float
    bars_held: int


def backtest(df: pd.DataFrame, events: List[Event], p: Params,
             skipped_out: Optional[List] = None) -> List[Trade]:
    """1分足で逐次シミュレーション。

    重要な設計:
      - エントリーは検知バーの *次* のバーの始値（先読み防止）
      - exhaust_bars ぶん待つ場合はさらにその後
      - 損切りと利確が同一バー内で両方触れた場合は「損切り優先」で悲観的に扱う
    """
    trades: List[Trade] = []
    skipped: List[Event] = []
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    idx = df.index
    pos = {t: i for i, t in enumerate(idx)}

    for e in events:
        i0 = pos.get(e.ts)
        if i0 is None:
            continue
        i_entry = i0 + e.entry_offset
        if i_entry >= len(df) - 2:
            continue

        entry = o[i_entry]
        if not np.isfinite(entry) or entry <= 0:
            continue

        # --- カスケード極値を基準に損切りを置く ---
        # エントリーバー(i_entry)の高値・安値はエントリー時点では未確定なので
        # 必ず「エントリー直前まで」で切る（先読み防止）
        seg = slice(max(i0 - p.lookback_bars, 0), i_entry)

        # 利確幅は「行き過ぎた幅の何割を取り返すか」で決める。
        # ATR固定にすると、カスケードの規模と無関係な小さすぎる利確になり、
        # 往復コストに負ける（実測で確認済み）。
        if e.side == "long":
            extreme = np.nanmin(l[seg])
            dislocation = max(e.ref_price - extreme, 0.0)
            tdist = max(p.retrace_frac * dislocation, p.target_atr * e.atr)
            stop = extreme - p.stop_atr * e.atr
            target = entry + tdist
        else:
            extreme = np.nanmax(h[seg])
            dislocation = max(extreme - e.ref_price, 0.0)
            tdist = max(p.retrace_frac * dislocation, p.target_atr * e.atr)
            stop = extreme + p.stop_atr * e.atr
            target = entry - tdist

        # --- コスト: カスケード直後はスプレッドが開くことを織り込む ---
        cost_bps = (p.spread_bps * p.stress_spread_mult) / 2.0 \
            + p.spread_bps / 2.0 + p.fee_bps + p.slippage_bps

        # 利確幅がコストに見合わないなら「条件不成立」として見送る。
        # 最小ロット未満をスキップするのと同じ発想の、エッジ版の足切り。
        if (tdist / entry) * 1e4 < p.min_edge_mult * cost_bps:
            skipped.append(e)
            continue

        exit_px, reason, i_exit = None, "time", i_entry
        end = min(i_entry + p.time_stop_bars, len(df) - 1)
        for j in range(i_entry, end + 1):
            if e.side == "long":
                if l[j] <= stop:
                    exit_px, reason, i_exit = stop, "stop", j
                    break
                if h[j] >= target:
                    exit_px, reason, i_exit = target, "target", j
                    break
            else:
                if h[j] >= stop:
                    exit_px, reason, i_exit = stop, "stop", j
                    break
                if l[j] <= target:
                    exit_px, reason, i_exit = target, "target", j
                    break
        if exit_px is None:
            exit_px, reason, i_exit = c[end], "time", end

        gross = ((exit_px / entry - 1.0) if e.side == "long"
                 else (entry / exit_px - 1.0)) * 1e4
        net = gross - cost_bps

        trades.append(Trade(idx[i_entry], idx[i_exit], e.side, entry, exit_px,
                            reason, net, i_exit - i_entry))

    if skipped_out is not None:
        skipped_out.extend(skipped)
    return trades


# =============================================================================
# 6. 統計 — 本物のエッジか、偶然か
# =============================================================================

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(q: float) -> float:
    """逆正規CDF（Acklam近似）。scipy 非依存にするため自前実装。"""
    if not 0.0 < q < 1.0:
        return float("nan")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if q < pl:
        x = math.sqrt(-2 * math.log(q))
        return (((((c[0]*x+c[1])*x+c[2])*x+c[3])*x+c[4])*x+c[5]) / \
               ((((d[0]*x+d[1])*x+d[2])*x+d[3])*x+1)
    if q > ph:
        x = math.sqrt(-2 * math.log(1 - q))
        return -(((((c[0]*x+c[1])*x+c[2])*x+c[3])*x+c[4])*x+c[5]) / \
                ((((d[0]*x+d[1])*x+d[2])*x+d[3])*x+1)
    x = q - 0.5
    r = x * x
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*x / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


@dataclass
class Stats:
    n: int = 0
    win_rate: float = float("nan")
    avg_bps: float = float("nan")
    med_bps: float = float("nan")
    avg_win: float = float("nan")
    avg_loss: float = float("nan")
    payoff: float = float("nan")
    profit_factor: float = float("nan")
    sharpe_trade: float = float("nan")
    total_bps: float = float("nan")
    max_dd_bps: float = float("nan")
    dsr: float = float("nan")
    n_required: float = float("nan")
    stop_rate: float = float("nan")
    target_rate: float = float("nan")
    time_rate: float = float("nan")
    avg_bars: float = float("nan")


def compute_stats(trades: List[Trade], n_trials: int = 1) -> Stats:
    s = Stats(n=len(trades))
    if not trades:
        return s
    r = np.array([t.ret_bps for t in trades], dtype=float)
    wins, losses = r[r > 0], r[r <= 0]

    s.win_rate = len(wins) / len(r)
    s.avg_bps = float(r.mean())
    s.med_bps = float(np.median(r))
    s.avg_win = float(wins.mean()) if len(wins) else 0.0
    s.avg_loss = float(losses.mean()) if len(losses) else 0.0
    s.payoff = abs(s.avg_win / s.avg_loss) if s.avg_loss else float("inf")
    gp, gl = wins.sum(), abs(losses.sum())
    s.profit_factor = float(gp / gl) if gl > 0 else float("inf")
    s.total_bps = float(r.sum())
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    s.sharpe_trade = float(s.avg_bps / sd) if sd > 0 else float("nan")

    eq = np.cumsum(r)
    s.max_dd_bps = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0

    reasons = [t.reason for t in trades]
    s.stop_rate = reasons.count("stop") / len(reasons)
    s.target_rate = reasons.count("target") / len(reasons)
    s.time_rate = reasons.count("time") / len(reasons)
    s.avg_bars = float(np.mean([t.bars_held for t in trades]))

    # --- Deflated Sharpe Ratio ---
    # 「何通り試したか」を罰する。グリッドサーチで最良を拾うと
    # SR は必ず上振れるため、その分を割り引いて有意性を判定する。
    if len(r) > 3 and sd > 0 and n_trials >= 1:
        sr = s.sharpe_trade
        g = 0.5772156649
        n_t = max(int(n_trials), 1)
        if n_t > 1:
            e1 = _norm_ppf(1.0 - 1.0 / n_t)
            e2 = _norm_ppf(1.0 - 1.0 / (n_t * math.e))
            sr0 = ((1 - g) * e1 + g * e2)   # 帰無仮説下での期待最大SR（SR分散=1想定）
            sr0 *= 1.0 / math.sqrt(max(len(r) - 1, 1))
        else:
            sr0 = 0.0
        skew = float(pd.Series(r).skew())
        kurt = float(pd.Series(r).kurtosis()) + 3.0
        denom = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr
        if denom > 0:
            s.dsr = _norm_cdf(((sr - sr0) * math.sqrt(len(r) - 1)) / math.sqrt(denom))

    # --- 有意性の判定に必要な試行回数 ---
    if sd > 0 and s.avg_bps > 0:
        s.n_required = float(((1.96 + 0.84) * sd / s.avg_bps) ** 2)
    return s


def print_stats(title: str, s: Stats, p: Optional[Params] = None) -> None:
    print(f"\n{'='*66}\n {title}\n{'='*66}")
    if s.n == 0:
        print("  トレードなし（条件が厳しすぎる可能性）")
        return
    print(f"  トレード数        : {s.n:,}")
    print(f"  勝率              : {s.win_rate*100:6.2f} %")
    print(f"  平均損益          : {s.avg_bps:+7.2f} bps   (中央値 {s.med_bps:+.2f})")
    print(f"  平均利益 / 平均損失: {s.avg_win:+.2f} / {s.avg_loss:+.2f}  (payoff {s.payoff:.2f})")
    print(f"  プロフィットファクタ: {s.profit_factor:.3f}")
    print(f"  累積損益          : {s.total_bps:+,.0f} bps")
    print(f"  最大DD            : {s.max_dd_bps:,.0f} bps")
    print(f"  トレードSharpe    : {s.sharpe_trade:.4f}")
    print(f"  決済内訳          : 利確 {s.target_rate*100:.1f}% / "
          f"損切 {s.stop_rate*100:.1f}% / 時間切れ {s.time_rate*100:.1f}%")
    print(f"  平均保有          : {s.avg_bars:.1f} 分")
    if np.isfinite(s.dsr):
        verdict = "有意" if s.dsr > 0.95 else ("要追加検証" if s.dsr > 0.80 else "有意でない")
        print(f"  Deflated Sharpe   : {s.dsr:.4f}  → {verdict}")
    if np.isfinite(s.n_required):
        short = "充足" if s.n >= s.n_required else f"あと {s.n_required - s.n:,.0f} 件必要"
        print(f"  必要トレード数    : {s.n_required:,.0f}  → {short}")


# =============================================================================
# 7. パラメータ感度 / アウトオブサンプル
# =============================================================================

def split_is_oos(df: pd.DataFrame, frac: float = 0.6) -> Tuple[pd.DataFrame, pd.DataFrame]:
    k = int(len(df) * frac)
    return df.iloc[:k], df.iloc[k:]


def grid_search(df_is: pd.DataFrame, df_oos: pd.DataFrame,
                base: Params) -> Optional[Stats]:
    """限定的なグリッドを回し、IS最良のパラメータをOOSで検証する。

    グリッドを広く取るほど「たまたま勝つ組み合わせ」が見つかるため、
    試行回数を DSR に渡して割り引く。
    """
    grid: List[Params] = []
    for mv in (1.8, 2.2, 2.8):
        for tk in (0.62, 0.68, 0.75):
            for rf in (0.35, 0.5, 0.7):
                for st in (1.0, 1.3):
                    q = Params(**{**asdict(base), "move_atr_mult": mv,
                                  "taker_skew": tk, "retrace_frac": rf,
                                  "stop_atr": st})
                    grid.append(q)

    print(f"\n■ グリッドサーチ: {len(grid)} 通りを in-sample で評価")
    results = []
    for i, q in enumerate(grid, 1):
        ev = detect_events(df_is, q)
        tr = backtest(df_is, ev, q)
        st = compute_stats(tr, n_trials=len(grid))
        results.append((st, q))
        if i % 12 == 0:
            print(f"    {i}/{len(grid)} …")

    valid = [(s, q) for s, q in results if s.n >= 20]
    if not valid:
        print("  [!] 有効な組み合わせなし（イベントが少なすぎる）。"
              "期間を延ばすか条件を緩めてください。")
        return None

    valid.sort(key=lambda x: (x[0].sharpe_trade if np.isfinite(x[0].sharpe_trade)
                              else -9e9), reverse=True)
    best_s, best_q = valid[0]
    print_stats(f"IS 最良（{len(grid)}通り中）", best_s)
    print(f"  → move_atr={best_q.move_atr_mult} taker_skew={best_q.taker_skew} "
          f"retrace_frac={best_q.retrace_frac} stop_atr={best_q.stop_atr}")

    ev_o = detect_events(df_oos, best_q)
    tr_o = backtest(df_oos, ev_o, best_q)
    st_o = compute_stats(tr_o, n_trials=1)
    print_stats("OOS（未使用期間での検証）— こちらが本物の成績", st_o)

    # 上位群の安定性: 最良が孤立した山なら過剰適合の疑い
    top = valid[:max(3, len(valid) // 10)]
    sh = [s.sharpe_trade for s, _ in top if np.isfinite(s.sharpe_trade)]
    if sh:
        print(f"\n  上位{len(sh)}件のSharpe: 平均 {np.mean(sh):.4f} / "
              f"最小 {np.min(sh):.4f} / 最大 {np.max(sh):.4f}")
        if np.mean(sh) > 0 and (np.max(sh) - np.mean(sh)) > 1.5 * (np.std(sh) + 1e-12):
            print("  [警告] 最良値が突出しています。過剰適合の可能性が高いです。")
    return st_o


# =============================================================================
# 8. エントリポイント
# =============================================================================

@dataclass
class SymbolSummary:
    symbol: str
    interval: str
    events_per_day: float = 0.0
    n_all: int = 0
    pf_all: float = float("nan")
    dsr_all: float = float("nan")
    oos: Optional[Stats] = None
    error: str = ""


def run(symbol: str, months: List[str], do_grid: bool, p: Params,
        interval: str = "1m", quiet: bool = False) -> SymbolSummary:
    pr = (lambda *a, **k: None) if quiet else print
    pr(f"\n{'#'*66}\n# 清算カスケード追随 — 検証: {symbol}  {months[0]}〜{months[-1]}  "
       f"足:{interval}\n{'#'*66}")

    summary = SymbolSummary(symbol=symbol, interval=interval)
    try:
        pr("\n■ データ取得")
        pr(f"  perp {interval}足…")
        perp = load_klines(symbol, months, "perp", interval=interval)
        pr(f"  → {len(perp):,} 本  ({perp.index[0]} 〜 {perp.index[-1]})")
        pr(f"  spot {interval}足…")
        spot = load_klines(symbol, months, "spot", interval=interval)
        pr(f"  → {len(spot):,} 本")
        oi = load_open_interest(symbol, months) if not quiet else _try_oi_quiet(symbol, months)
    except SystemExit as e:
        summary.error = str(e)
        if not quiet:
            raise
        print(f"  [{symbol}] データ取得に失敗、スキップします: {e}")
        return summary

    pr("\n■ 特徴量の構築")
    df = build_features(perp, spot, oi, p)
    usable = df.dropna(subset=["atr", "vol_z", "basis_z"])
    pr(f"  有効バー: {len(usable):,} / {len(df):,}")
    if oi is None:
        pr("  ※ OI が取得できなかったため、OI条件なしで判定します"
           "（フラッシュ判別の精度は落ちます）")

    pr("\n■ イベント検知（全期間）")
    ev_all = detect_events(df, p)
    days = max((df.index[-1] - df.index[0]).total_seconds() / 86400.0, 1.0)
    summary.events_per_day = len(ev_all) / days
    pr(f"  検知イベント: {len(ev_all)} 件  → 約 {summary.events_per_day:.2f} 回/日")
    if ev_all:
        longs = sum(1 for e in ev_all if e.side == "long")
        pr(f"  内訳: 下落フラッシュ買い {longs} / 上昇フラッシュ売り {len(ev_all)-longs}")

    skipped: List[Event] = []
    tr_all = backtest(df, ev_all, p, skipped_out=skipped)
    if skipped:
        pr(f"  うち {len(skipped)} 件は利確幅がコストに見合わず見送り "
           f"(min_edge_mult={p.min_edge_mult})")
    st_all = compute_stats(tr_all)
    summary.n_all, summary.pf_all, summary.dsr_all = st_all.n, st_all.profit_factor, st_all.dsr
    if not quiet:
        print_stats("全期間（パラメータ調整なし・素の成績）", st_all)

    if do_grid:
        df_is, df_oos = split_is_oos(df, 0.6)
        if not quiet:
            print(f"\n■ 分割: IS {df_is.index[0].date()}〜{df_is.index[-1].date()} / "
                  f"OOS {df_oos.index[0].date()}〜{df_oos.index[-1].date()}")
        summary.oos = grid_search(df_is, df_oos, p)

    if tr_all and not quiet:
        out = pd.DataFrame([{
            "entry_time": t.ts_in, "exit_time": t.ts_out, "side": t.side,
            "entry": t.entry, "exit": t.exit, "reason": t.reason,
            "net_bps": t.ret_bps, "bars": t.bars_held,
        } for t in tr_all])
        path = f"cascade_trades_{symbol}_{interval}.csv"
        out.to_csv(path, index=False)
        print(f"\n  トレード明細を保存: {path}")

    if not quiet:
        print("\n" + "="*66)
        print(" 判断基準")
        print("="*66)
        print("  OOS のプロフィットファクタが 1.2 未満、または DSR が 0.95 未満なら、")
        print("  このパラメータでの実弾投入は見送ること。条件を変えて再検証するか、")
        print("  別の銘柄・期間で再現するかを先に確認する。")
        print("  「全期間の成績」ではなく「OOS の成績」だけを信じること。\n")

    return summary


def _try_oi_quiet(symbol: str, months: List[str]) -> Optional[pd.DataFrame]:
    try:
        return load_open_interest(symbol, months)
    except Exception:
        return None


# =============================================================================
# 8b. 複数銘柄の一括検証
#
# ここに並ぶ11銘柄は、GMOコイン「取引所（レバレッジ）」の取扱銘柄として
# 2024年4月の公式発表（BTC/ETH/BCH/LTC/XRPの既存5銘柄 + DOT/ATOM/ADA/
# LINK/DOGE/SOLの新規6銘柄で計11銘柄）に基づく。取扱銘柄はその後も
# 増減している可能性があるため、実弾を検討する前に必ず
# GMOコイン公式サイトか、以前渡した gmo_scalp_bot.py のドライラン実行結果
# （get_symbol_rules() の応答）で最新の一覧を確認すること。
# =============================================================================

GMO_LEVERAGE_SYMBOLS: Dict[str, str] = {
    "BTCUSDT": "BTC_JPY", "ETHUSDT": "ETH_JPY", "BCHUSDT": "BCH_JPY",
    "LTCUSDT": "LTC_JPY", "XRPUSDT": "XRP_JPY", "DOTUSDT": "DOT_JPY",
    "ATOMUSDT": "ATOM_JPY", "ADAUSDT": "ADA_JPY", "LINKUSDT": "LINK_JPY",
    "DOGEUSDT": "DOGE_JPY", "SOLUSDT": "SOL_JPY",
}


def run_multi(symbols: List[str], months: List[str], do_grid: bool,
             p: Params, interval: str = "1m") -> None:
    print(f"\n{'#'*66}")
    print(f"# 複数銘柄一括検証: {len(symbols)}銘柄 × {months[0]}〜{months[-1]} × 足:{interval}")
    print(f"{'#'*66}")
    if do_grid:
        print("※ --grid 併用のため銘柄数×グリッド分の時間がかかります。気長にお待ちください。")

    rows: List[SymbolSummary] = []
    for i, sym in enumerate(symbols, 1):
        print(f"\n[{i}/{len(symbols)}] {sym} を検証中…")
        try:
            s = run(sym, months, do_grid, p, interval=interval, quiet=True)
        except Exception as exc:
            print(f"  [{sym}] 想定外のエラーでスキップ: {exc}")
            s = SymbolSummary(symbol=sym, interval=interval, error=str(exc))
        rows.append(s)
        if s.error:
            continue
        if do_grid and s.oos:
            print(f"  → OOS: {s.oos.n}件 勝率{s.oos.win_rate*100:.1f}% "
                  f"PF={s.oos.profit_factor:.3f} DSR={s.oos.dsr:.4f} "
                  f"({s.events_per_day:.2f}回/日)")
        else:
            print(f"  → 全期間: {s.n_all}件 PF={s.pf_all:.3f} DSR={s.dsr_all:.4f} "
                  f"({s.events_per_day:.2f}回/日)")

    def sort_key(s: SymbolSummary) -> float:
        st = s.oos if (do_grid and s.oos) else None
        pf = st.profit_factor if st else s.pf_all
        return pf if np.isfinite(pf) else -9e9

    rows_ok = [s for s in rows if not s.error]
    rows_ok.sort(key=sort_key, reverse=True)

    label = "OOS" if do_grid else "全期間"
    print("\n" + "=" * 78)
    print(f" サマリー（{label}の成績で降順）— GMOコインで執行可能な銘柄のみ収録")
    print("=" * 78)
    print(f"{'銘柄':<10}{'件数':>6}{'勝率':>8}{'PF':>8}{'DSR':>8}{'回/日':>8}  判定")
    for s in rows_ok:
        st = s.oos if (do_grid and s.oos) else None
        n = st.n if st else s.n_all
        wr = f"{st.win_rate*100:.1f}%" if st else "-"
        pf = st.profit_factor if st else s.pf_all
        dsr = st.dsr if st else s.dsr_all
        verdict = ("実弾検討可" if (np.isfinite(pf) and pf >= 1.2
                                  and np.isfinite(dsr) and dsr >= 0.95)
                   else "見送り")
        gmo = GMO_LEVERAGE_SYMBOLS.get(s.symbol, "?")
        print(f"{s.symbol:<10}{n:>6}{wr:>8}{pf:>8.3f}{dsr:>8.4f}"
              f"{s.events_per_day:>8.2f}  {verdict}  (GMO: {gmo})")

    skipped_syms = [s.symbol for s in rows if s.error]
    if skipped_syms:
        print(f"\n  データ取得に失敗しスキップ: {', '.join(skipped_syms)}")

    winners = [s for s in rows_ok if sort_key(s) >= 1.2]
    if not winners:
        print("\n  どの銘柄も判断基準を満たしませんでした。この時間軸・この期間での")
        print("  カスケード追随フェードは、いずれの銘柄でも実弾に進める段階にありません。")
    print("=" * 78 + "\n")


INTERVAL_MINUTES = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
                    "1h": 60, "2h": 120, "4h": 240}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="清算カスケード追随戦略の検証エンジン")
    ap.add_argument("--symbol", default="BTCUSDT", help="例: BTCUSDT, ETHUSDT, SOLUSDT")
    ap.add_argument("--months", nargs=2, metavar=("START", "END"),
                    default=["2025-01", "2025-06"], help="例: 2025-01 2025-06")
    ap.add_argument("--interval", default="1m", choices=list(INTERVAL_MINUTES),
                    help="足の時間軸。既定パラメータは自動でこの足に換算される")
    ap.add_argument("--grid", action="store_true",
                    help="グリッドサーチ + アウトオブサンプル検証を行う")
    ap.add_argument("--multi", action="store_true",
                    help="GMOコインで執行可能な11銘柄をまとめて検証する（--symbolは無視）")
    ap.add_argument("--symbols", nargs="*", default=None,
                    help="--multi と併用: 検証銘柄を指定（省略時はGMO取扱11銘柄）")
    ap.add_argument("--move-atr", type=float, default=None)
    ap.add_argument("--taker-skew", type=float, default=None)
    ap.add_argument("--target-atr", type=float, default=None)
    ap.add_argument("--stop-atr", type=float, default=None)
    ap.add_argument("--spread-bps", type=float, default=None,
                    help="GMOコインの実測スプレッド(bps)を入れると現実的になる")
    a = ap.parse_args()

    p = Params.scaled_for_interval(INTERVAL_MINUTES[a.interval])
    if a.move_atr is not None:
        p.move_atr_mult = a.move_atr
    if a.taker_skew is not None:
        p.taker_skew = a.taker_skew
    if a.target_atr is not None:
        p.target_atr = a.target_atr
    if a.stop_atr is not None:
        p.stop_atr = a.stop_atr
    if a.spread_bps is not None:
        p.spread_bps = a.spread_bps

    months = _month_range(a.months[0], a.months[1])

    if a.multi:
        symbols = a.symbols if a.symbols else list(GMO_LEVERAGE_SYMBOLS)
        run_multi(symbols, months, a.grid, p, interval=a.interval)
    else:
        run(a.symbol, months, a.grid, p, interval=a.interval)


if __name__ == "__main__":
    main()
