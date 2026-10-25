#!/usr/bin/env python3
"""今日のテーマ選び。data/theme_pool.md から、過去記事と重ならないテーマを順位付けして出す。

使い方: python3 scripts/pick_theme.py [件数]
1位から順に検討し、過去記事と同じ悩み・同じ結論にならないものを選ぶ（最終判断は CLAUDE.md の「テーマの選び方」）。
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECENT = 7
SAME_CATEGORY_LIMIT = 3
GENERIC_WORDS = {"髪", "毛先"}  # 中心の語として扱わない
NEAR_LIMIT = 0.35  # 過去記事と言葉の重なりがこれ以上なら「近い」


def bigrams(s):
    s = re.sub(r"[\s【】「」『』！？!?、。・｜|（）()～〜0-9０-９]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def overlap(theme, past, core=""):
    """テーマ側の言葉のうち、過去記事に出てくる割合。中心の語（カテゴリ名以外）が過去記事にあれば 0.5 以上"""
    a, b = bigrams(theme), bigrams(past)
    score = len(a & b) / len(a) if a and b else 0.0
    return max(score, 0.5) if core and core in past else score


def load_pool():
    pool = []
    for line in (ROOT / "data/theme_pool.md").read_text(encoding="utf-8").splitlines():
        parts = [p.strip() for p in line.split("｜")]
        if len(parts) == 3 and all(parts) and not line.startswith("#"):
            pool.append({"category": parts[0], "main_keyword": parts[1], "worry": parts[2]})
    return pool


def load_csv(name):
    path = ROOT / "data" / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def category_scores(history, performance):
    """performance.csv の収益・クリックをカテゴリごとに合計"""
    cat_by_date = {r["date"]: r["category"] for r in history}
    links = json.loads((ROOT / "data/affiliate_links.json").read_text(encoding="utf-8"))["links"]
    cat_by_link = {l["id"]: l["category"][0] for l in links if l.get("category")}
    score = Counter()
    for r in performance:
        cat = cat_by_date.get(r.get("date", "")) or cat_by_link.get(r.get("affiliate_id", ""))
        if not cat:
            continue
        def num(k):
            try:
                return float(r.get(k) or 0)
            except ValueError:
                return 0.0
        score[cat] += num("revenue_yen") * 10 + num("clicks")
    return score


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    pool, history = load_pool(), load_csv("theme_history.csv")
    history.sort(key=lambda r: r["date"])
    used = {r["main_keyword"] for r in history}
    recent = history[-RECENT:]
    recent_count = Counter(r["category"] for r in recent)
    last_category = history[-1]["category"] if history else ""
    perf = category_scores(history, load_csv("performance.csv"))
    links = json.loads((ROOT / "data/affiliate_links.json").read_text(encoding="utf-8"))["links"]

    rows = []
    for i, t in enumerate(pool):
        if t["main_keyword"] in used:
            continue
        text = t["main_keyword"] + t["worry"]
        core = t["main_keyword"].split()[0]
        core = "" if core == t["category"] or core in GENERIC_WORDS else core
        near = max(((overlap(text, r["title"] + r["theme"] + r["main_keyword"], core), r) for r in history),
                   key=lambda x: x[0], default=(0.0, None))
        products = [l["id"] for l in links if t["category"] in l.get("category", [])]
        t.update(index=i, near=near[0], near_title=near[1]["title"] if near[1] else "",
                 blocked=recent_count[t["category"]] >= SAME_CATEGORY_LIMIT,
                 same_as_last=t["category"] == last_category, perf=perf[t["category"]],
                 recent=recent_count[t["category"]], products=products)
        rows.append(t)

    rows.sort(key=lambda t: (t["blocked"], t["near"] >= NEAR_LIMIT, t["same_as_last"], -t["perf"],
                             not t["products"], t["recent"], t["index"]))
    print(f"直近{RECENT}本のカテゴリ: " + "、".join(f"{c}{n}" for c, n in recent_count.most_common()))
    print(f"前回のカテゴリ: {last_category or 'なし'}　未使用テーマ: {len(rows)} 個")
    if perf:
        print("反応の良いカテゴリ: " + "、".join(f"{c}({v:g})" for c, v in perf.most_common(3)))
    print()
    for n, t in enumerate(rows[:limit], 1):
        notes = []
        if t["blocked"]:
            notes.append(f"直近{RECENT}本で{t['category']}が{t['recent']}本のため不可")
        if t["near"] >= NEAR_LIMIT:
            notes.append(f"過去記事に近い（{t['near']:.2f}「{t['near_title']}」）→ 対象か切り口を変える")
        if t["same_as_last"]:
            notes.append("前回と同じカテゴリ")
        notes.append("登録商品: " + ("、".join(t["products"]) if t["products"] else "なし"))
        print(f"{n}. {t['category']}｜{t['main_keyword']}｜{t['worry']}")
        print("   " + "／".join(notes))
    if len(rows) < 10:
        print("\nテーマの追加が必要（未使用が10個未満）")


if __name__ == "__main__":
    main()
