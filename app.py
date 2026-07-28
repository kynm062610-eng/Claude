"""YouTube視聴者データ・トレンド分析ダッシュボード。

起動方法:
    streamlit run app.py

事前に .env に YOUTUBE_API_KEY を設定してください(.env.example 参照)。
"""

import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import analysis
from youtube_client import YouTubeClient

load_dotenv()

st.set_page_config(page_title="YouTube分析ダッシュボード", page_icon="📊", layout="wide")


@st.cache_resource
def get_client(api_key: str) -> YouTubeClient:
    return YouTubeClient(api_key)


def videos_to_df(videos) -> pd.DataFrame:
    if not videos:
        return pd.DataFrame()
    df = pd.DataFrame([v.__dict__ for v in videos])
    df["published_at"] = pd.to_datetime(df["published_at"])
    return df.sort_values("view_count", ascending=False)


def render_video_table(df: pd.DataFrame):
    if df.empty:
        st.info("該当する動画が見つかりませんでした。")
        return
    show = df[["title", "channel_title", "view_count", "like_count", "comment_count", "published_at"]].copy()
    show.columns = ["タイトル", "チャンネル", "再生数", "高評価数", "コメント数", "投稿日"]
    st.dataframe(show, use_container_width=True, hide_index=True)


@st.cache_data(show_spinner=False)
def cached_dominant_color(thumbnail_url: str) -> str | None:
    return analysis.dominant_color(thumbnail_url)


def render_pattern_analysis(df: pd.DataFrame):
    """タイトル・タグ・ハッシュタグ・サムネイル色の傾向をまとめて表示する。"""
    if df.empty:
        return
    with st.expander("📊 傾向分析(似た動画の企画ヒント)"):
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


st.title("📊 YouTube視聴者データ・トレンド分析ツール")

api_key = os.environ.get("YOUTUBE_API_KEY", "")
with st.sidebar:
    st.header("設定")
    api_key_input = st.text_input(
        "YouTube Data API キー", value=api_key, type="password",
        help=".env の YOUTUBE_API_KEY からも読み込めます",
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
    max_videos_own = st.slider("取得する動画数", 5, 50, 20, key="own_max")

    if st.button("分析する", key="own_run") and own_query:
        with st.spinner("データを取得しています..."):
            channel_id = client.resolve_channel_id(own_query)
            if not channel_id:
                st.error("チャンネルが見つかりませんでした。")
            else:
                stats = client.get_channel_stats(channel_id)
                col1, col2, col3 = st.columns(3)
                col1.metric("登録者数", f"{stats.subscriber_count:,}")
                col2.metric("総再生回数", f"{stats.view_count:,}")
                col3.metric("動画数", f"{stats.video_count:,}")

                videos = client.get_channel_videos(channel_id, max_videos_own)
                df = videos_to_df(videos)
                if not df.empty:
                    st.markdown("**再生数の推移(投稿日順)**")
                    chart_df = df.sort_values("published_at").set_index("published_at")["view_count"]
                    st.line_chart(chart_df)

                    st.markdown("**動画一覧(再生数順)**")
                render_video_table(df)
                render_pattern_analysis(df)

# ----------------------------------------------------------------------
# トレンド調査
# ----------------------------------------------------------------------
with tab_trend:
    st.subheader("キーワード・トピックのトレンド調査")
    keyword = st.text_input("調査したいキーワード", key="trend_keyword", placeholder="例: 副業 プログラミング")
    col_a, col_b, col_c = st.columns(3)
    days = col_a.selectbox("期間", [7, 14, 30, 90], index=2, key="trend_days")
    order = col_b.selectbox(
        "並び順", ["viewCount", "relevance", "date", "rating"],
        format_func=lambda x: {
            "viewCount": "再生数順", "relevance": "関連度順", "date": "新着順", "rating": "評価順",
        }[x], key="trend_order",
    )
    max_trend = col_c.slider("取得件数", 5, 50, 20, key="trend_max")

    if st.button("トレンドを調べる", key="trend_run") and keyword:
        with st.spinner("トレンドを検索しています..."):
            videos = client.search_trending_videos(
                keyword, max_results=max_trend, published_within_days=days, order=order
            )
            df = videos_to_df(videos)
            if not df.empty:
                st.markdown("**上位動画のチャンネル別再生数合計**")
                by_channel = df.groupby("channel_title")["view_count"].sum().sort_values(ascending=False).head(10)
                st.bar_chart(by_channel)
            render_video_table(df)
            render_pattern_analysis(df)

    st.divider()
    st.subheader("急上昇動画(地域別)")
    region = st.selectbox("地域", ["JP", "US", "KR", "GB"], key="popular_region")
    if st.button("急上昇動画を見る", key="popular_run"):
        with st.spinner("取得しています..."):
            popular_df = videos_to_df(client.get_most_popular(region_code=region, max_results=25))
            render_video_table(popular_df)
            render_pattern_analysis(popular_df)

# ----------------------------------------------------------------------
# 競合チャンネル分析
# ----------------------------------------------------------------------
with tab_competitor:
    st.subheader("競合チャンネルの分析")
    competitor_query = st.text_input(
        "競合チャンネルID / @ハンドル / チャンネル名", key="competitor_query",
        placeholder="例: @CompetitorChannel",
    )
    max_videos_competitor = st.slider("取得する動画数", 5, 50, 20, key="competitor_max")

    if st.button("分析する", key="competitor_run") and competitor_query:
        with st.spinner("データを取得しています..."):
            channel_id = client.resolve_channel_id(competitor_query)
            if not channel_id:
                st.error("チャンネルが見つかりませんでした。")
            else:
                stats = client.get_channel_stats(channel_id)
                col1, col2, col3 = st.columns(3)
                col1.metric("登録者数", f"{stats.subscriber_count:,}")
                col2.metric("総再生回数", f"{stats.view_count:,}")
                col3.metric("動画数", f"{stats.video_count:,}")

                videos = client.get_channel_videos(channel_id, max_videos_competitor)
                df = videos_to_df(videos)
                if not df.empty:
                    st.markdown("**投稿頻度と再生数の傾向**")
                    chart_df = df.sort_values("published_at").set_index("published_at")["view_count"]
                    st.line_chart(chart_df)
                render_video_table(df)
                render_pattern_analysis(df)
