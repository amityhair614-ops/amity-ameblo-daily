# HTML 装飾のルール

※暫定版。ChatGPTで作ったHTML見本（samples/html/）の分析後に色・余白を合わせる。

- 部品は templates/components.html のものだけを使う。部品の style は変えない
- インラインCSSのみ。`<style>`・`class`・`id`・`<script>`・`<iframe>`・`position`・`flex`・`grid` は使わない
- 大見出し：グリーンの帯。小見出し：左にグリーンの線
- 重要ポイント：淡いグリーンの囲み。注意点：淡い赤の囲み。商品紹介：淡いブルーの囲み
- 比較表は3列まで（スマホで横にはみ出さないため）。Q&A は Q と A の色を分ける
- 段落は2〜3文ごとに区切る。1つの囲みに詰め込みすぎない
- 商品リンクには rel="nofollow sponsored" を付ける
