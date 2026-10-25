# amity-ameblo-daily

Amity のアメブロ用収益記事を毎日1本作って保存するリポジトリ（非公開）。アメブロへの自動投稿はしません。

- 記事: `posts/YYYY-MM-DD/article.html`（アメブロの「HTML表示」に貼る本文）、`meta.json`（タイトル・テーマ・使った商品）
- iPhoneでのコピー: 毎日更新されるコピー用ページ（URLは `data/copy_page.json`）。開けないときは GitHub アプリで `posts/日付/article.html` → 右上「…」→ Copy
- テーマの履歴: `data/theme_history.csv`　失敗の記録: `logs/failures.md`
- 商品リンク: `data/affiliate_links.json`（登録したものだけ使う）
- 収益の記録: `data/performance.csv` に月ごとのクリック数・収益を記入すると、テーマ選びに使います
- 見本の追加: `samples/README.md`
- 毎日の手順: `CLAUDE.md`
