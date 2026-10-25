#!/usr/bin/env python3
"""アメブロ記事の自動チェック。

使い方: python3 scripts/check_post.py YYYY-MM-DD
NG が1つでもあれば終了コード1。NG のまま保存しない。
"""
import csv
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_WORDS = ["僕は", "思います", "候補", "先日お客様", "お客様から", "実際に使って"]
# アメブロの HTML 編集で使えるタグだけ
ALLOWED_TAGS = {
    "div", "p", "span", "strong", "b", "em", "br", "hr", "h2", "h3", "h4",
    "table", "thead", "tbody", "tr", "th", "td", "a", "ul", "ol", "li", "img",
}
VOID_TAGS = {"br", "hr", "img"}
ALLOWED_ATTRS = {"style", "href", "target", "rel", "src", "alt", "width", "height", "colspan", "rowspan"}
FORBIDDEN_CSS = ["position", "@media", "javascript:", "expression(", "url(", "display:flex", "display: flex", "grid"]
# 広告表示・購入誘導は自動生成HTMLに入れない（本人が投稿時にアメブロで設定する）
AD_LABEL = re.compile(r"((?<![A-Za-z])PR(?![A-Za-z])|広告|アフィリエイト)")
CTA_WORDS = ["で見る", "商品ページ", "詳細を見る", "詳しく見る", "購入はこちら", "こちらから購入", "購入する", "チェックする▶", "▶"]
PRICE = re.compile(r"[0-9０-９,，]+\s*円")
MIN_CHARS, MAX_CHARS = 2500, 7000
MAX_SAME_PRODUCT = 3
TITLE_SIMILARITY_LIMIT = 0.5
REQUIRED_TEXT = ["よくある質問", "まとめ"]
# 話し言葉のリズム（rules/writing_rules.md「話し言葉のリズム」）
DESU_MASU = re.compile(r"(です|ます|ません|ました|でしょう)。$")
MAX_DESU_RATIO = 0.5
MAX_DESU_RUN = 6
MIN_EXCLAIM, MIN_QUESTION = 8, 6


class Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.errors, self.stack, self.hrefs, self.srcs, self.text = [], [], [], [], []
        self.tags = []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            self.errors.append(f"使えないタグ <{tag}>")
        for name, value in attrs:
            if name not in ALLOWED_ATTRS:
                self.errors.append(f"使えない属性 {name}= （<{tag}>）")
            if name == "style":
                low = (value or "").lower()
                for bad in FORBIDDEN_CSS:
                    if bad in low:
                        self.errors.append(f"使えないCSS「{bad}」（<{tag}>）")
            if name == "href":
                self.hrefs.append(value or "")
            if name == "src":
                self.srcs.append(value or "")
        self.tags.append(tag)
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS and self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"タグの閉じ忘れ・順番違い </{tag}>（開いているタグ: {self.stack[-3:]}）")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
            return
        self.stack.pop()

    def handle_data(self, data):
        self.text.append(data)


