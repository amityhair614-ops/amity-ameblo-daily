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
MAX_SAME_PRODUCT = 1        # 同じ商品名は記事内で1回だけ
MIN_PRODUCTS, MAX_PRODUCTS = 1, 2  # 1記事1商品以上、多くて2商品（rules/writing_rules.md「商品の紹介」）
# 年代は書かない（rules/writing_rules.md「年代を書かない」）
AGE = re.compile(r"[0-9０-９]+\s*代|年齢を重ね|年齢とともに|加齢|アラサー|アラフォー|アラフィフ")
TITLE_SIMILARITY_LIMIT = 0.5
REQUIRED_TEXT = ["よくある質問", "まとめ"]
# 話し言葉のリズム（rules/writing_rules.md「文体の基準」）
DESU_MASU = re.compile(r"(です|ます|ません|ました|でしょう)。$")
MAX_DESU_RATIO = 0.7
MAX_DESU_RUN = 7
MAX_SAME_ENDING_RUN = 4      # 同じ語尾が続く上限（この数で NG）
MAX_EXCLAIM_RUN = 3          # 「！」で終わる文が続く上限（この数で NG）
MAX_EXCLAIM_RATIO = 0.2      # 「！」で終わる文の割合の上限
MAX_HABIT = 6                # 口ぐせ1つあたりの上限
HABITS = ["なんです", "ですよね", "ですよ", "んですよ"]
SAME_LENGTH_RUN, SAME_LENGTH_DIFF = 5, 4
# 読みやすさ（rules/writing_rules.md「文体の基準」）
MAX_COMMAS_IN_SENTENCE = 3   # この数で NG
MAX_SENTENCE_LEN = 50        # これを超えると NG
MAX_COMMA_AVG = 0.35         # 1文あたりの読点の平均（2026-10-30 に 0.5 から下げた。目安は 0.3 以下）
WARN_COMMA_AVG = 0.3
WARN_TWO_COMMAS, WARN_LONG_LEN, WARN_LONG_COUNT = 1, 40, 4
MAX_SENTENCES_IN_PARAGRAPH = 2
SHORT_LINE = 15              # 体言止めを3行並べる段落は、各文がこの字数以下なら可
HARD_WORDS = ["重要", "適切", "推奨", "となります", "において", "該当", "する必要があります", "することができます",
              "を行う", "を行い", "実施", "傾向があります", "可能です",
              "印象", "調整", "量感", "輪郭", "維持", "状態"]
BLOCK_TAGS = {"p", "div", "h2", "h3", "h4", "table", "tr", "td", "th", "li", "ul", "ol"}
# 長いものから順に判定する
ENDINGS = ["なんです", "んですよね", "んですよ", "んです", "ですよね", "ですよ", "ですね", "ますよね", "ますよ", "ますね",
           "ましょう", "でしょう", "ません", "ました", "です", "ます", "ください"]


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


def ending(sentence):
    """文末の形（「なんです」「ですよね」など）。決まった形でなければ最後の2字"""
    body = sentence.rstrip("。！？!?")
    for e in ENDINGS:
        if body.endswith(e):
            return e
    return body[-2:]


def longest_run(items, same):
    run = best = 0
    prev = None
    for x in items:
        run = run + 1 if prev is not None and same(prev, x) else 1
        best, prev = max(best, run), x
    return best


def rhythm(text):
    """単調さと不自然な繰り返しを調べる。記号の最低回数は決めない"""
    ng, warn = [], []
    parts = re.split(r"(?<=[。！？!?])", text)
    sentences = [x.strip() for x in parts if len(x.strip()) >= 4 and x.strip()[-1] in "。！？!?"]
    if not sentences:
        return ng, warn
    total = len(sentences)

    # です・ます止めばかりの説明書のような文章
    desu = [bool(DESU_MASU.search(x)) for x in sentences]
    ratio = sum(desu) / total
    # 注意として表示するだけ。数を合わせるために文を不自然に切らない（rules/writing_rules.md「文体の基準」）
    if ratio >= MAX_DESU_RATIO:
        warn.append(f"「です・ます」で終わる文が {ratio:.0%}（説明調が続いていないか読み直す）")
    run = longest_run(desu, lambda a, b: a and b) if any(desu) else 0
    if run >= MAX_DESU_RUN:
        warn.append(f"「です・ます」で終わる文が {run} 文続く箇所がある（説明調が続いていないか読み直す）")

    # 同じ語尾の連続（「〜なんです。〜なんです。〜なんです。」など）
    ends = [ending(x) for x in sentences]
    run = longest_run(ends, lambda a, b: a == b)
    if run >= MAX_SAME_ENDING_RUN:
        word = next(e for i, e in enumerate(ends) if longest_run(ends[i:i + run], lambda a, b: a == b) == run)
        ng.append(f"同じ語尾「{word}」が {run} 文続く箇所がある（{MAX_SAME_ENDING_RUN - 1} 文まで）")

    # 「！」の多用
    excl = [x[-1] in "！!" for x in sentences]
    run = longest_run(excl, lambda a, b: a and b) if any(excl) else 0
    if run >= MAX_EXCLAIM_RUN:
        ng.append(f"「！」で終わる文が {run} 文続く箇所がある（{MAX_EXCLAIM_RUN - 1} 文まで。「！」は必要なところだけ）")
    if sum(excl) / total > MAX_EXCLAIM_RATIO:
        ng.append(f"「！」で終わる文が {sum(excl) / total:.0%}（2割まで。「！」は必要なところだけ）")

    # 口ぐせの使いすぎ
    for habit in HABITS:
        count = sum(ending(x) == habit for x in sentences)
        if count > MAX_HABIT:
            ng.append(f"語尾「〜{habit}」が {count} 回（{MAX_HABIT} 回まで。言い回しを変える）")

    # 長さがそろった文の連続
    lengths = [len(x) for x in sentences]
    for i in range(total - SAME_LENGTH_RUN + 1):
        window = lengths[i:i + SAME_LENGTH_RUN]
        if max(window) - min(window) <= SAME_LENGTH_DIFF:
            warn.append(f"長さがほぼ同じ文が {SAME_LENGTH_RUN} 文続く（「{sentences[i][:12]}…」から）")
            break
    return ng, warn


