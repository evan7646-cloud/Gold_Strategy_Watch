# Gold Strategy Watch 🥇

即時黃金交易策略監控儀表板，整合 XAUUSD 8H K 線回測策略與視覺化介面。

## 功能

- **XAUUSD 主圖**：K 線圖、30MA / 20MA / 50MA / 60MA，可勾選顯示歷史交易進出場標記
- **Equity Curve**：策略累積損益曲線
- **DXY 美元指數圖**：日線走勢與均線
- **交易紀錄表格**：355 筆歷史交易，含排序、篩選、勾選顯示功能
- **自動更新**：GitHub Actions 平日每 4 小時自動抓取最新 K 線並重跑策略

## 策略說明

- **多單（Long-Only）**：8H 收盤 > 30MA 且動能向上 → 次根 8H 開盤進場；止損跌破移動止損（ATR-based）
- **空單（Short-Only）**：8H 收盤 < 30MA 且動能向下 → 次根 8H 開盤進場
- **加倉（Pyramid）**：日線 close > MA50 且 Alpha 多頭時加倉
- **成本**：每筆扣 0.3 pts 點差；多單每日扣 0.75 pts 過夜費，空單每日加 0.27 pts 利息

## 回測績效（截至最新更新）

| 指標 | Long-Only | Short-Only | Combined |
|------|------|------|------|
| 累積損益 | 1961.65 pts | 121.12 pts | **2082.77 pts** |
| 最大回撤 | 405.75 pts | 260.19 pts | 600.21 pts |
| Sharpe Ratio | 1.927 | 0.189 | 1.608 |
| 勝率 | 38.5% | 33.9% | 37.7% |
| 獲利因子 | 1.66 | 1.11 | 1.51 |

## 本地執行

```bash
pip install -r requirements.txt
python gold_hybrid_strategy.py   # 抓取資料並更新 strategy_results.json
# 開啟 index.html 或用 Python 起伺服器
python3 -m http.server 8000
```

## 自動更新排程

GitHub Actions 在平日（週一至週五）的台北時間 **06:00 / 10:00 / 14:00 / 18:00 / 22:00** 自動執行資料更新。

## 檔案說明

| 檔案 | 說明 |
|------|------|
| `gold_hybrid_strategy.py` | 主策略：抓資料 + 回測 + 輸出 JSON |
| `Final_backtest_combined_hybrid.py` | 完整回測（含 Sharpe / MDD / Calmar） |
| `strategy_results.json` | 網頁讀取的策略結果 |
| `index.html` / `app.js` / `styles.css` | 前端儀表板 |
