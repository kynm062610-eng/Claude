# 07. 動画生成プロンプト（Veo 3.1 / Kling）

**方針：動かしすぎない。**
ゆきみの世界は「静けさ」が資産。派手に動かすと癒しが壊れる。

Kling は image-to-video で使う。
[06. 画像生成プロンプト](06-image-prompts.md) で作った画像を入力し、**わずかな動き**だけを指示する。

---

## 基本ルール

| 項目 | 設定 |
|---|---|
| モード | **image-to-video**（text-to-videoは使わない＝キャラが崩れる） |
| 尺 | 5秒 or 10秒。長いほど崩れやすいので **5秒推奨** |
| カメラ | 固定 or 極めてゆっくりのズームイン |
| 動きの量 | **最小**。Motion / CFG は低めに |
| 出力 | 9:16 縦 |

### やってはいけない指示
```
❌ flying, jumping, running, spinning, dancing
❌ fast, quick, sudden, dramatic, dynamic
❌ camera shake, whip pan, zoom out fast
❌ character turns around（振り向きで顔が崩れる）
❌ talking, lip sync（くちばしが破綻する）
```

---

## モーションテンプレート

### M1. 語りの基本（全パート共通・使用頻度最高）
```
The character stays still and gently breathes, its fluffy body softly rising
and falling. It blinks slowly a few times. The knitted scarf sways very
slightly in a soft breeze. Snow falls gently and continuously in the
background. The camera is completely static. Extremely subtle motion,
calm and peaceful, cinematic, no character movement other than breathing
and blinking.
```
用途：①共感／②物語のベースカット

### M2. 首をかしげる（考え中）
```
The character slowly tilts its head to one side with a curious, thoughtful
look, then holds the pose. It blinks once. Snow drifts down slowly.
The camera is static. Very slow and gentle motion.
```
用途：②の「どうしてだろうね」

### M3. ゆっくりズームイン（引き込み）
```
The character stays still, breathing softly and blinking. The camera slowly
and smoothly pushes in toward the character. Snow falls gently.
Very slow dolly-in, cinematic, no shake, no other motion.
```
用途：②の後半／③に入る直前

### M4. 光がふわっと強くなる（気づき）
```
The character stays still with a gentle smile. The lantern light beside it
slowly grows warmer and brighter, softly illuminating the character's face.
Snow falls gently. The camera is static. Very slow light change,
no flicker, no flash.
```
用途：③の「小さな考え方」を渡す瞬間
※ **点滅は禁止**。`no flicker, no flash` を必ず入れる

### M5. 羽をふわっと広げる（うれしい）
```
The character slowly spreads its two small wings outward in a gentle,
happy motion, then softly lowers them. Its eyes close in a warm smile.
Snow falls gently. The camera is static. Soft and slow motion, no jumping,
no flying.
```
用途：③〜④のポジティブな締め

### M6. 雪の結晶を空へ返す（締め・ブランドの象徴）
```
Tiny glowing snowflake crystals slowly rise from around the character and
float upward into the starry night sky, sparkling softly as they ascend.
The character looks up gently and watches them, then smiles.
The camera very slowly tilts upward. Magical, calm, dreamlike,
extremely slow motion, no fast particles, no flash.
```
用途：④の締め専用。**毎回同じ画にすることでブランド記号になる**

### M7. 手（羽）を振る（また会おうね）
```
The character gently raises one small wing and waves slowly twice,
with a warm closed-eye smile. Snow falls softly. The camera is static.
Slow, gentle, friendly motion. No jumping, no flying.
```
用途：④の最後

### M8. 窓辺・雨（落ち込んだ日）
```
The character sits still on the windowsill, breathing softly and blinking.
Raindrops slowly stream down the window glass behind it. Warm lamp light
glows steadily in the room. The camera is static. Calm, quiet,
very subtle motion.
```
用途：「雨の日もそばにいるよ」シーン

