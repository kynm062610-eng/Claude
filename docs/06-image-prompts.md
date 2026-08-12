# 06. 画像生成プロンプト

**最大の課題はキャラクターの一貫性。**
毎回ゼロから作らず、「固定ブロック＋可変ブロック」の組み立て方式で作る。

---

## 構造

```
[① キャラ固定ブロック]  ← 絶対に変えない
      +
[② シーンブロック]      ← 4つの定番から選ぶ
      +
[③ 表情・ポーズ]        ← 7種から選ぶ
      +
[④ 品質・構図ブロック]  ← 絶対に変えない
      +
[⑤ ネガティブ]          ← 絶対に変えない
```

---

## ① キャラ固定ブロック（変更禁止・毎回コピペ）

```
A super cute chibi long-tailed tit (shima-enaga) fairy character named Yukimi,
perfectly round fluffy snow-white body, soft downy feather texture,
large sparkling black eyes with bright catchlights,
tiny black triangular beak, soft pink round blush on cheeks,
grey and white speckled wings, long black-and-grey tail,
wearing a light blue knitted scarf with an embroidered snowflake and fringed ends,
3D render style, soft plush toy aesthetic, gentle and kind expression
```

**日本語メモ**：まるい／白い／ふわふわ／大きな黒い目に光／小さな黒いくちばし／ピンクのチーク／グレーの斑の翼／**水色マフラー（雪の結晶刺繍）** ← マフラーは絶対に外さない

---

## ② シーンブロック（4定番）

### A. あたたかい部屋で
```
sitting on a wooden table inside a cozy cabin at night,
a lit fireplace glowing warm orange in the background,
a steaming mug of cocoa beside, soft bokeh, warm firelight from the side
```

### B. 月明かりの森で
```
perched on a snow-covered branch in a quiet winter forest at night,
crescent moon and stars in a deep navy sky, gentle snowfall,
soft blue moonlight, distant snowy pine trees in bokeh
```

### C. そっと話を聞くよ
```
sitting in the snow beside a small antique lantern glowing warm amber,
deep navy night background, softly falling snow,
warm rim light from the lantern on the left
```

### D. 雨の日もそばにいるよ
```
sitting on a windowsill indoors at night, rain streaming down the glass outside,
warm orange lamp light inside the room, cool blue light outside,
soft reflections on the window
```

### 拡張：結晶を返す（締め用）
```
looking up at the night sky, tiny glowing snowflake crystals floating upward
from around the character into a starry navy sky, magical soft sparkles
```

---

## ③ 表情・ポーズ

| 表情 | プロンプト断片 |
|---|---|
| 通常 | `calm gentle expression, looking softly at the viewer` |
| にっこり | `happy closed smiling eyes (^ ^ shape), cheerful warm smile` |
| びっくり | `wide round surprised eyes, small open beak, slightly tilted head` |
| 考え中… | `looking up thoughtfully to the side, head tilted, one wing near the beak` |
| うれしい！ | `both small wings spread out joyfully, bright happy closed-eye smile` |
| おつかれさま… | `eyes gently closed, soft peaceful smile, slightly lowered head` |
| だいじょうぶだよ | `calm reassuring gaze at the viewer, soft warm smile, one wing slightly raised` |

---

## ④ 品質・構図ブロック（変更禁止）

### 縦動画用（9:16）
```
vertical 9:16 composition, character centered slightly below the middle,
generous empty space above, cinematic soft lighting, shallow depth of field,
warm and cool color contrast, muted low-saturation palette,
color palette: snow white #FFFFFF, soft light blue #B8D4E8, deep night navy #1B2A4A,
warm orange #F0B96B, gentle pink #F5C6C6, forest grey-green #8FA396,
highly detailed, soft focus background, healing and calm atmosphere,
professional 3D character render, 8k
```

### サムネ／正方形用（1:1）
`vertical 9:16 composition, character centered slightly below the middle, generous empty space above,` を
`square 1:1 composition, character centered,` に差し替え。

