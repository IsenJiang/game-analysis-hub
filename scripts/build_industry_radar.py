#!/usr/bin/env python3
"""
build_industry_radar.py

抓取 feeds.yaml 中列出的行业信源，按「内容类型 × 地区」两个维度分组，
生成 docsify 页面 reports/industry-radar.md。

地区维度：cn（中国）/ kr（韩国）/ west（欧美）

分类逻辑：
- 优先用关键词规则判断每一篇文章属于 news / hot / review 中的哪一类
  （检查标题 + 摘要文本，命中即归类，不需要任何付费 API）；
- 如果一篇都没命中，退回到该信源在 feeds.yaml 里配置的默认 category。

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

REGION_ORDER = ["cn", "kr", "west"]
REGION_LABELS = {
    "cn": "🇨🇳 中国",
    "kr": "🇰🇷 韩国",
    "west": "🌍 欧美",
}

# ---------------------------------------------------------------------------
# 关键词分类规则：按优先级从上到下检查，命中第一个就用哪个分类。
# review（游戏评论）优先级最高，因为"评测/上手"这类词最不容易和别的类目混淆；
# news（行业新闻）其次，因为"发布/融资/财报"这类词通常指向客观事件；
# 都没命中的，最后交给 hot 或者信源默认分类兜底。
#
# 覆盖中文 / 英文 / 韩文，方便匹配三个地区的信源。
# 想调整分类效果，直接在这几个列表里增删关键词即可，不需要动其他逻辑。
# ---------------------------------------------------------------------------
KEYWORD_RULES = {
    "review": [
        # 中文
        "评测", "测评", "体验测评", "上手体验", "评分", "打分",
        # 英文
        "review", "hands-on", "impressions", "we played", "verdict",
        # 韩文
        "리뷰", "평가", "체험기",
    ],
    "news": [
        # 中文
        "发布", "上线", "公告", "财报", "季度营收", "收购", "融资", "裁员",
        "IPO", "上市", "股价", "并购",
        # 英文
        "acquisition", "acquires", "earnings", "revenue", "layoffs",
        "funding", "announces", "launches", "launch date", "release date",
        "ipo", "merger",
        # 韩文
        "발매", "발표", "인수", "실적", "출시",
    ],
    "hot": [
        # 中文
        "热议", "爆火", "吐槽", "争议", "复盘", "现象级", "破圈",
        # 英文
        "controversy", "backlash", "viral", "trending", "opinion",
        "why is", "explained",
        # 韩文
        "논란", "화제", "떡밥",
    ],
}


def classify_item(title, summary, fallback_category):
    text = f"{title} {summary}".lower()
    for category in ("review", "news", "hot"):
        for kw in KEYWORD_RULES[category]:
            if kw.lower() in text:
                return category
    return fallback_category


def load_feeds():
    with open(FEEDS_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["feeds"]


def load_state():
    """返回 {link: item_dict} 形式的已收录条目"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):  # 兼容更早期的 state 格式
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
        region = src.get("region", "west")
        if region not in REGION_ORDER:
            print(f"[WARN] 未知 region '{region}'，跳过信源: {src['name']}")
            continue

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

            title = entry.get("title", "无标题").strip()
            summary = entry.get("summary", "")
            fallback_category = src.get("category", "news")
            category = classify_item(title, summary, fallback_category)

            new_items.append({
                "link": link,
                "title": title,
                "source": src["name"],
                "region": region,
                "category": category,
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
        "> 分类由关键词规则自动判断，可能存在误判，仅供参考。",
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
