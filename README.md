# Claude

## YouTube競合・視聴者・トレンド分析ツール

自分のチャンネルの視聴者データ、キーワード/トピックのトレンド、競合チャンネルを
分析できるStreamlitダッシュボードです。

### セットアップ

1. 依存パッケージをインストール
   ```bash
   pip install -r requirements.txt
   ```
2. `.env.example` を `.env` にコピーし、YouTube Data API v3のキーを設定
   ```bash
   cp .env.example .env
   # .env を編集して YOUTUBE_API_KEY=xxxx を設定
   ```
   APIキーは [Google Cloud Console](https://console.cloud.google.com/) で
   プロジェクトを作成し、「YouTube Data API v3」を有効化した上で
   「認証情報」から発行できます。
3. ダッシュボードを起動
   ```bash
   streamlit run app.py
   ```

### 機能

- **自分のチャンネル**: 登録者数・総再生数・動画数と、動画ごとの再生数推移を表示
- **トレンド調査**: キーワードで動画を検索し、再生数順・地域別急上昇動画を確認
- **競合チャンネル分析**: 競合チャンネルの統計情報と投稿傾向を可視化