#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 FX ヒストリカルデータ取得・整形パイプライン（HistData.com）
================================================================================

【このファイルが最優先で守っていること: タイムゾーン】

★公式仕様書の記載は、実データと一致しない★

HistData.comの公式仕様ページにはこう書かれている。

    All data files are in Eastern Standard Time (EST)
    WITHOUT Day Light Savings adjustments

しかし USD/JPY 2015-2026 の実データ（金曜605週分）で実測したところ、
週末クローズはファイル上で夏も冬も 16:59 で一定だった。
FX市場の週末クローズは「NY現地時間の金曜17時」で固定されているため、
ファイルの時計が固定オフセットなら夏冬で1時間ずれて見えるはずである。
ずれていない以上、ファイルの時計は NY現地時間（夏時間に追随）である。

    仕様書どおり固定UTC-5で変換していたら、
    夏時間期間（605週中398週＝全体の約3分の2）が丸ごと1時間ずれ、
    しかもエラーは一切出ないまま分析結果だけが壊れていた。

したがって本モジュールは America/New_York として解釈する。
この判断は verify_timezone_convention() でいつでも再検証できるし、
配信元が将来また規約を変えたときも同じ手順で検出できる。

  ★教訓★
    タイムゾーンは仕様書ではなくデータ自身に確認させること。
    判定には「絶対時刻」ではなく「夏と冬でずれるかどうか」を使うと、
    クローズが16時か17時かを知らなくても規約を特定できる。

このモジュールは、読み込んだ時点で必ず「真のUTC」に変換し、
以降のすべての処理はUTC基準のインデックスから派生させる。
生のファイル表記をそのまま業務ロジックに持ち込ませない、というのが設計方針。

【セッション境界について、もうひとつの罠】

データのタイムスタンプが固定オフセットである一方、実際の市場は現地の
夏時間に従って動く。したがって「データ上の固定時刻」でセッションを
区切ると、ロンドンとNYのセッションが半年ぶん1時間ずれて集計される。

  東京   : Asia/Tokyo       — 夏時間なし。UTC+9で固定
  ロンドン: Europe/London    — 冬GMT / 夏BST(UTC+1)。ずれる
  NY     : America/New_York — 冬EST(UTC-5) / 夏EDT(UTC-4)。ずれる

そのため to_market_local() で、各市場の「本物の現地時間」に変換してから
セッションを定義する。fixed offsetでの近似はしない。

【データの性質（backtestの前提として重要）】

  - 1分足(M1)は BID のみ。ASKは含まれない
    → スプレッドは別途、想定値としてコストモデルに載せる必要がある
  - volume列はFXでは常に0（意味を持たない）
  - 土日は完全に欠損（週足の切れ目は NY時間 金17:00 〜 日17:00）

================================================================================
 使い方（ユーザーのPC側で実行する。クラウド検証環境からはHistData.comへ
 アクセスできないため、ダウンロードはローカルで行う）
================================================================================

    pip install requests pandas pyarrow tzdata --break-system-packages

    ★tzdata は Windows では必須★
      WindowsにはOS標準のタイムゾーンデータベースが無いため、これを入れないと
      Asia/Tokyo や America/New_York への変換が ZoneInfoNotFoundError で落ちる。

    # 1) ダウンロード（初回。年数ぶん時間がかかる）
    python fx_data.py --download --pair USDJPY --from 2015 --to 2026

    # 2) タイムゾーン規約の実証チェック（★必ず最初に通すこと★）
    python fx_data.py --verify --pair USDJPY

    # 3) 概況の確認
    python fx_data.py --diagnostics --pair USDJPY

================================================================================
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

# =============================================================================
# 定数
# =============================================================================

# =============================================================================
# ★★ ファイルの時計の解釈 — ここが本モジュールで最も重要な設定 ★★
# =============================================================================
#
# HistData.comの公式仕様ページにはこう書かれている:
#
#     All data files are in Eastern Standard Time (EST)
#     WITHOUT Day Light Savings adjustments
#
# ところが、実際のファイルはこの記載と一致しない。
# USD/JPY 2015-2026（605週分）で実測した結果:
#
#     週末クローズ(ファイル上) 夏 : 16:59
#     週末クローズ(ファイル上) 冬 : 16:59
#     夏冬のズレ                  : 0分
#
# FX市場の週末クローズは「NY現地時間の金曜17時」で固定されているため、
# ファイルの時計が固定オフセットなら、夏と冬で1時間ずれて見えるはずである。
# ずれていない＝ファイルの時計はNY現地時間（夏時間に追随）である。
#
# 仕様書を信じて固定UTC-5で変換すると、夏時間期間（605週中398週、
# 全体の約3分の2）が丸ごと1時間ずれる。しかもエラーは一切出ない。
#
# したがって America/New_York として解釈する。
# この判断は verify_timezone_convention() でいつでも再検証できる。
#
HISTDATA_TZ = "America/New_York"

