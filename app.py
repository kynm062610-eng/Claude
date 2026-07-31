"""YouTube競合・視聴者・トレンド分析ツール。

起動方法:
    streamlit run app.py

事前に .env に YOUTUBE_API_KEY を設定してください(.env.example 参照)。
"""

import datetime as dt
import html
import os
import re

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import analysis
import report
import storage
from youtube_client import YouTubeClient

load_dotenv()

APP_TITLE = "YouTube競合・視聴者・トレンド分析ツール"

if "mobile_mode" not in st.session_state:
    st.session_state.mobile_mode = True

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📊",
    layout="centered" if st.session_state.mobile_mode else "wide",
)

if st.session_state.mobile_mode:
    st.markdown(
        """
        <style>
        html, body, [class*="css"] { font-size: 18px !important; }
        h1 { font-size: 1.35rem !important; line-height: 1.4 !important; }
        .stButton>button, .stTextInput input, .stSelectbox div[data-baseweb="select"],
        .stSlider, .stTabs [data-baseweb="tab"] { font-size: 17px !important; }
        .stButton>button { padding: 0.7rem 1rem !important; width: 100%; }
        div[data-testid="stMetric"] { padding: .5rem 0; }
        div[data-testid="column"] { min-width: 100% !important; flex: 1 1 100% !important; }
        div[data-testid="stDataFrame"] { font-size: 15px !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource
def get_client(api_key: str) -> YouTubeClient:
    return YouTubeClient(api_key)


def videos_to_df(videos) -> pd.DataFrame:
    if not videos:
        return pd.DataFrame()
    df = pd.DataFrame([v.__dict__ for v in videos])
    df["published_at"] = pd.to_datetime(df["published_at"])
    return df.sort_values("view_count", ascending=False)


def format_count_ja(n) -> str:
    """100000 -> '10万' のように日本語の桁単位で読みやすくする。"""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "-"

    def trim(v: float) -> str:
        s = f"{v:.1f}"
        return s[:-2] if s.endswith(".0") else s

    if n >= 100_000_000:
        return f"{trim(n / 100_000_000)}億"
    if n >= 10_000:
        return f"{trim(n / 10_000)}万"
    return f"{n:,}"


_VIDEO_CARD_CSS = """
<style>
.yt-card {
    display:flex; gap:12px; align-items:flex-start;
    padding:10px 4px; border-bottom:1px solid rgba(128,128,128,.25);
    text-decoration:none; color:inherit;
}
.yt-card:hover { background: rgba(128,128,128,.08); }
.yt-card-thumb {
    width:128px; height:72px; object-fit:cover; border-radius:8px;
    flex:none; background:rgba(128,128,128,.2);
}
.yt-card-title { font-weight:600; font-size:.95rem; line-height:1.35; }
.yt-card-channel { font-size:.8rem; opacity:.65; margin-top:3px; }
.yt-card-stats { font-size:.8rem; opacity:.85; margin-top:3px; font-variant-numeric: tabular-nums; }
</style>
"""


def render_video_table(df: pd.DataFrame):
    """動画をタップするとYouTubeで開けるカード一覧として表示する。"""
    if df.empty:
        st.info("該当する動画が見つかりませんでした。")
        return

    cards = [_VIDEO_CARD_CSS]
    for _, row in df.iterrows():
        video_id = html.escape(str(row.get("video_id", "")), quote=True)
        url = f"https://www.youtube.com/watch?v={video_id}"
        title = html.escape(str(row.get("title", "")))
        channel = html.escape(str(row.get("channel_title", "")))
        thumb = html.escape(str(row.get("thumbnail_url", "")), quote=True)
        views = format_count_ja(row.get("view_count", 0))
        likes = format_count_ja(row.get("like_count", 0))
        comments = format_count_ja(row.get("comment_count", 0))
        published = pd.to_datetime(row.get("published_at")).strftime("%Y/%m/%d")
        thumb_html = f'<img class="yt-card-thumb" src="{thumb}">' if thumb else '<div class="yt-card-thumb"></div>'
        cards.append(f'''
<a class="yt-card" href="{url}" target="_blank" rel="noopener">
  {thumb_html}
  <div style="min-width:0;">
    <div class="yt-card-title">{title}</div>
    <div class="yt-card-channel">{channel}</div>
    <div class="yt-card-stats">▶ {views}回 ・ 👍 {likes} ・ 💬 {comments} ・ {published}</div>
  </div>
</a>''')
    st.markdown("".join(cards), unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def cached_dominant_color(thumbnail_url: str) -> str | None:
    return analysis.dominant_color(thumbnail_url)


def render_pattern_analysis(df: pd.DataFrame, label: str, key: str):
    """タイトル・タグ・ハッシュタグ・サムネイル色の傾向をまとめて表示する。"""
    if df.empty:
        return
    with st.expander("📊 傾向分析(似た動画の企画ヒント)"):
        insights = analysis.growth_insights(df)
        if insights:
            st.markdown("**📈 伸びている動画の共通点(推定)**")
            for line in insights:
                st.markdown(f"- {line}")
            st.caption("※ データ上の相関から見える傾向であり、断定はできません。")
            st.divider()

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**タイトルの頻出ワード**")
            words = analysis.title_word_frequency(df["title"].tolist())
            if words:
                word_df = pd.DataFrame(words, columns=["ワード", "回数"]).set_index("ワード")
                st.bar_chart(word_df)
            else:
                st.caption("集計できるワードがありませんでした。")
        with col2:
            st.markdown("**頻出タグ**")
            tags = analysis.tag_frequency(df["tags"].tolist())
            if tags:
                tag_df = pd.DataFrame(tags, columns=["タグ", "回数"]).set_index("タグ")
                st.bar_chart(tag_df)
            else:
                st.caption("タグを公開している動画がありませんでした。")

        hashtags = analysis.hashtag_frequency(df["description"].tolist())
        if hashtags:
            st.markdown("**概要欄の頻出ハッシュタグ**")
            st.write(" ".join(f"`{tag}`({count})" for tag, count in hashtags))

        st.markdown("**⏰ 投稿時間帯(日本時間)**")
        hour_dist = analysis.posting_hour_distribution(df)
        if not hour_dist.empty:
            st.bar_chart(hour_dist)
        for line in analysis.posting_time_insights(df):
            st.markdown(f"- {line}")

        st.markdown("**上位動画のサムネイル代表色**")
        top_thumbs = df.head(8)
        swatch_cols = st.columns(max(len(top_thumbs), 1))
        for col, (_, row) in zip(swatch_cols, top_thumbs.iterrows()):
            with col:
                if row["thumbnail_url"]:
                    st.image(row["thumbnail_url"], use_container_width=True)
                color = cached_dominant_color(row["thumbnail_url"])
                if color:
                    st.markdown(
                        f'<div style="background:{color};height:22px;border-radius:4px;"></div>',
                        unsafe_allow_html=True,
                    )
                    st.caption(color)

        st.divider()
        render_download_section(df, label, f"{key}_pattern")


def render_comment_analysis(df: pd.DataFrame, key: str):
    """視聴者コメントを取得し、どんな反応が多いかを分類して見せる。"""
    if df.empty:
        return

    with st.expander("💬 視聴者コメントの反応分析"):
        target_count = pick_count(
            "コメントを読む動画数(再生数の多い順)", f"{key}_comment_videos", [3, 5, 10], 5
        )
        st.caption("コメントの取得には動画1本あたり1ポイント使います(1日の無料枠は10,000)。")

        if st.button("💬 コメントを分析する", key=f"{key}_comment_run"):
            targets = df.head(target_count)
            comments: list[str] = []
            progress = st.progress(0.0, text="コメントを取得しています...")
            for i, (_, row) in enumerate(targets.iterrows(), start=1):
                comments.extend(client.get_video_comments(row["video_id"], max_results=50))
                progress.progress(i / len(targets), text=f"コメントを取得しています... {i}/{len(targets)}本")
            progress.empty()
            st.session_state[f"comments_{key}"] = comments

        comments = st.session_state.get(f"comments_{key}")
        if comments is None:
            return
        if not comments:
            st.info("コメントを取得できませんでした(コメント無効の可能性があります)。")
            return

        sentiment = analysis.comment_sentiment(comments)

        st.markdown("**読み取れること**")
        for line in analysis.comment_insights(comments, sentiment):
            st.markdown(f"- {line}")
        st.caption("※ キーワードによる自動分類です。皮肉や文脈までは読み取れません。")

        if sentiment:
            st.markdown("**反応の内訳**")
            sentiment_df = pd.DataFrame(
                sorted(sentiment.items(), key=lambda x: x[1], reverse=True),
                columns=["反応", "件数"],
            ).set_index("反応")
            st.bar_chart(sentiment_df)

        words = analysis.comment_word_frequency(comments)
        if words:
            st.markdown("**コメントの頻出ワード**")
            st.bar_chart(pd.DataFrame(words, columns=["ワード", "回数"]).set_index("ワード"))

        st.markdown("**コメントの例**")
        for c in comments[:5]:
            st.markdown(f"> {c[:150]}")


def render_download_section(df: pd.DataFrame, label: str, key: str):
    """分析結果をiPhoneの「ファイル」アプリなどに保存できるダウンロードボタン。"""
    if df.empty:
        return
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    safe_label = re.sub(r"[^\w\-]", "_", label)[:40]

    with st.container(border=True):
        st.markdown("### 💾 この分析結果を保存する")
        col_txt, col_csv = st.columns(2)
        col_txt.download_button(
            "📄 レポートを保存",
            data=report.build_text_report(df, label).encode("utf-8"),
            file_name=f"{safe_label}_{stamp}.txt",
            mime="text/plain",
            key=f"dl_txt_{key}",
            use_container_width=True,
            type="primary",
        )
        col_csv.download_button(
            "📊 一覧を保存(CSV)",
            data=("﻿" + report.build_csv(df)).encode("utf-8"),
            file_name=f"{safe_label}_{stamp}.csv",
            mime="text/csv",
            key=f"dl_csv_{key}",
            use_container_width=True,
        )
        st.caption("ボタンを押したあと「\"ファイル\"に保存」を選ぶと、iPhone内に残せます。")


def pick_count(label: str, key: str, options: list[int], default: int) -> int:
    """スライダーの代わりに、決まった数をワンタップで選べるようにする。"""
    st.markdown(f"**{label}**")
    picker = getattr(st, "segmented_control", None) or getattr(st, "pills", None)
    if picker is not None:
        value = picker(
            label, options, default=default, key=key,
            format_func=lambda n: f"{n}本", label_visibility="collapsed",
        )
        return value if value is not None else default
    return st.radio(
        label, options, index=options.index(default), horizontal=True,
        key=key, format_func=lambda n: f"{n}本", label_visibility="collapsed",
    )


def render_channel_result(res: dict, key: str):
    """保存済みのチャンネル分析結果を描画する(他を触っても消えないよう毎回描く)。"""
    df = res["df"]
    st.divider()
    col1, col2, col3 = st.columns(3)
    col1.metric("登録者数", f"{format_count_ja(res['subscriber_count'])}人")
    col2.metric("総再生回数", f"{format_count_ja(res['view_count'])}回")
    col3.metric("動画数", f"{res['video_count']:,}本")

    render_download_section(df, res["label"], key)

    if not df.empty:
        st.markdown("**再生数の推移(投稿日順)**")
        st.line_chart(df.sort_values("published_at").set_index("published_at")["view_count"])
        st.markdown("**動画一覧(再生数順)**")
    render_video_table(df)
    render_pattern_analysis(df, res["label"], key)
    render_comment_analysis(df, key)


st.title(f"📊 {APP_TITLE}")
st.session_state.mobile_mode = st.toggle(
    "📱 スマホ表示(文字を大きく・縦並びにする)",
    value=st.session_state.mobile_mode,
)

def _default_api_key() -> str:
    try:
        if "YOUTUBE_API_KEY" in st.secrets:
            return st.secrets["YOUTUBE_API_KEY"]
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get("YOUTUBE_API_KEY", "")


api_key = _default_api_key()
with st.sidebar:
    st.header("設定")
    if api_key:
        st.success("APIキーは登録済みです(Secretsから読み込み)")
        api_key_input = api_key
    else:
        api_key_input = st.text_input(
            "YouTube Data API キー", type="password",
            help="毎回入力したくない場合は、Streamlit CloudのSecretsに YOUTUBE_API_KEY を登録してください",
        )
    st.caption("キーは Google Cloud Console から取得できます。")

if not api_key_input:
    st.warning("サイドバーにYouTube Data API キーを入力してください。")
    st.stop()

try:
    client = get_client(api_key_input)
except Exception as e:  # noqa: BLE001
    st.error(f"APIクライアントの初期化に失敗しました: {e}")
    st.stop()

tab_own, tab_trend, tab_competitor = st.tabs(
    ["自分のチャンネル", "トレンド調査", "競合チャンネル分析"]
)

# ----------------------------------------------------------------------
# 自分のチャンネル
# ----------------------------------------------------------------------
with tab_own:
    st.subheader("自分のチャンネルの視聴者データ")
    own_query = st.text_input(
        "チャンネルID / @ハンドル / チャンネル名", key="own_query",
        placeholder="例: @MyChannel または UCxxxxxxxxxxxxxxxxxxxxxx",
    )
    max_videos_own = pick_count("取得する動画数", "own_max", [5, 10, 15, 20, 30, 50], 20)

    if st.button("分析する", key="own_run", type="primary") and own_query:
        with st.spinner("データを取得しています..."):
            channel_id = client.resolve_channel_id(own_query)
            if not channel_id:
                st.error("チャンネルが見つかりませんでした。")
            else:
                stats = client.get_channel_stats(channel_id)
                df = videos_to_df(client.get_channel_videos(channel_id, max_videos_own))
                st.session_state.result_own = {
                    "df": df,
                    "label": f"自分のチャンネル_{stats.title}",
                    "subscriber_count": stats.subscriber_count,
                    "view_count": stats.view_count,
                    "video_count": stats.video_count,
                }

    if st.session_state.get("result_own"):
        render_channel_result(st.session_state.result_own, "own")

# ----------------------------------------------------------------------
# トレンド調査
# ----------------------------------------------------------------------
with tab_trend:
    st.subheader("キーワード・トピックのトレンド調査")
    keyword = st.text_input("調査したいキーワード", key="trend_keyword", placeholder="例: 副業 プログラミング")
    col_a, col_b = st.columns(2)
    days = col_a.selectbox("期間", [7, 14, 30, 90], index=2, key="trend_days")
    order = col_b.selectbox(
        "並び順", ["viewCount", "relevance", "date", "rating"],
        format_func=lambda x: {
            "viewCount": "再生数順", "relevance": "関連度順", "date": "新着順", "rating": "評価順",
        }[x], key="trend_order",
    )
    max_trend = pick_count("取得件数", "trend_max", [5, 10, 15, 20, 30, 50], 20)

    if st.button("トレンドを調べる", key="trend_run", type="primary") and keyword:
        with st.spinner("トレンドを検索しています..."):
            df = videos_to_df(client.search_trending_videos(
                keyword, max_results=max_trend, published_within_days=days, order=order
            ))
            st.session_state.result_trend = {"df": df, "label": f"トレンド調査_{keyword}"}

    trend_res = st.session_state.get("result_trend")
    if trend_res:
        df = trend_res["df"]
        st.divider()
        render_download_section(df, trend_res["label"], "trend")
        if not df.empty:
            st.markdown("**上位動画のチャンネル別再生数合計**")
            by_channel = df.groupby("channel_title")["view_count"].sum().sort_values(ascending=False).head(10)
            st.bar_chart(by_channel)
        render_video_table(df)
        render_pattern_analysis(df, trend_res["label"], "trend")
        render_comment_analysis(df, "trend")

    st.divider()
    st.subheader("急上昇動画(地域別)")
    region = st.selectbox("地域", ["JP", "US", "KR", "GB"], key="popular_region")
    if st.button("急上昇動画を見る", key="popular_run"):
        with st.spinner("取得しています..."):
            st.session_state.result_popular = {
                "df": videos_to_df(client.get_most_popular(region_code=region, max_results=25)),
                "label": f"急上昇動画_{region}",
            }

    popular_res = st.session_state.get("result_popular")
    if popular_res:
        render_download_section(popular_res["df"], popular_res["label"], "popular")
        render_video_table(popular_res["df"])
        render_pattern_analysis(popular_res["df"], popular_res["label"], "popular")
        render_comment_analysis(popular_res["df"], "popular")

# ----------------------------------------------------------------------
# 競合チャンネル分析
# ----------------------------------------------------------------------
with tab_competitor:
    st.subheader("競合チャンネルの分析")

    saved_competitors = storage.load_competitors()

    st.markdown("**登録済みの競合チャンネル**")
    if saved_competitors:
        for c in saved_competitors:
            row_l, row_r = st.columns([5, 1.2])
            row_l.write(f"📌 {c['title']}")
            if row_r.button("削除", key=f"remove_{c['channel_id']}"):
                storage.remove_competitor(c["channel_id"])
                st.rerun()
        st.caption(
            "※ この一覧はアプリが稼働している間だけ保持されます。"
            "アプリの再起動・更新でリセットされる場合があります。"
        )
    else:
        st.caption("まだ登録がありません。下でチャンネルを分析し、「💾 保存」で追加できます。")

    if len(saved_competitors) >= 2:
        combined_max = pick_count(
            "各チャンネルから取得する動画数", "competitor_combined_max", [5, 10, 15, 20, 30], 15
        )
        if st.button(
            "🔍 登録済み競合をまとめて分析(共通点を探す)",
            key="competitor_combined_run", type="primary",
        ):
            with st.spinner(f"{len(saved_competitors)}チャンネル分のデータを取得しています..."):
                all_videos = []
                for c in saved_competitors:
                    all_videos.extend(client.get_channel_videos(c["channel_id"], combined_max))
                st.session_state.result_combined = {
                    "df": videos_to_df(all_videos),
                    "label": "競合まとめ分析",
                    "channel_count": len(saved_competitors),
                }

        combined_res = st.session_state.get("result_combined")
        if combined_res:
            combined_df = combined_res["df"]
            st.divider()
            if combined_df.empty:
                st.info("動画が取得できませんでした。")
            else:
                st.markdown(
                    f"**{combined_res['channel_count']}チャンネル・{len(combined_df)}本から見える共通点**"
                )
                render_download_section(combined_df, combined_res["label"], "combined")
                render_video_table(combined_df)
                render_pattern_analysis(combined_df, combined_res["label"], "combined")
                render_comment_analysis(combined_df, "combined")

    st.divider()
    st.markdown("**新しいチャンネルを分析する**")
    competitor_query = st.text_input(
        "競合チャンネルID / @ハンドル / チャンネル名", key="competitor_query",
        placeholder="例: @CompetitorChannel",
    )
    max_videos_competitor = pick_count(
        "取得する動画数", "competitor_max", [5, 10, 15, 20, 30, 50], 20
    )

    analyze_col, save_col = st.columns(2)
    run_clicked = analyze_col.button("分析する", key="competitor_run", type="primary")
    save_clicked = save_col.button("➕ 競合として登録", key="competitor_save")

    if save_clicked and competitor_query:
        with st.spinner("チャンネルを確認しています..."):
            channel_id = client.resolve_channel_id(competitor_query)
            if not channel_id:
                st.error("チャンネルが見つかりませんでした。")
            else:
                stats = client.get_channel_stats(channel_id)
                title = stats.title if stats else competitor_query
                storage.add_competitor(channel_id, title, competitor_query)
                st.success(f"「{title}」を登録済み競合チャンネルに保存しました。")
                st.rerun()

    if run_clicked and competitor_query:
        with st.spinner("データを取得しています..."):
            channel_id = client.resolve_channel_id(competitor_query)
            if not channel_id:
                st.error("チャンネルが見つかりませんでした。")
            else:
                stats = client.get_channel_stats(channel_id)
                df = videos_to_df(client.get_channel_videos(channel_id, max_videos_competitor))
                st.session_state.result_competitor = {
                    "df": df,
                    "label": f"競合_{stats.title}",
                    "subscriber_count": stats.subscriber_count,
                    "view_count": stats.view_count,
                    "video_count": stats.video_count,
                }

    if st.session_state.get("result_competitor"):
        render_channel_result(st.session_state.result_competitor, "competitor")
