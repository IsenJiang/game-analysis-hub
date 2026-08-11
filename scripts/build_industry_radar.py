#!/usr/bin/env python3
"""
build_industry_radar.py

抓取 feeds.yaml 中列出的行业资深人士/媒体 RSS 源，生成 docsify 页面
reports/industry-radar.md。

设计原则（合规 & 可维护）：
- 只保留标题 / 来源 / 日期 / 原文链接，不转载正文，规避版权问题；
- 用 .radar_state.json 记录已收录过的链接，避免重复；
- 单个源解析失败不影响其他源（不会让整个 Action 失败）；
- 可选关键词过滤，只留下与你关注方向相关的条目。
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import yaml

FEEDS_FILE = "feeds.yaml"
OUTPUT_FILE = "reports/industry-radar.md"
STATE_FILE = ".radar_state.json"

LOOKBACK_DAYS = 14      # 只收录最近 N 天的条目
MAX_TOTAL_ITEMS = 300   # 页面最多保留多少条历史记录，超出从尾部裁掉

# 关键词过滤：留空列表 [] 表示不过滤、全部保留。
# 想让抓取更"有效"，就把你实际在追的方向/游戏名填进来，比如：
# KEYWORDS = ["留存", "变现", "SLG", "roguelike", "赛季制", "monetization", "retention"]
KEYWORDS = []


def load_feeds():
    with open(FEEDS_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["feeds"]


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_state(seen_links):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen_links), f, ensure_ascii=False, indent=2)


def matches_keywords(entry, keywords):
    if not keywords:
        return True
    text = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
    return any(k.lower() in text for k in keywords)


def entry_date(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def main():
    feeds = load_feeds()
    seen_links = load_state()
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    new_items = []
    for src in feeds:
        try:
            parsed = feedparser.parse(src["url"])
        except Exception as e:
            print(f"[WARN] 抓取失败: {src['name']} ({src['url']}) -> {e}")
            continue

        if not parsed.entries:
            print(f"[WARN] 无法解析或无内容: {src['name']} ({src['url']})")
            continue

        for entry in parsed.entries:
            link = entry.get("link")
            if not link or link in seen_links:
                continue

            date = entry_date(entry)
            if date and date < cutoff:
                continue

            if not matches_keywords(entry, KEYWORDS):
                continue

            new_items.append({
                "source": src["name"],
                "category": src.get("category", ""),
                "title": entry.get("title", "无标题").strip(),
                "link": link,
                "date": date.strftime("%Y-%m-%d") if date else "未知日期",
                "sort_key": date or datetime.min.replace(tzinfo=timezone.utc),
            })
            seen_links.add(link)

    new_items.sort(key=lambda x: x["sort_key"], reverse=True)

    # 读取旧内容里已生成的条目，插到新条目后面
    existing_lines = []
    marker = "<!-- RADAR_ITEMS_START -->"
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        if marker in content:
            body = content.split(marker, 1)[1].strip("\n")
            if body:
                existing_lines = body.split("\n")

    new_lines = [
        f"- **{item['date']}** · [{item['title']}]({item['link']}) "
        f"— *{item['source']}*" + (f" `{item['category']}`" if item["category"] else "")
        for item in new_items
    ]

    all_lines = (new_lines + existing_lines)[:MAX_TOTAL_ITEMS]

    header = (
        "# 📡 行业资讯雷达 (Industry Radar)\n\n"
        f"> 自动抓取，最后更新：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        "> 仅收录标题、来源与链接，不转载正文，请点击标题跳转阅读原文。\n\n"
        f"{marker}\n"
    )

    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(all_lines) + "\n")

    save_state(seen_links)
    print(f"本次新增 {len(new_items)} 条，页面共保留 {len(all_lines)} 条")


if __name__ == "__main__":
    main()