# 旧実装の値（仕様書どおりの固定オフセット）。実測と食い違ったため不使用。
# 判定ロジックの説明用に残してある。
HISTDATA_UTC_OFFSET_HOURS = -5

BASE = "https://www.histdata.com"
REFERER_TMPL = (BASE + "/download-free-forex-historical-data/"
                "?/ascii/1-minute-bar-quotes/{pair}/{path}")
GET_URL = BASE + "/get.php"

# 各市場の「本物の現地タイムゾーン」（夏時間を正しく扱う）
MARKET_TZ: Dict[str, str] = {
    "tokyo": "Asia/Tokyo",
    "london": "Europe/London",
    "newyork": "America/New_York",
    "jst": "Asia/Tokyo",      # 別名（日本時間で見たいとき用）
}

DEFAULT_DATA_DIR = "fx_data"

# 読み込みキャッシュの世代。タイムゾーンの解釈など、CSVからDataFrameへの
# 変換規則を変えたら必ずこの数字を上げる（古いキャッシュを読ませないため）。
#   v1: 固定UTC-5として変換していた版（実測と食い違ったため破棄）
#   v2: America/New_York として変換する版（現行）
CACHE_VERSION = 2

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0 Safari/537.36")


# =============================================================================
# 1. ダウンロード
# =============================================================================

class HistDataError(Exception):
    pass


class HistDataDownloader:
    """HistData.com からM1のZIPを取得する。

    サイトはPOSTの前にCSRFトークン(`tk`)を要求するため、
      ① ダウンロードページをGETして <input id="tk"> を拾う
      ② そのトークンを付けて /get.php にPOSTする
    という2段構えになっている。この流れはサイト側の変更で壊れうるので、
    失敗時は「何段目で失敗したか」が分かるようにログを出す。
    """

    def __init__(self, timeout: float = 60.0, sleep_sec: float = 1.0):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT})
        self.timeout = timeout
        self.sleep_sec = sleep_sec

    def _fetch_token(self, pair: str, path: str) -> Tuple[str, str]:
        url = REFERER_TMPL.format(pair=pair.lower(), path=path)
        r = self.s.get(url, timeout=self.timeout)
        if r.status_code != 200:
            raise HistDataError(f"参照ページの取得に失敗 (HTTP {r.status_code}): {url}")
        m = re.search(r'id=["\']tk["\']\s+value=["\']([^"\']+)["\']', r.text)
        if not m:
            m = re.search(r'name=["\']tk["\']\s+value=["\']([^"\']+)["\']', r.text)
        if not m:
            raise HistDataError(
                f"CSRFトークン(tk)が見つかりません。サイトの構造が変わった可能性: {url}")
        return m.group(1), url

    def download(self, pair: str, year: int, month: Optional[int] = None) -> bytes:
        """1年分（month=None）または1か月分のZIPをbytesで返す。

        ★HistDataの仕様上のクセ★
        すでに終了した年は「年まるごと」で取得できるが、進行中の年は
        月単位でしか提供されない。呼び出し側(download_range)がこれを面倒みる。
        """
        path = f"{year}" if month is None else f"{year}/{month}"
        tk, referer = self._fetch_token(pair, path)
        payload = {
            "tk": tk,
            "date": str(year),
            "datemonth": f"{year}{month:02d}" if month else str(year),
            "platform": "ASCII",
            "timeframe": "M1",
            "fxpair": pair.upper(),
        }
        r = self.s.post(GET_URL, data=payload,
                        headers={"Referer": referer}, timeout=self.timeout)
        if r.status_code != 200:
            raise HistDataError(f"ZIP取得に失敗 (HTTP {r.status_code}): {pair} {path}")
        if not r.content[:2] == b"PK":
            raise HistDataError(
                f"ZIPではない応答が返りました（データ未提供の期間かもしれません）: "
                f"{pair} {path} / 先頭bytes={r.content[:32]!r}")
        time.sleep(self.sleep_sec)
        return r.content