### M9. 暖炉のそば（あたたかい部屋）
```
The character sits still beside a fireplace, breathing softly and blinking
slowly. The fire flickers gently and warmly in the background. Steam rises
slowly from a mug beside the character. The camera is static.
Warm, cozy, extremely subtle motion.
```
※ 暖炉の炎は例外的に `flickers gently` を許可（背景で小さく、輝度変化は最小）

### M10. 眠り（おやすみ回・BGM動画用）
```
The character sits still with its eyes gently closed, breathing slowly and
deeply, its fluffy body rising and falling. Snow falls very slowly.
The moonlight is soft and steady. The camera is completely static.
Extremely slow, peaceful, loopable, no sudden motion.
```
用途：睡眠用BGM動画のループ素材。**ループ化しやすいよう動きを最小に**

---

## ネガティブプロンプト（毎回入れる）

```
fast motion, sudden movement, camera shake, zoom out, whip pan,
flying, jumping, running, spinning, dancing, walking,
talking, lip sync, mouth opening wide,
character turning around, back view, face distortion, morphing face,
extra limbs, extra eyes, deformed body, melting, warping,
scarf disappearing, color change, flickering light, flashing, strobe,
bright saturated colors, daylight, text, watermark, low quality, artifacts
```

---

## 1本の組み立て（32秒動画の例）

Klingの5秒クリップを組み合わせて、CapCutで繋ぐ。

| パート | 秒数 | 素材 | モーション |
|---|---|---|---|
| ① 共感 | 0:00-0:05 | 月明かりの森／おつかれさま… | **M1** |
| ② 物語 前半 | 0:05-0:12 | 月明かりの森／考え中… | **M2** |
| ② 物語 後半 | 0:12-0:20 | 月明かりの森／だいじょうぶだよ | **M3**（ズームイン） |
| ③ 考え方 | 0:20-0:28 | ランタンのそば／にっこり | **M4**（光が強くなる） |
| ④ 締め | 0:28-0:32 | 結晶が舞う空／うれしい！ | **M6 → M7** |

- **5秒クリップを必要に応じてスロー再生（0.8倍など）** して尺を伸ばす
  → 生成回数を減らせて、動きがさらにゆっくりになる（世界観的にプラス）
- 繋ぎは **クロスフェード 0.3〜0.5秒**。カット切り替えは使わない

---

## 生成コストを抑える運用

