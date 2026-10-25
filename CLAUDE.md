# amity-ameblo-daily

Amity（美容室）のアメブロ用収益記事を、毎日1本だけ新しく作るリポジトリ。

## 守ること
- 扱うのはこのリポジトリだけ。note・WordPress・動画編集など他のリポジトリには触れない
- アメブロへのログイン・投稿はしない。有料API・外部サービスは使わない
- 新規記事のみ。過去記事の書き直しや、既存の posts/ の上書きはしない
- リンクは data/affiliate_links.json と rules/profile.json に登録されたものだけ。作成・変更しない
- 商品名・価格・効能・実体験・お客様の声・受賞歴を作らない
- 定期タスクの作成・変更・削除はしない。rules/・scripts/・templates/・CLAUDE.md は変更しない（本人の指示があるときを除く）

## 毎日の手順
1. 日付は日本時間: `DATE=$(TZ=Asia/Tokyo date +%F)`。posts/$DATE/ が既にあれば何も作らずに終了し「既に存在するため作成しなかった」と報告する
2. 次を読み直す: rules/writing_rules.md、rules/html_style.md、rules/style_analysis.md、rules/profile.json、templates/components.html、data/affiliate_links.json、data/theme_pool.md、data/theme_history.csv、data/performance.csv、samples/ の見本
3. テーマを1つ選ぶ（下の「テーマの選び方」）。`python3 scripts/pick_theme.py` の上位から検討する
4. 記事を書く（rules/writing_rules.md の構成どおり）。HTMLは templates/components.html の部品だけで組み立てる
5. posts/$DATE/article.html（アメブロに貼る本文HTML）と posts/$DATE/meta.json を作る
   - meta.json: `{"date","title","theme","main_keyword","category","search_intent","affiliate_ids":[],"sub_keywords":[]}`
6. `python3 scripts/check_post.py $DATE` が OK になるまで直す。NG のまま保存しない
7. iPhoneの幅（390px）で表示を確認する: `node scripts/render_check.mjs $DATE` で画像を作り、Read で開いて崩れ・はみ出しがないかを目で見る
8. data/theme_history.csv に1行追加する（status は `created`）
9. `python3 scripts/build_copy_page.py` で copy/index.html を作り直す
10. コミットして main に push する（force push・rebase・amend はしない。拒否されたら `git pull --no-rebase origin main` してから再 push。ネットワークエラーは 2・4・8・16秒待って最大4回）
11. コピー用ページを更新する: data/copy_page.json の url を Artifact の read で読み、copy/index.html をその url に publish する（新しい url を作らない）
12. origin/main に posts/$DATE/article.html と meta.json があることを確認できたときだけ「成功」と報告する（タイトル・テーマ・使った商品・コピー用ページのURL）

## 失敗したとき
- 途中で止まったら logs/failures.md に「日付・止まった手順・理由」を追記して push し、「失敗」と報告する
- main に push できなかったときだけ daily/$DATE ブランチに push する

## テーマの選び方
- data/theme_pool.md から、theme_history.csv で未使用のキーワードを選ぶ（status が published の行はアメブロに公開済みの記事。created と同じく使用済みとして扱う）
- `scripts/pick_theme.py` が「過去記事に近い」と出したテーマは、使うなら対象（年代・髪質・場面）か切り口を変え、meta.json の theme にその違いを書く
- 直近7本と同じカテゴリ（ショート・ボブ・白髪・くせ毛・ダメージ・シャンプー・トリートメント・ドライヤー・頭皮 等）が3本以上なら、別のカテゴリにする
- 過去記事と同じ悩み・同じ結論にしない。近いテーマのときは、対象（年代・髪質・場面）か切り口を変える
- data/performance.csv にクリック・収益の記録があれば、反応の良かったカテゴリと商品の組み合わせを優先する（同じ記事の焼き直しにはしない）
- theme_pool の未使用が10個を切ったら、報告の最後に「テーマの追加が必要」と書く
