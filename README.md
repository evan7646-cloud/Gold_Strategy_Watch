# Gold Strategy Watch 🥇

即時黃金交易策略監控儀表板，整合 XAUUSD 4H K 線 30MA 跨市場動能策略 (+0h MT5 Server Time Alignment) 與視覺化介面。

## 功能

- **XAUUSD 主圖**：4H K 線圖、4H 30MA / Daily 20MA / 50MA / 60MA，可勾選顯示歷史交易進出場標記
- **Equity Curve**：策略累積損益曲線與即時浮動權益
- **DXY 美元指數圖**：日線走勢與 20MA / 60MA 均線
- **交易紀錄表格**：歷史交易含排序、篩選、勾選顯示功能
- **自動更新**：GitHub Actions 自動抓取最新 K 線並重跑策略 (跨時區歸一化防護)

## 策略說明

- **時區切分 (+0h MT5 伺服器對齊)**：從 1H K線歸一化時間切分，100% 精準對齊 Pepperstone MT5 伺服器標準 4H K線（開盤於 03, 07, 11, 15, 19, 23 伺服器時間 / 08, 12, 16, 20, 00, 04 台北時間）
- **多單邏輯（Long-Only）**：日線 Close > 50MA (牛市環境) 且 4H Close > 30MA 動能向上 → 次根 4H 開盤第 1 秒進場；採 1.0x ATR 軌跡移動停損
- **空單邏輯（Short-Only）**：日線 Close < 50MA (熊市環境) 且 4H Close < 30MA 動能向下 → 次根 4H 開盤第 1 秒進場
- **強勢加碼（Pyramid Boost）**：日線 20MA > 60MA 且 Alpha 動能全正時加碼；若 **10D Alpha > 3% (0.03)** 觸發 **2.0x 強勢放大手數加碼**
- **交易成本**：每筆扣 0.3 pts 點差；多單每日扣 0.75 pts 過夜費，空單每日加 0.27 pts 利息補貼

## 回測績效 (對齊 Pepperstone MT5 +0h 冠軍對齊版)

| 指標 | 4H 30MA (+0h Offset) 表現 |
|------|------|
| **累積總淨損益 (Total PnL)** | **+5,144.81 pts** |
| **最大點數回撤 (Max DD)** | **475.89 pts** |
| **夏普比率 (Sharpe Ratio)** | **2.80** |
| **卡爾瑪比率 (Calmar Ratio)** | **5.41 (極強抗洗盤與獲利能力)** |
| **獲利因子 (Profit Factor)** | **1.98** |
| **勝率 (Win Rate)** | **40.07%** |
| **總交易數** | **534 筆** |

## 本地執行

```bash
pip install -r requirements.txt
python gold_hybrid_strategy.py   # 抓取資料並更新 strategy_results.json
# 開啟 index.html 或用 Python 起伺服器
python3 -m http.server 8000
```

## 自動更新排程

GitHub Actions 在平日（週一至週五）的台北時間 **06:00 / 10:00 / 14:00 / 18:00 / 22:00** 自動執行資料更新，並透過 `Asia/Taipei` 時區防護確保與 MT5 實盤 100% 同步。

## 檔案說明

| 檔案 | 說明 |
|------|------|
| `gold_hybrid_strategy.py` | 主策略：時區歸一化數據抓取 + 回測 + 輸出 JSON |
| `Gold_4H_30MA_add2.0>3%_Strategy_Offset+0h.mq5` | Pepperstone MT5 實盤 EA (含 DXY.cash 自動匹配) |
| `Gold_4H_30MA_add1.5>3%_Strategy_Offset+0h_FTMO.mq5` | FTMO 專用風控熔斷版 MT5 EA |
| `strategy_results.json` | 網頁讀取的實時策略結果 |
| `index.html` / `app.js` / `styles.css` | 前端儀表板 |
