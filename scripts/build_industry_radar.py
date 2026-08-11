#!/usr/bin/env python3
"""
build_industry_radar.py

抓取 feeds.yaml 中列出的行业信源，按「内容类型 × 地区」两个维度分组，
生成 docsify 页面 reports/industry-radar.md。

设计原则（合规 & 可维护）：
- 只保留标题 / 来源 / 日期 / 原文链接，不转载正文，规避版权问题；
- 用 .radar_state.json 完整保存已抓到的条目（含分类信息），每次运行时
  重新分组、重新渲染整个页面，而不是简单地往文件顶部追加文本；
- 单个源解析失败不影响其他源（不会让整个 Action 失败）；
- 每个 (category, region) 分组只保留最近 MAX_ITEMS_PER_GROUP 条，
  防止页面无限增长。
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

LOOKBACK_DAYS = 30          # 抓取时只考虑最近 N 天发布的新条目
MAX_ITEMS_PER_GROUP = 30    # 每个 分类×地区 分组，页面上最多展示多少条

CATEGORY_ORDER = ["news", "hot", "review"]
CATEGORY_LABELS = {
    "news": "📰 行业新闻",
    "hot": "🔥 热点资讯",
    "review": "🎮 游戏评论",
}

REGION_ORDER = ["cn", "jp_kr", "west"]
REGION_LABELS = {
    "cn": "🇨🇳 中国",
    "jp_kr": "🇯🇵🇰🇷 日韩",
    "west": "🌍 欧美",
}


def load_feeds():
    with open(FEEDS_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["feeds"]


def load_state():
    """返回 {link: item_dict} 形式的已收录条目"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 兼容旧版本 state 文件（只存了链接列表的情况）
            if isinstance(data, list):
                return {}
            return {item["link"]: item for item in data.get("items", [])}
    return {}


def save_state(items_by_link):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"items": list(items_by_link.values())}, f, ensure_ascii=False, indent=2)


def entry_date(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def fetch_new_items(feeds, existing_links, cutoff):
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
            if not link or link in existing_links:
                continue

            date = entry_date(entry)
            if date and date < cutoff:
                continue

            new_items.append({
                "link": link,
                "title": entry.get("title", "无标题").strip(),
                "source": src["name"],
                "region": src.get("region", "west"),
                "category": src.get("category", "news"),
                "date": date.strftime("%Y-%m-%d") if date else "未知日期",
                "date_sort": date.isoformat() if date else "0000",
            })

    return new_items


def render_page(items_by_link):
    all_items = list(items_by_link.values())

    lines = [
        "# 📡 行业资讯雷达 (Industry Radar)",
        "",
        f"> 自动抓取，最后更新：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "> 仅收录标题、来源与链接，不转载正文，请点击标题跳转阅读原文。",
        "",
    ]

    for category in CATEGORY_ORDER:
        lines.append(f"## {CATEGORY_LABELS[category]}")
        lines.append("")

        for region in REGION_ORDER:
            group = [
                it for it in all_items
                if it["category"] == category and it["region"] == region
            ]
            group.sort(key=lambda x: x["date_sort"], reverse=True)
            group = group[:MAX_ITEMS_PER_GROUP]

            lines.append(f"### {REGION_LABELS[region]}")
            lines.append("")

            if not group:
                lines.append("_暂无收录内容_")
            else:
                for item in group:
                    lines.append(
                        f"- **{item['date']}** · [{item['title']}]({item['link']}) "
                        f"— *{item['source']}*"
                    )
            lines.append("")

    return "\n".join(lines) + "\n"


def main():
    feeds = load_feeds()
    items_by_link = load_state()
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    new_items = fetch_new_items(feeds, set(items_by_link.keys()), cutoff)
    for item in new_items:
        items_by_link[item["link"]] = item

    page = render_page(items_by_link)

    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(page)

    save_state(items_by_link)
    print(f"本次新增 {len(new_items)} 条，累计收录 {len(items_by_link)} 条")


if __name__ == "__main__":
    main()