class Paragraphs(HTMLParser):
    """包みの div の直下の並び（段落・空行・枠や見出し）と、改行で区切ったテキストを集める"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.items = []          # ("p", テキスト) / ("blank", "") / ("block", タグ名)
        self.current = None
        self.lines = []

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK_TAGS or tag == "br":
            self.lines.append("\n")
        if tag == "br":
            return
        if tag in ("img", "hr"):
            return
        if self.depth == 1:
            if tag == "p":
                self.current = []
            else:
                self.items.append(("block", tag))
        self.depth += 1

    def handle_endtag(self, tag):
        if tag in BLOCK_TAGS:
            self.lines.append("\n")
        if tag in ("br", "img", "hr"):
            return
        self.depth -= 1
        if self.depth == 1 and tag == "p" and self.current is not None:
            body = "".join(self.current).strip()
            self.items.append(("p", body) if body else ("blank", ""))
            self.current = None

    def handle_data(self, data):
        self.lines.append(data)
        if self.current is not None:
            self.current.append(data)


def split_sentences(text):
    out = []
    for line in text.split("\n"):
        for x in re.split(r"(?<=[。！？!?])", line):
            x = x.strip()
            if len(x) >= 4 and x[-1] in "。！？!?":
                out.append(x)
    return out


def readability(html):
    """読点・文の長さ・段落と空行・硬い言葉を調べる（末尾の LINE・店舗は除く）"""
    ng, warn = [], []
    body = html.split("LINEにてご予約")[0]
    parser = Paragraphs()
    parser.feed(body)
    sentences = split_sentences("".join(parser.lines))
    if not sentences:
        return ng, warn

    commas = [x.count("、") for x in sentences]
    for x, c in zip(sentences, commas):
        if c >= MAX_COMMAS_IN_SENTENCE:
            ng.append(f"読点が {c} 個の文（「。」で分ける）: {x}")
        if len(x) > MAX_SENTENCE_LEN:
            ng.append(f"{len(x)} 字の長い文（分ける）: {x}")
    avg = sum(commas) / len(sentences)
    if avg > MAX_COMMA_AVG:
        ng.append(f"読点が1文あたり平均 {avg:.2f} 個（{MAX_COMMA_AVG} 個以下にする。「、」が無くても伝わる文に書き直す。ぶつ切りにはしない）")
    elif avg > WARN_COMMA_AVG:
        warn.append(f"読点が1文あたり平均 {avg:.2f} 個（目安は {WARN_COMMA_AVG} 個以下）")
    two = [x for x, c in zip(sentences, commas) if c == 2]
    if len(two) > WARN_TWO_COMMAS:
        warn.append(f"読点2個の文が {len(two)} 個（分けられないか見直す）: " + " / ".join(two[:3]))
    long = [x for x in sentences if len(x) > WARN_LONG_LEN]
    if len(long) > WARN_LONG_COUNT:
        warn.append(f"{WARN_LONG_LEN} 字を超える文が {len(long)} 個: " + " / ".join(long[:3]))
    hard = [w for w in HARD_WORDS if w in body]
    if hard:
        warn.append("硬い言葉: " + "、".join(hard) + "（日常の言葉に言いかえる。rules/writing_rules.md「やさしい言葉にする」）")

    # 段落と空行
    prev = None
    for kind, text in parser.items:
        if kind == "p":
            ss = split_sentences(text)
            if len(ss) > MAX_SENTENCES_IN_PARAGRAPH and not all(len(x) <= SHORT_LINE for x in ss):
                ng.append(f"{len(ss)} 文の段落（1〜2文にする）: {text[:30]}…")
            if prev == "p":
                ng.append(f"段落の間に空行 <p><br></p> がない: {text[:30]}…")
        if kind == "blank" and prev == "blank":
            ng.append("空行 <p><br></p> が2つ以上続いている")
        prev = kind
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

    meta_words = " ".join([meta.get("title", ""), meta.get("main_keyword", "")] + list(meta.get("sub_keywords", [])))
    for where, src in (("本文", text), ("meta.json", meta_words)):
        m = AGE.search(src)
        if m:
            ng.append(f"{where}に年代・年齢の表現「{m.group()}」がある（年代は書かない。髪の悩み・髪質を中心にする）")
    for word in FORBIDDEN_WORDS:
        if word in text or word in meta.get("title", ""):
            ng.append(f"使わない言葉「{word}」がある")
    # 最後の LINE・店舗・Instagram は決まった文なので、リズムの確認から外す
    lines = Paragraphs()
    lines.feed(html.split("LINEにてご予約")[0])
    r_ng, r_warn = rhythm("\n".join(split_sentences("".join(lines.lines))))
    ng += r_ng
    warn += r_warn
    r_ng, r_warn = readability(html)
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
    if len(named) < MIN_PRODUCTS:
        if meta.get("no_product_reason"):
            warn.append(f"商品なし（理由: {meta['no_product_reason']}）。報告で追加が必要な商品を伝える")
        else:
            ng.append("商品が入っていない（1記事1商品以上。合う登録商品がないときは meta.json に no_product_reason を書く）")
    if len(named) > MAX_PRODUCTS:
        ng.append(f"商品が {len(named)} 個（{MAX_PRODUCTS} 商品まで。基本は1商品）")
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
