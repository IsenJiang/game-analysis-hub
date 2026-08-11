name: Update Industry Radar

on:
  schedule:
    - cron: "0 1 * * *"   # 每天 UTC 01:00（北京时间 09:00）自动运行
  workflow_dispatch: {}    # 允许在 GitHub Actions 页面手动点击触发

permissions:
  contents: write   # 需要写权限才能把生成的文件 commit 回仓库

jobs:
  build-radar:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run radar script
        run: python scripts/build_industry_radar.py

      - name: Commit changes
        run: |
          git config user.name "industry-radar-bot"
          git config user.email "actions@users.noreply.github.com"
          git add reports/industry-radar.md .radar_state.json
          git diff --cached --quiet || git commit -m "chore: update industry radar $(date -u +'%Y-%m-%d')"
          git push
