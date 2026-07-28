# Gold Strategy Watch 🥇

即時黃金交易策略監控儀表板，整合 XAUUSD 4H K 線 30MA 回測策略 (+2h Offset) 與視覺化介面。

## 功能

- **XAUUSD 主圖**：4H K 線圖、4H 30MA / Daily 20MA / 50MA / 60MA，可勾選顯示歷史交易進出場標記
- **Equity Curve**：策略累積損益曲線
- **DXY 美元指數圖**：日線走勢與均線
- **交易紀錄表格**：歷史交易含排序、篩選、勾選顯示功能
- **自動更新**：GitHub Actions 自動抓取最新 K 線並重跑策略

## 策略說明

- **多單（Long-Only）**：4H 收盤 > 30MA 且動能向上 → 次根 4H 開盤進場；止損跌破移動止損（ATR-based）
- **空單（Short-Only）**：4H 收盤 < 30MA 且動能向下 → 次根 4H 開盤進場
- **加倉（Pyramid）**：日線 close > MA50 且 Alpha 多頭時加倉 (Alpha10 > 3% 時觸發 2.0x 強勢加碼)
- **成本**：每筆扣 0.3 pts 點差；多單每日扣 0.75 pts 過夜費，空單每日加 0.27 pts 利息

## 回測績效（截至 2026-07 回測）

| 指標 | 4H 30MA (+2h Offset) |
|------|------|
| **累積總損益 (Total PnL)** | **+3354.61 pts** |
| **最大回撤 (Max DD)** | **437.35 pts** |
| **Sharpe Ratio** | **2.43** |
| **Calmar Ratio** | **4.97 (極佳抗洗盤)** |
| **勝率 (Win Rate)** | **37.60%** |
| **獲利因子 (Profit Factor)** | **1.62** |
| **總交易數** | **500 筆** |

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