def bigrams(s):
    s = re.sub(r"[\s【】「」『』！？!?、。・｜|]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def similarity(a, b):
    x, y = bigrams(a), bigrams(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def rhythm(text):
    """文末の偏りを調べる。です・ます止めばかりの説明書のような文章を NG にする"""
    ng, warn = [], []
    parts = re.split(r"(?<=[。！？!?])", text)
    sentences = [x.strip() for x in parts if len(x.strip()) >= 4 and x.strip()[-1] in "。！？!?"]
    if not sentences:
        return ng, warn
    run = longest = 0
    for x in sentences:
        run = run + 1 if DESU_MASU.search(x) else 0
        longest = max(longest, run)
    ratio = sum(bool(DESU_MASU.search(x)) for x in sentences) / len(sentences)
    exclaim = sum(x[-1] in "！!" for x in sentences)
    question = sum(x[-1] in "？?" for x in sentences)
    if ratio >= MAX_DESU_RATIO:
        ng.append(f"「です・ます」で終わる文が {ratio:.0%}（半分未満にする。言い切り・体言止め・問いかけを混ぜる）")
    elif ratio >= 0.45:
        warn.append(f"「です・ます」で終わる文が {ratio:.0%}（やや多い）")
    if longest >= MAX_DESU_RUN:
        ng.append(f"「です・ます」で終わる文が {longest} 文続く箇所がある（{MAX_DESU_RUN - 1} 文まで）")
    if exclaim < MIN_EXCLAIM:
        ng.append(f"「！」で終わる文が {exclaim} 個（{MIN_EXCLAIM} 個以上。「〜なんです！」「〜ですよ！」など）")
    if question < MIN_QUESTION:
        ng.append(f"「？」で終わる文が {question} 個（{MIN_QUESTION} 個以上。読者への問いかけを入れる）")
    return ng, warn


def load_products():
    return json.loads((ROOT / "data/affiliate_links.json").read_text(encoding="utf-8")).get("links", [])


def load_history(date):
    """比べる過去記事。この日の自分の行（status=created）だけ除く"""
    path = ROOT / "data/theme_history.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [row for row in csv.DictReader(f)
                if not (row.get("date") == date and row.get("status") == "created")]


def check(date):
    ng, warn = [], []
    post = ROOT / "posts" / date
    html_path, meta_path = post / "article.html", post / "meta.json"
    if not html_path.exists() or not meta_path.exists():
        return [f"{post} に article.html と meta.json の両方が必要"], warn

    html = html_path.read_text(encoding="utf-8")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for key in ["date", "title", "theme", "main_keyword", "category", "affiliate_ids"]:
        if key not in meta:
            ng.append(f"meta.json に {key} がない")
    if meta.get("date") != date:
        ng.append("meta.json の date がフォルダ名と違う")

    parser = Collector()
    parser.feed(html)
    parser.close()
    ng += parser.errors
    if parser.stack:
        ng.append(f"閉じていないタグ: {parser.stack}")
    text = "".join(parser.text)

    for word in FORBIDDEN_WORDS:
        if word in text or word in meta.get("title", ""):
            ng.append(f"使わない言葉「{word}」がある")
    r_ng, r_warn = rhythm(text)
    ng += r_ng
    warn += r_warn
    n = len(re.sub(r"\s", "", text))
    if not MIN_CHARS <= n <= MAX_CHARS:
        ng.append(f"本文 {n} 字（{MIN_CHARS}〜{MAX_CHARS} 字にする）")
    for need in REQUIRED_TEXT:
        if need not in text:
            ng.append(f"「{need}」の見出しがない")
    if PRICE.search(text):
        ng.append(f"価格の記載がある（「{PRICE.search(text).group()}」）。価格はリンク先で確認と書く")

    profile = json.loads((ROOT / "rules/profile.json").read_text(encoding="utf-8"))
    site = {u for u in profile.get("allowed_urls", []) if u}
    images = set(profile.get("allowed_images", []))
    for src in parser.srcs:
        if src not in images:
            ng.append(f"登録されていない画像: {src}")
    if parser.tags.count("h2") != 1:
        ng.append(f"大見出し h2 は1つだけ（今 {parser.tags.count('h2')} 個）")

    # リンクは LINE・店舗・Instagram だけ。商品リンク（アフィリエイトURL）は入れない
    products = load_products()
    affiliate = {item["url"] for item in products}
    for href in parser.hrefs:
        if href in affiliate or "odsyms15" in href:
            ng.append(f"アフィリエイトURLが入っている（投稿時に本人が設定する）: {href}")
        elif href not in site:
            ng.append(f"登録されていないリンク: {href}")
    for key in ["line_url", "instagram_url"]:
        url = profile.get(key)
        if url and url not in parser.hrefs:
            ng.append(f"{key} の案内リンクがない")
    m = AD_LABEL.search(text)
    if m:
        ng.append(f"広告表示「{m.group()}」がある（自動生成HTMLには入れない）")
    for word in CTA_WORDS:
        if word in text:
            ng.append(f"購入への誘導文「{word}」がある（商品は名前だけ）")

    # 商品は display_name で名前だけ。meta.json の affiliate_ids と一致させる
    named = {item["id"]: text.count(item["display_name"]) for item in products if item["display_name"] in text}
    for pid, count in named.items():
        if count > MAX_SAME_PRODUCT:
            ng.append(f"商品名「{pid}」が {count} 回（{MAX_SAME_PRODUCT} 回まで）")
    if set(named) != set(meta.get("affiliate_ids", [])):
        ng.append(f"meta.json の affiliate_ids が本文の商品名と一致しない（本文: {sorted(named)}）")

    for row in load_history(date):
        if row.get("main_keyword") and row["main_keyword"] == meta.get("main_keyword"):
            ng.append(f"メインキーワード「{row['main_keyword']}」は {row['date']} に使用済み")
        t = similarity(row.get("theme", ""), meta.get("theme", ""))
        if t >= TITLE_SIMILARITY_LIMIT:
            ng.append(f"テーマが {row['date']}「{row['theme']}」と似すぎ（{t:.2f}）")
        s = similarity(row.get("title", ""), meta.get("title", ""))
        if s >= TITLE_SIMILARITY_LIMIT:
            ng.append(f"タイトルが {row['date']}「{row['title']}」と似すぎ（{s:.2f}）")
        elif s >= 0.35:
            warn.append(f"タイトルが {row['date']}「{row['title']}」とやや近い（{s:.2f}）")
    title_len = len(meta.get("title", ""))
    if not 20 <= title_len <= 45:
        warn.append(f"タイトル {title_len} 字（20〜45字が目安）")
    return ng, warn


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", sys.argv[1]):
        print("使い方: python3 scripts/check_post.py YYYY-MM-DD")
        sys.exit(2)
    ng, warn = check(sys.argv[1])
    for w in warn:
        print("注意:", w)
    for e in ng:
        print("NG:", e)
    print("OK" if not ng else f"NG {len(ng)} 件")
    sys.exit(1 if ng else 0)


if __name__ == "__main__":
    main()