---

## ⑤ ネガティブプロンプト（変更禁止）

```
scary, creepy, angry, crying, sad face, aggressive, sharp teeth,
human hands, human arms, human legs, anthropomorphic body,
realistic bird, photorealistic animal, feathers too detailed, ugly,
multiple characters, extra limbs, extra eyes, deformed, distorted,
text, watermark, signature, logo, letters,
bright saturated colors, neon, red background, white background,
daylight, harsh lighting, high contrast, flat lighting,
busy background, cluttered, low quality, blurry, jpeg artifacts,
no scarf, missing scarf, red scarf, green scarf
```

---

## 組み立て例（完成形）

**用途：#21「返信が来ない夜」の①共感カット**

```
A super cute chibi long-tailed tit (shima-enaga) fairy character named Yukimi,
perfectly round fluffy snow-white body, soft downy feather texture,
large sparkling black eyes with bright catchlights, tiny black triangular beak,
soft pink round blush on cheeks, grey and white speckled wings,
long black-and-grey tail, wearing a light blue knitted scarf with an embroidered
snowflake and fringed ends, 3D render style, soft plush toy aesthetic,
--
perched on a snow-covered branch in a quiet winter forest at night,
crescent moon and stars in a deep navy sky, gentle snowfall, soft blue moonlight,
distant snowy pine trees in bokeh,
--
eyes gently closed, soft peaceful smile, slightly lowered head,
--
vertical 9:16 composition, character centered slightly below the middle,
generous empty space above, cinematic soft lighting, shallow depth of field,
muted low-saturation palette, color palette: snow white, soft light blue,
deep night navy, warm orange, gentle pink, forest grey-green,
highly detailed, soft focus background, healing and calm atmosphere,
professional 3D character render, 8k

Negative: scary, creepy, angry, crying, human hands, realistic bird, multiple
characters, extra limbs, deformed, text, watermark, bright saturated colors,
daylight, white background, busy background, low quality, no scarf, red scarf
```

*(`--` は説明用の区切り。実際は改行かカンマで繋げて1本の文字列として入力する)*

---

## 一貫性を上げる運用

### 1. シードを固定する
うまくいったカットのシード値を記録し、同じシリーズでは再利用する。
記録先：`assets/generated/seeds.md`

```markdown
| 用途 | シーン | シード | 生成日 | メモ |
|---|---|---|---|---|
| 基準ポーズ | 月明かりの森 | 384729184 | 2026-08-07 | マフラーの結び目がきれい |
```

### 2. 参照画像を必ず使う
[キャラクターシート](../assets/reference/yukimi-character-sheet.png) を
image-to-image / character reference として入力する。
- 参照の強さ：**0.6〜0.75** が目安（強すぎるとポーズが変わらない、弱いと別人になる）

### 3. 素材ライブラリを作る
1本ごとに生成し直さない。**使い回せる素材を貯める。**

```
assets/generated/
├── base/          … 表情7種 × シーン4種 = 28枚の基本カット
├── scenes/        … 背景のみ（ゆきみなし）
├── endings/       … 結晶が舞い上がる締めカット
└── seeds.md       … シード記録
```

基本28枚が揃えば、多くの動画は**生成なしで組める。**

### 4. 採用前チェック
[02. キャラクターバイブル](02-character-bible.md#キャラクター一貫性チェック毎回確認) の
9項目チェックを全部通す。1つでも欠けたら不採用。

---

## サムネイル用プロンプト

サムネはゆきみを大きく、余白に文字を入れる場所を残す。

```
[キャラ固定ブロック]
+ close-up portrait, character fills the left half of the frame,
  large empty dark navy space on the right for text,
  [シーンブロック] + [表情]
+ [品質ブロック]
```

**文字はプロンプトに入れず、編集ソフトで乗せる**（AI生成の文字は崩れる）。