def _extract_csv(zip_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise HistDataError(f"ZIP内にCSVがありません: {z.namelist()}")
        return z.read(names[0]).decode("utf-8", errors="replace")


def download_range(pair: str, year_from: int, year_to: int,
                   data_dir: str = DEFAULT_DATA_DIR,
                   overwrite: bool = False) -> List[Path]:
    """指定年範囲のCSVをローカルに保存する。既にあるものはスキップ。"""
    out_dir = Path(data_dir) / pair.upper()
    out_dir.mkdir(parents=True, exist_ok=True)
    dl = HistDataDownloader()
    written: List[Path] = []
    now = pd.Timestamp.now("UTC")
    this_year = now.year

    for year in range(year_from, year_to + 1):
        # 進行中の年は月単位でしか取れない
        months: List[Optional[int]] = [None] if year < this_year else list(range(1, 13))
        for month in months:
            # ★当月と未来の月は取りに行かない★
            #   HistDataは「完了した月」しか公開しないため、当月以降を
            #   リクエストしても必ず失敗する。無駄な試行とまぎらわしい
            #   エラーメッセージを避けるため、最初から対象外にする。
            if month is not None and (year, month) >= (now.year, now.month):
                continue
            tag = f"{year}" if month is None else f"{year}-{month:02d}"
            dest = out_dir / f"{pair.upper()}_{tag}.csv"
            if dest.exists() and not overwrite:
                print(f"  skip (既存): {dest.name}")
                written.append(dest)
                continue
            try:
                blob = dl.download(pair, year, month)
                dest.write_text(_extract_csv(blob), encoding="utf-8")
                print(f"  saved: {dest.name}")
                written.append(dest)
            except HistDataError as e:
                # 進行中の年の未到来の月などは普通に失敗する。止めずに続ける
                print(f"  -- {tag}: {e}")
    return written


# =============================================================================
# 2. 読み込みとタイムゾーン変換（このモジュールの心臓部）
# =============================================================================

def _parse_csv(path: Path) -> pd.DataFrame:
    """HistDataのM1 CSVを読む。

    形式: DateTime Stamp;OPEN;HIGH;LOW;CLOSE;Volume
          例) 20120201 000000;1.306600;1.306600;1.306560;1.306560;0
    価格はすべて BID。volumeはFXでは常に0。
    """
    df = pd.read_csv(
        path, sep=";", header=None,
        names=["ts", "open", "high", "low", "close", "volume"],
        dtype={"ts": str},
    )
    if df.empty:
        return df
    naive = pd.to_datetime(df["ts"], format="%Y%m%d %H%M%S", errors="coerce")
    bad = int(naive.isna().sum())
    if bad:
        print(f"    ! {path.name}: 日時をパースできない行が{bad}件（除外します）")
    df = df.assign(ts=naive).dropna(subset=["ts"])
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"])


def to_utc_index(df: pd.DataFrame, quiet: bool = False) -> pd.DataFrame:
    """HistDataのnaiveタイムスタンプを、真のUTCインデックスに変換する。

    ファイルの時計は America/New_York（夏時間あり）である。
    根拠は HISTDATA_TZ の定義箇所のコメントを参照（実測による）。

    ★夏時間の切り替わり時刻の扱いについて★
      米国の夏時間は日曜の午前2時に切り替わる。FX市場は金曜17時から
      日曜17時まで閉まっているため、切り替わりの時間帯にバーは存在しない。
      したがって「存在しない時刻」「二重に存在する時刻」は通常出てこないが、
      配信元の不具合で混入する可能性はゼロではない。黙って推測で埋めると
      静かにずれるので、NaTにして件数を報告し、落とす。
    """
    if df.empty:
        return df.drop(columns=["ts"], errors="ignore").set_index(
            pd.DatetimeIndex([], tz="UTC", name="ts_utc"))

    naive = pd.DatetimeIndex(df["ts"].values)
    localized = naive.tz_localize(HISTDATA_TZ, ambiguous="NaT", nonexistent="NaT")

    bad = localized.isna()
    n_bad = int(bad.sum())
    if n_bad and not quiet:
        print(f"    ! 夏時間の境界で解釈できない時刻が{n_bad}件ありました（除外します）")

    out = df.drop(columns=["ts"]).copy()
    out.index = localized.tz_convert("UTC").rename("ts_utc")
    out = out[~bad]
    return out.sort_index()


def load(pair: str, data_dir: str = DEFAULT_DATA_DIR,
         year_from: Optional[int] = None, year_to: Optional[int] = None,
         use_cache: bool = True) -> pd.DataFrame:
    """保存済みCSVをまとめて読み、UTCインデックスのDataFrameを返す。

    2回目以降を速くするため、結合結果をparquet（無ければpickle）に
    キャッシュする。CSVの数が変わったらキャッシュは作り直す。
    """
    src_dir = Path(data_dir) / pair.upper()
    if not src_dir.exists():
        raise FileNotFoundError(
            f"{src_dir} がありません。先に --download を実行してください")

    files = sorted(src_dir.glob(f"{pair.upper()}_*.csv"))
    if year_from is not None or year_to is not None:
        def _year_of(p: Path) -> int:
            return int(p.stem.split("_")[1][:4])
        lo = year_from if year_from is not None else -10**9
        hi = year_to if year_to is not None else 10**9
        files = [p for p in files if lo <= _year_of(p) <= hi]
    if not files:
        raise FileNotFoundError(f"{src_dir} に対象CSVがありません")

    # ★キャッシュキーにバージョンを入れる★
    #   タイムゾーンの解釈を変えたとき、ファイル数が同じだと古いキャッシュを
    #   そのまま読んでしまい、修正が反映されないまま分析が進む。
    #   解釈を変えたら CACHE_VERSION を上げること。
    cache = src_dir / f"_cache_v{CACHE_VERSION}_{len(files)}files.parquet"
    if use_cache and cache.exists():
        try:
            return pd.read_parquet(cache)
        except Exception as e:  # noqa: BLE001
            print(f"  キャッシュ読み込みに失敗、CSVから再構築します: {e}")

    frames = [to_utc_index(_parse_csv(p)) for p in files]
    frames = [f for f in frames if not f.empty]
    if not frames:
        raise ValueError("読み込めるデータがありませんでした")
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="first")]

    if use_cache:
        try:
            df.to_parquet(cache)
        except Exception as e:  # noqa: BLE001
            print(f"  キャッシュ保存をスキップ（pyarrow未導入など）: {e}")
    return df


