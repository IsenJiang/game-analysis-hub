#!/usr/bin/env python3
"""
build_industry_radar.py

抓取 feeds.yaml 中列出的行业信源，按「内容类型 × 地区」两个维度分组，
生成 docsify 页面 reports/industry-radar.md。

页面交互：左侧「分类 + 地区」导航，右侧内容区，点击左侧某个地区按钮，
右侧内容原地切换到对应分组，不需要滚动翻找。用纯 CSS（:checked 选择器）
实现 Tab 切换，不依赖 JavaScript，docsify 默认渲染即可正常工作。

地区维度：cn（中国）/ kr（韩国）/ west（欧美）

分类逻辑：
- 优先用关键词规则判断每一篇文章属于 news / hot / review 中的哪一类
  （检查标题 + 摘要文本，命中即归类，不需要任何付费 API）；
- 如果一篇都没命中，退回到该信源在 feeds.yaml 里配置的默认 category。

设计原则（合规 & 可维护）：
- 只保留标题 / 来源 / 日期 / 原文链接，不转载正文，规避版权问题；
- 用 .radar_state.json 完整保存已抓到的条目（含分类信息），每次运行时
  重新分组、重新渲染整个页面；
- 单个源解析失败不影响其他源；
- 每个 (category, region) 分组只保留最近 MAX_ITEMS_PER_GROUP 条。
"""

import html
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import yaml

FEEDS_FILE = "feeds.yaml"
OUTPUT_FILE = "reports/industry-radar.md"
STATE_FILE = ".radar_state.json"

LOOKBACK_DAYS = 30
MAX_ITEMS_PER_GROUP = 30

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