> ### ⚠️ 2026-08-19 撤回：「クリップの使い回し」はやめる
>
> 旧方針（同一クリップの使い回し・締めクリップの共通化・新規生成ゼロ）は、
> **YouTubeの「オリジナリティ不足／テンプレートの使い回し」に該当し、
> ショートフィードに載らない原因になっていた。**
>
> 003の視聴継続率は **10.7%**（目安50%以上）。以降の投稿は399→0→1と落ちた。
>
> **回ごとに映像を変える。** 制作コストは上がるが、
> 使い回した動画は配信されないので、コスト削減の意味がない。
> 詳細は [13. 拡散設計](13-viral-design.md#ショートフィードに載るための条件2026-08-19-外部指針と実測の照合)

### 新しい方針

- **1本ごとに、少なくとも1つは新規クリップを作る**
- **締めクリップも複数パターンを用意して回す**（完全な使い回しにしない）
- 素材ライブラリは「そのまま使う」ためではなく、**組み合わせの幅を持つため**に貯める
- **画面に動きをつける**：カットを3つに割る／字幕を動かす／雪の粒子を増やす
  → **ゆきみ自身は静かなままでよい。キャラの静けさと画面の動きは分離できる**

```
assets/video/
├── loops/     … シーン × 表情のバリエーション（組み合わせ元として使う）
├── endings/   … 締めクリップを複数パターン用意して回す
└── bg/        … ゆきみなしの背景ループ（雪・雨・炎）
```

### 採用チェック（Kling出力）
- [ ] マフラーが消えていない／色が変わっていない
- [ ] 顔が崩れていない（特にくちばしと目）
- [ ] 手足が生えていない
- [ ] 動きが速すぎない・カメラが揺れていない
- [ ] 光が点滅していない
- [ ] 全体を通して「静か」に見える

**1つでも欠けたら、その5秒は使わない。**

---

# ★ Veo 3.1 / Google Flow（2026-08-19 追加・こちらを主に使う）

出典：Veo 3.1 公式機能まとめ（ユーザー提供資料 2026-08-19）

## 使える新機能とゆきみへの当てはめ

| 機能 | ゆきみでどう使うか |
|---|---|
| **最初と最後のフレームを指定** | **同じキャラ画像を最初と最後の両方に入れる。** 間が補間されるので途中で別の鳥に変形できない。**キャラ崩れの最有力対策** |
| **複数画像から生成** | キャラ画像＋背景画像を同時に渡して世界観を固定する |
| **動画の延長（最後の1秒を起点に継ぎ足し）** | **8秒クリップの使い回しをやめられる。** 34秒を継ぎ目なしで作る。長尺化の土台にもなる |
| オブジェクトの追加 | 生成後に雪の結晶・星を足す |

## 得意・苦手（公式）

| | 内容 | ゆきみへの影響 |
|---|---|---|
| **得意** | 水・火・煙・**雪**・雨の物理表現 | **ゆきみの世界は雪。相性は最高** |
| **得意** | 環境音の生成 | 使わない（BGMは自前） |
| **苦手** | **アニメ系** | **イラスト寄りに崩さない。3Dぬいぐるみ質感のまま維持する** |
| **苦手** | **日本語の発話** | **Veoに喋らせない。声はElevenLabs一択** |

## クレジット（Flow）

| プラン | 月あたり |
|---|---|
| 無料 | 100 |
| Google AI Pro | 1,000 |
| Google AI Ultra | 25,000 |

**撮り直しでクレジットが減る。** プロンプトを毎回直すより、下の必須ブロックを固定で使う。

---

## ★ キャラ崩れ対策（実際に起きた事故と対処）

### 事故1：フクロウになった（2026-08-19）

耳のような羽（羽角）が生え、目つきが鋭くなった。
**原因：プロンプトに種類を書いていなかった。** Veoは「丸くて白い鳥」を学習量の多いフクロウとして解釈する。

### 事故2：勝手に声が入った（2026-08-19）

**原因：`as if speaking softly` と書いた。** Veo 3.1は音声を自動生成するため、
「話している」と書いた時点で音声を作りにいく。

### 事故3：天使の羽が生えた

**原因：羽の枚数を指定していなかった。**

### → 必須ブロック（毎回そのまま入れる）

```
SPECIES - important:
This is a long-tailed tit (shima-enaga), a small round white songbird.
It is NOT an owl.
- no ear tufts, no horns, no feather tufts on the head
- the head is completely round and smooth
- small triangular black beak
- it has a long straight tail behind the body

APPEARANCE LOCK - do not change:
- same body shape, proportions and size as the reference image
- large round warm amber orange eyes with a bright black catchlight
- same light blue knitted scarf with the snowflake pattern
- exactly two wings only, one on each side, both folded against the body
- no extra wing, no wing above or behind the head
- do not change any color
- keep the 3D plush texture, do not turn it into anime or 2D illustration

AUDIO:
Silent. No voice, no speech, no dialogue, no narration, no music, no sound effects.
```

### 書いてはいけない語

```
❌ as if speaking / talking / lip sync   → 音声が生成される
❌ anime / illustration / 2D             → Veoの苦手分野に入る
❌ don't move / stay completely still    → 全部止まって静止画になる
```

**「動かさないで」ではなく「この動きだけして」と書く。**

---

## 推奨の作り方（34秒の台本を1本で作る）

```
1. 最初のフレーム＝キャラ画像
2. 最後のフレーム＝同じキャラ画像      ← ここが崩れ対策
3. 8秒を生成する
4. 「動画の延長」で最後の1秒から継ぎ足す（×3〜4回）
5. 34秒まで伸ばす
6. CapCutでElevenLabsの音声と字幕を乗せる
```

**クリップの使い回しはしない。** 延長機能があるので不要になった。