def to_market_local(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """UTCインデックスを、各市場の「本物の現地時間」に変換する。

    ★fixed offsetでの近似はしない★
    ロンドンとNYは夏時間で1時間動く。セッション境界を現地の時計基準で
    定義するには、tzデータベース上の正しいタイムゾーンに変換する必要がある。
    """
    if market not in MARKET_TZ:
        raise ValueError(f"未知の市場です: {market} (選択肢: {list(MARKET_TZ)})")
    if df.index.tz is None:
        raise ValueError("UTCのtz-awareインデックスを渡してください")
    out = df.copy()
    out.index = df.index.tz_convert(MARKET_TZ[market])
    return out


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """M1から任意の足に集約する（例: "5min", "15min", "1h"）。"""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df.columns:
        agg["volume"] = "sum"
    return df.resample(rule, label="left", closed="left").agg(agg).dropna(subset=["close"])


# =============================================================================
# 3. 検証 ── 「仕様書を信じる」のではなく、データ自身に確認させる
# =============================================================================

def _naive_file_clock(df: pd.DataFrame) -> pd.DatetimeIndex:
    """UTCインデックスから、生ファイル上の時計表記へ戻す。

    localize(X) → convert(UTC) → convert(X) → naive は往復で必ず元に戻るため、
    Xの選択が正しいかどうかに関わらず、生ファイルの表記を復元できる。
    だからこの関数を使った判定は、現在の設定が正しいかを検証する材料になる
    （設定が自分自身を正当化してしまう循環にはならない）。
    """
    return df.index.tz_convert(HISTDATA_TZ).tz_localize(None)


def verify_timezone_convention(df: pd.DataFrame, verbose: bool = True) -> dict:
    """データがどの時計で記録されているかを、データ自身から判定する。

    【判定の原理 — 絶対時刻ではなく「夏冬のズレ」を見る】

    FX市場の週次クローズは「NY現地時間の金曜夕方」で固定されている。
    クローズが16時なのか17時なのかは配信元によって違うが、そこは問題ではない。
    決定的なのは、夏と冬でズレるかどうか。

      ファイルの時計が固定オフセット（夏時間に追随しない）
        → 市場は現地時間で動くので、ファイル上のクローズ時刻は
           夏と冬で1時間ずれて見える
      ファイルの時計がNY現地時間（夏時間に追随する）
        → 夏も冬もファイル上のクローズ時刻は同じに見える

    この「ズレの有無」だけで規約が確定する。絶対時刻を知る必要がない。

    ★以前の実装の誤り（記録として残す）★
      当初は「週の最終バー」を月曜始まりの週で集計していたが、FX市場は
      日曜夜に開くため、月曜始まりの週の最終バーは日曜夜になる。
      結果として金曜終わりの週＝日曜データが欠けた異常な週だけが
      拾われ、11年分のデータから9週しか検査していなかった。
      現在は「各金曜の最終バー」を直接見るように改めている。
    """
    if df.empty:
        raise ValueError("空のDataFrameです")

    naive = _naive_file_clock(df)
    fri = naive[naive.dayofweek == 4]
    if len(fri) == 0:
        raise ValueError("金曜のバーが見つかりません")

    # 各金曜の最終バー（＝その週のクローズ）
    ser = pd.Series(fri, index=fri)
    last_per_fri = ser.groupby(fri.normalize()).last()
    dates = pd.DatetimeIndex(last_per_fri.index)
    times = pd.DatetimeIndex(last_per_fri.values)
    minutes = times.hour * 60 + times.minute

    # その金曜がNYの夏時間期間だったか
    is_dst = np.array([
        bool(pd.Timestamp(d).tz_localize("America/New_York").dst().total_seconds())
        for d in dates])

    summer = pd.Series(minutes[is_dst])
    winter = pd.Series(minutes[~is_dst])
    s_mode = int(summer.mode().iloc[0]) if len(summer) else None
    w_mode = int(winter.mode().iloc[0]) if len(winter) else None
    shift = (w_mode - s_mode) if (s_mode is not None and w_mode is not None) else None

    def _fmt(m: Optional[int]) -> str:
        return "-" if m is None else f"{m // 60:02d}:{m % 60:02d}"

    res = {
        "fridays_checked": int(len(dates)),
        "summer_fridays": int(is_dst.sum()),
        "winter_fridays": int((~is_dst).sum()),
        "summer_close_file_clock": s_mode,
        "winter_close_file_clock": w_mode,
        "shift_minutes": shift,
    }

    # ズレが約0分  → ファイルの時計はNY現地時間（＝現在の実装が正しい）
    # ズレが約60分 → ファイルの時計は固定オフセット（実装を変える必要がある）
    if shift is None:
        detected, passed = "判定不能", False
    elif abs(shift) <= 5:
        detected, passed = "NY現地時間(夏時間あり)", True
    elif abs(shift - 60) <= 5:
        detected, passed = "固定オフセット(夏時間なし)", False
    else:
        detected, passed = f"想定外のズレ({shift}分)", False
    res["detected"] = detected
    res["configured"] = HISTDATA_TZ
    res["passed"] = bool(passed)

    # 年別の内訳。途中で配信元が規約を変えていないかを確認する。
    by_year: Dict[int, Tuple[int, Optional[int], Optional[int]]] = {}
    years = pd.Index(dates.year)
    for y in sorted(set(years)):
        sel = years == y
        s_y = pd.Series(minutes[sel & is_dst])
        w_y = pd.Series(minutes[sel & ~is_dst])
        by_year[int(y)] = (
            int(sel.sum()),
            int(s_y.mode().iloc[0]) if len(s_y) else None,
            int(w_y.mode().iloc[0]) if len(w_y) else None,
        )
    res["by_year"] = by_year
    res["consistent_across_years"] = all(
        (s is None or w is None or abs(w - s) <= 5) for _, s, w in by_year.values())

    if verbose:
        print("\n[タイムゾーン規約の実証チェック]")
        print(f"  検査した金曜の数        : {res['fridays_checked']:,}"
              f" (夏時間期間 {res['summer_fridays']:,} / "
              f"標準時期間 {res['winter_fridays']:,})")
        print(f"  週末クローズ(ファイル上) 夏 : {_fmt(s_mode)}")
        print(f"  週末クローズ(ファイル上) 冬 : {_fmt(w_mode)}")
        print(f"  夏冬のズレ              : "
              f"{'-' if shift is None else f'{shift}分'}"
              f"   （0分ならNY現地時間 / 60分なら固定オフセット）")
        print(f"  → 検出された規約: 「{detected}」")
        print(f"     現在の設定    : HISTDATA_TZ = {HISTDATA_TZ}")
        print("\n  年別の内訳（夏/冬のクローズ時刻がずれていないか）")
        for y, (n, s_y, w_y) in by_year.items():
            mark = "" if (s_y is None or w_y is None or abs(w_y - s_y) <= 5) else "  ★ズレあり"
            print(f"    {y}: 金曜{n:3d}回  夏={_fmt(s_y)}  冬={_fmt(w_y)}{mark}")
        if not res["consistent_across_years"]:
            print("  ★年によって規約が違います。期間を分けて扱う必要があります★")
        if passed:
            print("\n  → 判定: OK。現在の実装で正しく変換できています")
        else:
            print("\n  → 判定: ★NG★ 現在の実装は誤りです。分析に進んではいけません")
    return res


def diagnostics(df: pd.DataFrame, verbose: bool = True) -> dict:
    """データの概況。欠損・カバー率・異常値の当たりをつける。"""
    idx = df.index
    span_days = (idx[-1] - idx[0]).total_seconds() / 86400.0
    # 平日の分数に対する充足率（土日は市場が閉まっているので分母から除く）
    days = pd.date_range(idx[0].normalize(), idx[-1].normalize(), freq="1D", tz="UTC")
    weekday_minutes = int((days.dayofweek < 5).sum()) * 1440

    gaps = idx.to_series().diff().dropna()
    big_gaps = gaps[gaps > pd.Timedelta(hours=6)]

    res = {
        "rows": int(len(df)),
        "start_utc": str(idx[0]),
        "end_utc": str(idx[-1]),
        "span_days": round(span_days, 1),
        "coverage_vs_weekday_minutes": round(len(df) / weekday_minutes, 3) if weekday_minutes else None,
        "gaps_over_6h": int(len(big_gaps)),
        "max_gap_hours": round(gaps.max().total_seconds() / 3600.0, 1) if len(gaps) else None,
        "price_min": float(df["close"].min()),
        "price_max": float(df["close"].max()),
    }
    if verbose:
        print("\n[データ概況]")
        print(f"  本数            : {res['rows']:,}")
        print(f"  期間(UTC)       : {res['start_utc']} 〜 {res['end_utc']}  ({res['span_days']}日)")
        print(f"  平日分数に対する充足率: {res['coverage_vs_weekday_minutes']}")
        print(f"  6時間超の欠損   : {res['gaps_over_6h']}件 (最大 {res['max_gap_hours']}時間)")
        print(f"  価格レンジ      : {res['price_min']} 〜 {res['price_max']}")
        print("  ※週末(金NY17:00〜日NY17:00)の欠損は正常です")
    return res


# =============================================================================
# CLI
# =============================================================================

def main() -> None:
    ap = argparse.ArgumentParser(description="HistData.com FXデータ取得・検証")
    ap.add_argument("--pair", default="USDJPY")
    ap.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--from", dest="year_from", type=int, default=2015)
    ap.add_argument("--to", dest="year_to", type=int,
                    default=pd.Timestamp.now("UTC").year)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--verify", action="store_true", help="タイムゾーン規約の実証チェック")
    ap.add_argument("--diagnostics", action="store_true")
    a = ap.parse_args()

    if a.download:
        print(f"[ダウンロード] {a.pair} {a.year_from}〜{a.year_to}")
        download_range(a.pair, a.year_from, a.year_to, a.data_dir, a.overwrite)
        print("完了。次は --verify でタイムゾーンを確認してください。")
        return

    if a.verify or a.diagnostics:
        df = load(a.pair, a.data_dir, a.year_from if a.year_from != 2015 else None,
                  a.year_to)
        print(f"[読み込み] {a.pair}: {len(df):,}本")
        if a.verify:
            r = verify_timezone_convention(df)
            if not r["passed"]:
                sys.exit(1)
        if a.diagnostics:
            diagnostics(df)
        return

    ap.print_help()


if __name__ == "__main__":
    main()
