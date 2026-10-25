#!/usr/bin/env python3
"""iPhone からコピーするためのページ copy/index.html を作る。

使い方: python3 scripts/build_copy_page.py
posts/ の新しい順に最大7本を載せる。1本目が最新。
"""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEEP = 7

# Artifact に publish するため <!doctype>・<html>・<head>・<body> は書かない（公開時に付く）
PAGE = """<title>アメブロ記事コピー</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="claude:viewport-fit-sides" content="cover">
<style>
:root {{ --bg:#f6f8f6; --card:#fff; --text:#1f2a24; --sub:#5d6b63; --line:#d9e3dc; --accent:#2e7d4f; --accent-text:#fff; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#121714; --card:#1b221e; --text:#e6ece8; --sub:#9fb0a6; --line:#2c3a32; --accent:#4caf7a; --accent-text:#08140d; color-scheme:dark; }} }}
:root[data-theme="dark"] {{ --bg:#121714; --card:#1b221e; --text:#e6ece8; --sub:#9fb0a6; --line:#2c3a32; --accent:#4caf7a; --accent-text:#08140d; color-scheme:dark; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,"Hiragino Sans",sans-serif; }}
main {{ max-width:720px; margin:0 auto; padding-block:16px; padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px)); }}
h1 {{ font-size:18px; margin:4px 0 12px; }}
select {{ width:100%; font-size:16px; padding:10px; border:1px solid var(--line); border-radius:10px; background:var(--card); color:var(--text); }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px; margin-top:12px; }}
.title {{ font-weight:700; font-size:16px; line-height:1.5; }}
.meta {{ color:var(--sub); font-size:13px; margin-top:4px; }}
button {{ width:100%; font-size:17px; font-weight:700; padding:14px; margin-top:10px; border:0; border-radius:12px; background:var(--accent); color:var(--accent-text); }}
button.sub {{ background:transparent; color:var(--accent); border:1px solid var(--accent); }}
textarea {{ width:100%; height:120px; font-size:12px; margin-top:10px; border:1px solid var(--line); border-radius:10px; padding:8px; background:var(--bg); color:var(--text); }}
.msg {{ text-align:center; font-size:14px; min-height:20px; margin-top:8px; color:var(--accent); }}
.preview {{ background:#fff; color:#333; border-radius:10px; padding:12px; margin-top:12px; overflow-x:auto; }}
details summary {{ cursor:pointer; color:var(--sub); font-size:14px; }}
</style>
<main>
<h1>アメブロ記事コピー</h1>
<select id="pick"></select>
<div class="card">
  <div class="title" id="t"></div>
  <div class="meta" id="m"></div>
  <button id="copyTitle" class="sub">タイトルをコピー</button>
  <button id="copyHtml">本文HTMLをコピー</button>
  <div class="msg" id="msg"></div>
  <textarea id="src" readonly></textarea>
</div>
<div class="card">
  <details><summary>表示の確認（プレビュー）</summary><div class="preview" id="pv"></div></details>
</div>
<p class="meta">アメブロの「HTML表示」に切り替えてから貼り付けてください。</p>
</main>
<script>
const POSTS = {posts};
const $ = id => document.getElementById(id);
POSTS.forEach((p, i) => {{ const o = document.createElement('option'); o.value = i; o.textContent = p.date + (i === 0 ? '（最新）' : '') + '　' + p.title; $('pick').appendChild(o); }});
function show(i) {{ const p = POSTS[i]; $('t').textContent = p.title; $('m').textContent = p.date + '・' + p.theme; $('src').value = p.html; $('pv').innerHTML = p.html; $('msg').textContent = ''; }}
async function copy(text, label) {{
  try {{ await navigator.clipboard.writeText(text); $('msg').textContent = label + 'をコピーしました'; return; }} catch (e) {{}}
  const ta = $('src'); const keep = ta.value; ta.value = text; ta.focus(); ta.select(); ta.setSelectionRange(0, text.length);
  let ok = false; try {{ ok = document.execCommand('copy'); }} catch (e) {{}}
  ta.value = keep;
  $('msg').textContent = ok ? label + 'をコピーしました' : '自動コピーできませんでした。下の欄を長押し→「すべてを選択」→「コピー」してください';
  if (!ok) {{ ta.focus(); ta.select(); }}
}}
$('pick').onchange = e => show(+e.target.value);
$('copyHtml').onclick = () => copy(POSTS[+$('pick').value].html, '本文HTML');
$('copyTitle').onclick = () => copy(POSTS[+$('pick').value].title, 'タイトル');
if (POSTS.length) show(0); else $('t').textContent = 'まだ記事がありません';
</script>
"""


def main():
    posts = []
    for d in sorted((ROOT / "posts").iterdir(), reverse=True):
        a, m = d / "article.html", d / "meta.json"
        if a.exists() and m.exists():
            meta = json.loads(m.read_text(encoding="utf-8"))
            posts.append({"date": meta["date"], "title": meta["title"], "theme": meta["theme"],
                          "html": a.read_text(encoding="utf-8").strip()})
        if len(posts) == KEEP:
            break
    data = json.dumps(posts, ensure_ascii=False).replace("</", "<\\/")
    out = ROOT / "copy/index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(PAGE.format(posts=data), encoding="utf-8")
    print(f"{out} に {len(posts)} 本を書き出し")


if __name__ == "__main__":
    main()