KEYWORD_RULES = {
    "review": [
        "评测", "测评", "体验测评", "上手体验", "评分", "打分",
        "review", "hands-on", "impressions", "we played", "verdict",
        "리뷰", "평가", "체험기",
    ],
    "news": [
        "发布", "上线", "公告", "财报", "季度营收", "收购", "融资", "裁员",
        "IPO", "上市", "股价", "并购",
        "acquisition", "acquires", "earnings", "revenue", "layoffs",
        "funding", "announces", "launches", "launch date", "release date",
        "ipo", "merger",
        "발매", "발표", "인수", "실적", "출시",
    ],
    "hot": [
        "热议", "爆火", "吐槽", "争议", "复盘", "现象级", "破圈",
        "controversy", "backlash", "viral", "trending", "opinion",
        "why is", "explained",
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
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
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


# ---------------------------------------------------------------------------
# 页面渲染：纯 CSS Tab 切换
# ---------------------------------------------------------------------------

CSS_BLOCK = """
<style>
.radar-wrap{display:flex;flex-wrap:wrap;gap:28px;margin-top:12px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;}
.radar-tab-input{position:absolute;opacity:0;pointer-events:none;}
.radar-nav{flex:0 0 200px;}
.radar-cat-group{margin-bottom:20px;}
.radar-cat-title{font-weight:700;font-size:14px;margin:0 0 6px;padding:6px 10px;border-radius:6px;background:rgba(66,185,131,0.10);}
.radar-btn{display:block;padding:6px 12px;margin:2px 0;border-radius:6px;cursor:pointer;font-size:13.5px;color:inherit;opacity:0.75;transition:background .15s,opacity .15s;}
.radar-btn:hover{background:rgba(0,0,0,0.06);opacity:1;}
.radar-content{flex:1 1 420px;min-width:280px;}
.radar-panel{display:none;}
.radar-item{padding:9px 0;border-bottom:1px solid rgba(0,0,0,0.08);}
.radar-item:last-child{border-bottom:none;}
.radar-item .radar-date{color:#888;font-size:12px;margin-right:8px;white-space:nowrap;}
.radar-item a{font-weight:500;text-decoration:none;}
.radar-item a:hover{text-decoration:underline;}
.radar-item .radar-source{color:#888;font-size:12.5px;margin-left:6px;}
.radar-empty{color:#999;font-style:italic;padding:12px 0;font-size:13.5px;}
@media (max-width:640px){.radar-wrap{flex-direction:column;}.radar-nav{flex:none;display:flex;flex-wrap:wrap;gap:0 16px;}.radar-cat-group{flex:1 1 100%;}}
{{ACTIVE_RULES}}
</style>
""".strip()


def escape(text):
    return html.escape(text, quote=True)


def render_page(items_by_link):
    all_items = list(items_by_link.values())

    all_keys = [f"{c}-{r}" for c in CATEGORY_ORDER for r in REGION_ORDER]
    default_key = all_keys[0]

    # 为每个 tab 生成一条 CSS 规则：选中该 radio 时，高亮对应按钮 + 显示对应面板
    active_rules = []
    for key in all_keys:
        active_rules.append(
            f'#radar-tab-{key}:checked ~ .radar-nav label[for="radar-tab-{key}"]'
            f'{{background:#42b983;color:#fff;opacity:1;font-weight:600;}}'
        )
        active_rules.append(
            f'#radar-tab-{key}:checked ~ .radar-content .radar-panel-{key}'
            f'{{display:block;}}'
        )
    css = CSS_BLOCK.replace("{{ACTIVE_RULES}}", "\n".join(active_rules))

    # 隐藏的 radio 输入（决定当前激活哪个 tab）
    radio_inputs = "".join(
        f'<input type="radio" name="radar-tab" id="radar-tab-{key}" '
        f'class="radar-tab-input"{" checked" if key == default_key else ""}>'
        for key in all_keys
    )

    # 左侧导航：按分类分组，组内是地区按钮
    nav_groups = []
    for category in CATEGORY_ORDER:
        buttons = "".join(
            f'<label for="radar-tab-{category}-{region}" class="radar-btn">'
            f'{REGION_LABELS[region]}</label>'
            for region in REGION_ORDER
        )
        nav_groups.append(
            f'<div class="radar-cat-group">'
            f'<p class="radar-cat-title">{CATEGORY_LABELS[category]}</p>'
            f'{buttons}</div>'
        )
    nav_html = "".join(nav_groups)

    # 右侧内容：每个 分类×地区 一个面板
    panels = []
    for category in CATEGORY_ORDER:
        for region in REGION_ORDER:
            key = f"{category}-{region}"
            group = [
                it for it in all_items
                if it["category"] == category and it["region"] == region
            ]
            group.sort(key=lambda x: x["date_sort"], reverse=True)
            group = group[:MAX_ITEMS_PER_GROUP]

            if not group:
                body = '<p class="radar-empty">暂无收录内容</p>'
            else:
                rows = "".join(
                    f'<div class="radar-item">'
                    f'<span class="radar-date">{escape(it["date"])}</span>'
                    f'<a href="{escape(it["link"])}" target="_blank" rel="noopener">{escape(it["title"])}</a>'
                    f'<span class="radar-source">— {escape(it["source"])}</span>'
                    f'</div>'
                    for it in group
                )
                body = rows

            panels.append(f'<div class="radar-panel radar-panel-{key}">{body}</div>')
    panels_html = "".join(panels)

    body_html = (
        f'{css}\n'
        f'<div class="radar-wrap">\n'
        f'{radio_inputs}\n'
        f'<div class="radar-nav">{nav_html}</div>\n'
        f'<div class="radar-content">{panels_html}</div>\n'
        f'</div>\n'
    )

    header_md = (
        "# 📡 行业资讯雷达 (Industry Radar)\n\n"
        f"> 自动抓取，最后更新：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        "> 仅收录标题、来源与链接，不转载正文，请点击标题跳转阅读原文。\n"
        "> 分类由关键词规则自动判断，可能存在误判，仅供参考。点击左侧分类下的地区按钮切换内容。\n\n"
    )

    return header_md + body_html


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
