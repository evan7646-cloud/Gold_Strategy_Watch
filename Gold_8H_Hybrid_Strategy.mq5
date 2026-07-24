//+------------------------------------------------------------------+
//|                                    Gold_8H_Hybrid_Strategy.mq5    |
//|                                    黃金 8H 多空混合策略 EA         |
//|                                    Version 1.00                    |
//+------------------------------------------------------------------+
#property copyright "Gold 8H Hybrid Strategy" // 版權宣告
#property version   "1.00" // 版本號
#property strict // 嚴格模式
#property description "黃金 8H 多空混合策略 EA" // EA 描述文字
#property description "基於日線趨勢過濾 + 8H 動能確認 + 移動停損 + 加倉機制" // 描述第二行

#include <Trade/Trade.mqh> // 引入 MQL5 標準交易函式庫

//+------------------------------------------------------------------+
//| 輸入參數 (Input Parameters)                                       |
//+------------------------------------------------------------------+
input group "===== 商品設定 =====" // 商品設定群組
// 📌 交易商品 = 圖表商品 (XAUUSD)，請將此 EA 掛載到 XAUUSD 圖表上
// 📌 DXY 僅用於計算 Alpha 動能指標（加倉過濾），不會對 DXY 下單
input string   InpDXYSymbol      = "DXY_U6";        // DXY 商品名稱 (僅用於讀取報價計算 Alpha，不交易此商品)
input double   InpLotSize        = 0.01;             // 每筆交易手數 (主部位與加倉各用此手數)

input group "===== 指標參數 =====" // 指標參數群組
input int      InpMA8H_Period    = 30;               // 8H 均線 (SMA) 週期
input int      InpATR8H_Period   = 14;               // 8H ATR 週期
input int      InpMA50_Period    = 50;               // 日線 50MA 週期 (大趨勢過濾)
input int      InpMA20_Period    = 20;               // 日線 20MA 週期 (加倉過濾)
input int      InpMA60_Period    = 60;               // 日線 60MA 週期 (加倉過濾)

input group "===== 交易識別 =====" // 交易識別群組
input ulong    InpMagicMain      = 88880001;         // 主部位 Magic Number
input ulong    InpMagicPyramid   = 88880002;         // 加倉部位 Magic Number

input group "===== 其他與加倉設定 =====" // 其他與加倉設定群組
input bool     InpEnablePyramid          = true;             // 是否啟用加倉機制
input double   InpAlphaBoostThresh       = 0.03;             // Alpha10 放大手數門檻 (預設 3% = 0.03)
input double   InpPyramidBoostMultiplier = 2.0;              // Alpha10 達標時加碼手數倍率 (預設 2.0 倍)
input bool     InpEnableAlerts           = true;             // 是否啟用交易提醒通知

//+------------------------------------------------------------------+
//| 全域狀態變數 (Global State Variables)                              |
//+------------------------------------------------------------------+
double   g_MainStopPrice    = 0.0;    // 主部位移動停損價
double   g_PyramidStopPrice = 0.0;    // 加倉部位移動停損價
datetime g_LastBar8H        = 0;      // 上一次已處理的 8H K 線開盤時間
datetime g_LastBarDaily     = 0;      // 上一次已處理的日線開盤時間

//--- 日線過濾器狀態 (Daily Filter State)
bool     g_RegimeBull       = false;  // 日線大趨勢是否為牛市 (Bull = true, Bear = false)
bool     g_PyramidLongOK    = false;  // 日線是否允許加多
bool     g_PyramidShortOK   = false;  // 日線是否允許加空
bool     g_DailyReady       = false;  // 日線指標是否已完成首次計算

//--- 指標句柄 (Indicator Handles)
int      g_hMA8H   = INVALID_HANDLE; // 8H 30SMA 指標句柄
int      g_hATR8H  = INVALID_HANDLE; // 8H ATR14 指標句柄
int      g_hMA50D  = INVALID_HANDLE; // 日線 50SMA 指標句柄
int      g_hMA20D  = INVALID_HANDLE; // 日線 20SMA 指標句柄
int      g_hMA60D  = INVALID_HANDLE; // 日線 60SMA 指標句柄

//--- 交易物件 (Trade Object)
CTrade   g_trade;                     // CTrade 交易執行物件

//--- GlobalVariable 持久化鍵名 (Persistence Keys)
string   g_gvKeyMainStop;            // 主部位停損價的 GlobalVariable 鍵名
string   g_gvKeyPyramidStop;         // 加倉部位停損價的 GlobalVariable 鍵名
string   g_gvKeyLastBar8H;           // 上次 8H K 線時間的 GlobalVariable 鍵名

//+------------------------------------------------------------------+
//| 取得經紀商支援的成交模式 (解決 10030 / 10027 成交模式退單錯誤)   |
//+------------------------------------------------------------------+
ENUM_ORDER_TYPE_FILLING GetValidFillingMode()
{
   uint filling = (uint)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE); // 讀取商品成交模式標誌
   if((filling & SYMBOL_FILLING_IOC) != 0) return ORDER_FILLING_IOC;    // 優先使用 IOC
   if((filling & SYMBOL_FILLING_FOK) != 0) return ORDER_FILLING_FOK;    // 次選 FOK
   return ORDER_FILLING_RETURN;                                         // 預設使用 RETURN
}

//+------------------------------------------------------------------+
//| 規範手數至經紀商最小/最大與步長範圍 (防止不合法手數退單)           |
//+------------------------------------------------------------------+
double NormalizeLot(double lot)
{
   double step   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP); // 手數步長
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);  // 最小手數
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);  // 最大手數

   if(step <= 0) step = 0.01; // 防空值
   double normalized = MathFloor(lot / step + 0.000001) * step; // 依步長向下對齊
   if(normalized < minLot) normalized = minLot; // 不得低於最小手數
   if(normalized > maxLot) normalized = maxLot; // 不得高於最大手數
   return NormalizeDouble(normalized, 2); // 規範小數位數
}

//+------------------------------------------------------------------+
//| EA 初始化函數 (OnInit)                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   //--- 建立 GlobalVariable 鍵名 (含 Magic Number 確保唯一性)
   string prefix = "G8H_" + IntegerToString(InpMagicMain) + "_"; // 建立前綴字串
   g_gvKeyMainStop    = prefix + "MainStop"; // 主部位停損鍵名
   g_gvKeyPyramidStop = prefix + "PyramidStop"; // 加倉停損鍵名
   g_gvKeyLastBar8H   = prefix + "LastBar8H"; // 上次 8H 時間鍵名

   //--- 嘗試將 DXY 商品加入 Market Watch (確保可取得跨市場數據)
   if(!SymbolSelect(InpDXYSymbol, true)) // 加入 DXY 至 Market Watch
   {
      PrintFormat("⚠️ 警告：無法將 %s 加入 Market Watch，加倉過濾器將尋找備用商品", InpDXYSymbol); // 印出警告
   }

   //--- 建立 8H 時區指標句柄
   g_hMA8H = iMA(_Symbol, PERIOD_H8, InpMA8H_Period, 0, MODE_SMA, PRICE_CLOSE); // 建立 8H SMA 句柄
   if(g_hMA8H == INVALID_HANDLE) // 若建立失敗
   {
      PrintFormat("❌ 錯誤：無法建立 8H MA(%d) 指標句柄", InpMA8H_Period); // 印出錯誤
      return(INIT_FAILED); // 回傳初始化失敗
   }

   g_hATR8H = iATR(_Symbol, PERIOD_H8, InpATR8H_Period); // 建立 8H ATR 句柄
   if(g_hATR8H == INVALID_HANDLE) // 若建立失敗
   {
      PrintFormat("❌ 錯誤：無法建立 8H ATR(%d) 指標句柄", InpATR8H_Period); // 印出錯誤
      return(INIT_FAILED); // 回傳初始化失敗
   }

   //--- 建立日線指標句柄
   g_hMA50D = iMA(_Symbol, PERIOD_D1, InpMA50_Period, 0, MODE_SMA, PRICE_CLOSE); // 建立日線 50SMA 句柄
   if(g_hMA50D == INVALID_HANDLE) // 若建立失敗
   {
      PrintFormat("❌ 錯誤：無法建立日線 MA(%d) 指標句柄", InpMA50_Period); // 印出錯誤
      return(INIT_FAILED); // 回傳初始化失敗
   }

   g_hMA20D = iMA(_Symbol, PERIOD_D1, InpMA20_Period, 0, MODE_SMA, PRICE_CLOSE); // 建立日線 20SMA 句柄
   if(g_hMA20D == INVALID_HANDLE) // 若建立失敗
   {
      PrintFormat("❌ 錯誤：無法建立日線 MA(%d) 指標句柄", InpMA20_Period); // 印出錯誤
      return(INIT_FAILED); // 回傳初始化失敗
   }

   g_hMA60D = iMA(_Symbol, PERIOD_D1, InpMA60_Period, 0, MODE_SMA, PRICE_CLOSE); // 建立日線 60SMA 句柄
   if(g_hMA60D == INVALID_HANDLE) // 若建立失敗
   {
      PrintFormat("❌ 錯誤：無法建立日線 MA(%d) 指標句柄", InpMA60_Period); // 印出錯誤
      return(INIT_FAILED); // 回傳初始化失敗
   }

   //--- 設定交易物件的 Magic Number 與滑點
   g_trade.SetExpertMagicNumber(InpMagicMain); // 預設使用主部位 Magic Number
   g_trade.SetDeviationInPoints(50); // 設定最大滑點 50 個點 (實盤保護)
   g_trade.SetTypeFilling(GetValidFillingMode()); // 🛡️ 動態設定經紀商支援的成交模式 (防止 10030 退單)

   //--- 從 GlobalVariable 恢復持久化狀態 (防止 EA 重啟後遺失停損價)
   LoadPersistentState(); // 載入持久化狀態

   //--- 初始化日線過濾器 (首次運行時立即計算)
   UpdateDailyFilters(); // 更新日線過濾指標

   //--- 印出初始化成功訊息
   PrintFormat("✅ Gold 8H Hybrid Strategy EA 初始化成功"); // 初始化成功提示
   PrintFormat("   商品: %s | DXY: %s | 手數: %.2f", _Symbol, InpDXYSymbol, InpLotSize); // 印出設定
   PrintFormat("   8H MA: %d | ATR: %d | Daily MA: %d/%d/%d", // 印出指標參數
               InpMA8H_Period, InpATR8H_Period, InpMA50_Period, InpMA20_Period, InpMA60_Period);

   return(INIT_SUCCEEDED); // 回傳初始化成功
}

//+------------------------------------------------------------------+
//| EA 卸載函數 (OnDeinit)                                            |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   //--- 釋放所有指標句柄以回收記憶體
   if(g_hMA8H  != INVALID_HANDLE) IndicatorRelease(g_hMA8H);   // 釋放 8H MA 句柄
   if(g_hATR8H != INVALID_HANDLE) IndicatorRelease(g_hATR8H);  // 釋放 8H ATR 句柄
   if(g_hMA50D != INVALID_HANDLE) IndicatorRelease(g_hMA50D);  // 釋放日線 50MA 句柄
   if(g_hMA20D != INVALID_HANDLE) IndicatorRelease(g_hMA20D);  // 釋放日線 20MA 句柄
   if(g_hMA60D != INVALID_HANDLE) IndicatorRelease(g_hMA60D);  // 釋放日線 60MA 句柄

   //--- 儲存當前狀態至 GlobalVariable (持久化)
   SavePersistentState(); // 儲存停損價等狀態

   PrintFormat("🔴 Gold 8H Hybrid Strategy EA 已卸載 (原因代碼: %d)", reason); // 印出卸載訊息
}

//+------------------------------------------------------------------+
//| EA 主邏輯 (OnTick) - 每個 Tick 觸發一次                           |
//+------------------------------------------------------------------+
void OnTick()
{
   //--- 🛡️ 斷線重啟與手動平倉同步防護
   int totalEAPos = CountPositionsByEA(); // 統計本 EA 當前總持倉數量
   bool hasMain = HasPositionByMagic(InpMagicMain, POSITION_TYPE_BUY) || HasPositionByMagic(InpMagicMain, POSITION_TYPE_SELL); // 有無主部位
   bool hasPyr  = HasPositionByMagic(InpMagicPyramid, POSITION_TYPE_BUY) || HasPositionByMagic(InpMagicPyramid, POSITION_TYPE_SELL); // 有無加倉部位

   if(!hasMain && hasPyr) // 🛡️ 漏洞修復：若手動關閉主單但殘留加倉單 (孤兒部位)
   {
      Print("⚠️ [孤兒部位防護] 偵測到主部位已被平倉！自動平倉孤立加倉部位以維持策略運作"); // 警報日誌
      ClosePositionsByMagic(InpMagicPyramid); // 強制平倉孤立加倉部位
      g_MainStopPrice = 0.0; // 清空主停損
      g_PyramidStopPrice = 0.0; // 清空加倉停損
      SavePersistentState(); // 儲存持久化狀態
   }
   else if(!hasMain && g_MainStopPrice != 0.0) // 主部位個案手動平倉同步
   {
      g_MainStopPrice = 0.0; // 清空主部位停損
      SavePersistentState(); // 儲存持久化狀態
   }
   else if(!hasPyr && g_PyramidStopPrice != 0.0) // 加倉部位個案手動平倉同步
   {
      g_PyramidStopPrice = 0.0; // 清空加倉部位停損
      SavePersistentState(); // 儲存持久化狀態
   }

   if(totalEAPos > 0 && g_MainStopPrice == 0.0 && g_DailyReady) // 若有持倉但停損價為零
   {
      ReconstructStopPrices(); // 啟動歷史軌跡重構
   }

   //--- 檢查是否有新的日線 K 線收盤 (更新日線過濾器)
   datetime currentDailyBar = iTime(_Symbol, PERIOD_D1, 0); // 取得當前日線 K 線的開盤時間
   if(currentDailyBar != g_LastBarDaily && currentDailyBar != 0) // 若日線有新 K 線開盤
   {
      g_LastBarDaily = currentDailyBar; // 更新紀錄的日線時間
      UpdateDailyFilters(); // 重新計算日線過濾指標
   }

   //--- 檢查是否有新的 8H K 線收盤 (主要交易邏輯觸發點)
   datetime currentBar8H = iTime(_Symbol, PERIOD_H8, 0); // 取得當前 8H K 線的開盤時間
   if(currentBar8H != g_LastBar8H && currentBar8H != 0) // 若 8H 有新 K 線開盤 (代表前一根已收盤)
   {
      g_LastBar8H = currentBar8H; // 更新紀錄 of 8H 時間
      ProcessNew8HBar(); // 執行 8H 訊號判定與交易
      SavePersistentState(); // 每次 8H 判定後儲存狀態
   }
}

//+------------------------------------------------------------------+
//| 更新日線過濾指標 (Daily Filter Update)                            |
//| 在每日新 K 線開盤時呼叫，使用 T-1 數據計算                       |
//+------------------------------------------------------------------+
void UpdateDailyFilters()
{
   //--- 讀取日線 MA 指標值 (使用 bar[1] = 昨日已收盤 K 線的數據)
   double ma50_buf[1], ma20_buf[1], ma60_buf[1]; // 宣告緩衝陣列
   if(CopyBuffer(g_hMA50D, 0, 1, 1, ma50_buf) < 1) return; // 讀取昨日 50MA 值，失敗則返回
   if(CopyBuffer(g_hMA20D, 0, 1, 1, ma20_buf) < 1) return; // 讀取昨日 20MA 值，失敗則返回
   if(CopyBuffer(g_hMA60D, 0, 1, 1, ma60_buf) < 1) return; // 讀取昨日 60MA 值，失敗則返回

   double dailyMA50 = ma50_buf[0]; // 昨日日線 50MA 值
   double dailyMA20 = ma20_buf[0]; // 昨日日線 20MA 值
   double dailyMA60 = ma60_buf[0]; // 昨日日線 60MA 值

   //--- 讀取昨日黃金日線收盤價 (bar[1])
   double goldClose = iClose(_Symbol, PERIOD_D1, 1); // 昨日黃金收盤價
   if(goldClose == 0) return; // 若無法取得則返回

   //--- 計算日線大趨勢過濾狀態 (Regime)
   g_RegimeBull = (goldClose > dailyMA50); // 昨日收盤 > 50MA 則為牛市

   //--- 計算跨市場超額動能 Alpha (需要 DXY 數據)
   double alpha1 = 0, alpha5 = 0, alpha10 = 0; // 初始化三個 Alpha 值
   bool alphaValid = CalculateAlpha(alpha1, alpha5, alpha10); // 計算 Alpha 指標

   //--- 計算加倉動能過濾 (Pyramid Filter)
   if(alphaValid) // 若 Alpha 計算成功
   {
      g_PyramidLongOK  = (alpha1 > 0) && (alpha5 > 0) && (alpha10 > 0) && (dailyMA20 > dailyMA60); // 加多條件
      g_PyramidShortOK = (alpha1 < 0) && (alpha5 < 0) && (alpha10 < 0) && (dailyMA20 < dailyMA60); // 加空條件
   }
   else // Alpha 無法計算 (可能 DXY 數據不可用)
   {
      g_PyramidLongOK  = false; // 禁止加多
      g_PyramidShortOK = false; // 禁止加空
   }

   g_DailyReady = true; // 標記日線指標已就緒

   //--- 印出日線過濾狀態
   PrintFormat("📊 [日線更新] Regime=%s | MA50=%.2f | Close=%.2f | PyramidL=%s PyramidS=%s", // 狀態日誌
               g_RegimeBull ? "Bull🐂" : "Bear🐻", dailyMA50, goldClose, // 印出趨勢與價格
               g_PyramidLongOK ? "✅" : "❌", g_PyramidShortOK ? "✅" : "❌"); // 印出加倉狀態
}

//+------------------------------------------------------------------+
//| 取得有效的 DXY 美元指數商品名稱 (自動搜尋經紀商相符代號)         |
//+------------------------------------------------------------------+
string GetValidDXYSymbol()
{
   if(SymbolSelect(InpDXYSymbol, true)) return InpDXYSymbol; // 若用戶指定之商品存在直接使用
   string candidates[] = {"DXY", "USDX", "USDOLLAR", "DXY_U6", "USDINDEX", "DXY.ecn", "DXY!"}; // 備選商品代號
   for(int i = 0; i < ArraySize(candidates); i++) // 遍歷備選清單
   {
      if(SymbolSelect(candidates[i], true)) return candidates[i]; // 找到可用商品即回傳
   }
   return InpDXYSymbol; // 若皆找不到則回傳用戶設定值
}

//+------------------------------------------------------------------+
//| 計算跨市場超額動能 Alpha 指標                                      |
//| 回傳值：true = 計算成功, false = DXY 數據不可用                   |
//+------------------------------------------------------------------+
bool CalculateAlpha(double &alpha1, double &alpha5, double &alpha10)
{
   string dxySym = GetValidDXYSymbol(); // 🛡️ 取得有效的 DXY 商品代號

   //--- 讀取黃金日線收盤價序列 (bar[1] 到 bar[11]，共需 12 根)
   double goldCloses[12]; // 宣告黃金收盤價陣列
   for(int i = 0; i < 12; i++) // 迴圈讀取 12 根日線收盤價
   {
      goldCloses[i] = iClose(_Symbol, PERIOD_D1, i + 1); // 從 bar[1] 開始讀取 (昨日)
      if(goldCloses[i] == 0) return false; // 若任一根為 0 則返回失敗
   }

   //--- 讀取 DXY 日線收盤價序列 (bar[1] 到 bar[11])
   double dxyCloses[12]; // 宣告 DXY 收盤價陣列
   for(int i = 0; i < 12; i++) // 迴圈讀取 12 根 DXY 日線收盤價
   {
      dxyCloses[i] = iClose(dxySym, PERIOD_D1, i + 1); // 🛡️ 使用選定之 DXY 商品代號
      if(dxyCloses[i] == 0) return false; // 若任一根為 0 則返回失敗
   }

   //--- 計算 Alpha_1 (1日動能差)
   // goldCloses[0] = 昨日收盤, goldCloses[1] = 前天收盤
   double goldRet1 = (goldCloses[0] - goldCloses[1]) / goldCloses[1]; // 黃金 1 日報酬率
   double dxyRet1  = (dxyCloses[0]  - dxyCloses[1])  / dxyCloses[1];  // DXY 1 日報酬率
   alpha1 = goldRet1 - dxyRet1; // Alpha_1 = 黃金報酬率 - DXY 報酬率

   //--- 計算 Alpha_5 (5日動能差)
   // goldCloses[0] = 昨日收盤, goldCloses[5] = 6天前收盤
   double goldRet5 = (goldCloses[0] - goldCloses[5]) / goldCloses[5]; // 黃金 5 日報酬率
   double dxyRet5  = (dxyCloses[0]  - dxyCloses[5])  / dxyCloses[5];  // DXY 5 日報酬率
   alpha5 = goldRet5 - dxyRet5; // Alpha_5

   //--- 計算 Alpha_10 (10日動能差)
   // goldCloses[0] = 昨日收盤, goldCloses[10] = 11天前收盤
   double goldRet10 = (goldCloses[0] - goldCloses[10]) / goldCloses[10]; // 黃金 10 日報酬率
   double dxyRet10  = (dxyCloses[0]  - dxyCloses[10])  / dxyCloses[10];  // DXY 10 日報酬率
   alpha10 = goldRet10 - dxyRet10; // Alpha_10

   return true; // 計算成功回傳 true
}

//+------------------------------------------------------------------+
//| 處理新 8H K 線收盤 (核心交易邏輯)                                  |
//| 當偵測到新 8H K 線開盤時呼叫，表示前一根 8H K 線剛收盤            |
//+------------------------------------------------------------------+
void ProcessNew8HBar()
{
   if(!g_DailyReady) return; // 若日線指標尚未就緒則不執行

   //--- 🛡️ 雙重保險：如果持倉大於 0 但停損價為 0，立即重構停損價
   int totalEAPos = CountPositionsByEA(); // 統計本 EA 當前總持倉數量
   if(totalEAPos > 0 && g_MainStopPrice == 0.0) // 若有持倉但停損價為零
   {
      ReconstructStopPrices(); // 啟動歷史軌跡重構
   }

   //--- 讀取 8H 指標數據 (使用 bar[1] = 剛收盤的那根 K 線)
   double ma8h_buf[1], atr8h_buf[1]; // 宣告指標緩衝陣列
   if(CopyBuffer(g_hMA8H, 0, 1, 1, ma8h_buf) < 1) return;   // 讀取 8H MA 值
   if(CopyBuffer(g_hATR8H, 0, 1, 1, atr8h_buf) < 1) return;  // 讀取 8H ATR 值

   double ma8h  = ma8h_buf[0];  // 剛收盤的 8H K 線之 30SMA 值
   double atr8h = atr8h_buf[0]; // 剛收盤的 8H K 線之 ATR14 值

   //--- 讀取 8H K 線 OHLC 數據
   double t_close     = iClose(_Symbol, PERIOD_H8, 1); // 剛收盤的 8H 收盤價 (bar[1])
   double t_high      = iHigh(_Symbol, PERIOD_H8, 1);  // 剛收盤的 8H 最高價 (bar[1])
   double t_low       = iLow(_Symbol, PERIOD_H8, 1);   // 剛收盤的 8H 最低價 (bar[1])
   double t_prev_close = iClose(_Symbol, PERIOD_H8, 2); // 前一根 8H 收盤價 (bar[2])
   double t_prev_high = iHigh(_Symbol, PERIOD_H8, 2);  // 前一根 8H 最高價 (bar[2])
   double t_prev_low  = iLow(_Symbol, PERIOD_H8, 2);   // 前一根 8H 最低價 (bar[2])

   if(t_close == 0 || t_prev_close == 0) return; // 若數據無效則返回

   //--- 計算 8H 動能指標
   double dy_raw = t_close - t_prev_close; // 一階差分 (價格變動方向)
   bool sig_long_8h = (t_close > ma8h) && (dy_raw > 0); // 8H 多頭動能確認訊號

   //--- 計算停損初始價位
   double longStopInit  = MathMin(t_low, t_prev_low) - 1.0 * atr8h; // 多單初始停損價
   double shortStopInit = MathMax(t_high, t_prev_high) + 1.0 * atr8h; // 空單初始停損價

   //--- 偵測當前持倉狀態
   bool hasMainLong   = HasPositionByMagic(InpMagicMain, POSITION_TYPE_BUY);     // 是否持有主多單
   bool hasMainShort  = HasPositionByMagic(InpMagicMain, POSITION_TYPE_SELL);     // 是否持有主空單
   bool hasPyrLong    = HasPositionByMagic(InpMagicPyramid, POSITION_TYPE_BUY);   // 是否持有加多單
   bool hasPyrShort   = HasPositionByMagic(InpMagicPyramid, POSITION_TYPE_SELL);  // 是否持有加空單
   bool hasMainPos    = hasMainLong || hasMainShort; // 是否持有任一主部位
   bool hasPyrPos     = hasPyrLong || hasPyrShort;   // 是否持有任一加倉部位
   totalEAPos    = CountPositionsByEA(); // 🛡️ 更新本 EA 當前總持倉數量

   //--- 🛡️ 絕對安全閘：若持倉已達上限 2 手，僅允許平倉操作
   if(totalEAPos > 2) // 若超過 2 個持倉 (異常狀態)
   {
      PrintFormat("🚨 [安全警報] 偵測到 %d 個持倉，超過上限 2！強制平倉所有部位", totalEAPos); // 警報
      ClosePositionsByMagic(InpMagicMain);    // 平倉主部位
      ClosePositionsByMagic(InpMagicPyramid);  // 平倉加倉部位
      g_MainStopPrice = 0.0;    // 重設停損
      g_PyramidStopPrice = 0.0;  // 重設加倉停損
      if(InpEnableAlerts) Alert("🚨 Gold 8H: 持倉超過上限，已強制全數平倉！"); // 提醒
      return; // 直接返回，本期不做任何交易
   }

   //--- 印出 8H 訊號日誌
   PrintFormat("🕐 [8H 訊號] Close=%.2f | MA8H=%.2f | dy=%.2f | sig_long=%s | Regime=%s | 持倉數=%d", // 日誌
               t_close, ma8h, dy_raw, sig_long_8h ? "True" : "False", // 印出價格與指標
               g_RegimeBull ? "Bull" : "Bear", totalEAPos); // 印出趨勢狀態與持倉數

   //=================================================================
   // A. 多單方向策略 (當 Regime == Bull 時)
   //=================================================================
   // 1. 多頭持倉管理 (獨立執行，不受 Regime 限制)
   //=================================================================
   if(hasMainLong) // 已持有主多單
   { // 開始處理多頭持倉
      //--- 檢查多單出場條件
      bool exitByStop   = (t_close < g_MainStopPrice);        // 主停損破位
      bool exitBySignal = (!sig_long_8h);                      // 8H 信號轉空

      if(exitByStop || exitBySignal) // 滿足任一出場條件
      { // 執行多單全數平倉
         string reason = exitByStop ? "主停損破位" : "8H 信號轉空"; // 出場原因
         PrintFormat("🔴 [多單出場] 原因: %s | Close=%.2f | StopPrice=%.2f", reason, t_close, g_MainStopPrice); // 印出出場日誌

         ClosePositionsByMagic(InpMagicMain);    // 平倉主多單
         ClosePositionsByMagic(InpMagicPyramid);  // 平倉加多單 (若有)
         g_MainStopPrice = 0.0;    // 重設主部位停損價
         g_PyramidStopPrice = 0.0;  // 重設加倉停損價

         if(InpEnableAlerts) Alert("🔴 Gold 8H: 多單全數平倉 - ", reason); // 發送提醒
      } // 結束多單全數平倉
      else // 持倉保留，更新移動停損與加倉
      { // 處理移動停損與加倉
         //--- 移動停損上調邏輯 (當期收盤 > 前期最高價時觸發)
         if(t_close > t_prev_high) // 創新高條件
         { // 上調停損價位
            double newStop = MathMin(t_low, t_prev_low) - 1.0 * atr8h; // 計算新停損價
            if(newStop > g_MainStopPrice) // 新停損價高於舊停損價 (只升不降)
            { // 上調主部位停損
               g_MainStopPrice = newStop; // 上調主部位停損價
               PrintFormat("📈 [多單停損上調] 新停損=%.2f | ATR=%.2f", g_MainStopPrice, atr8h); // 日誌
            } // 結束主部位停損上調
            if(hasPyrLong && newStop > g_PyramidStopPrice) // 加多部位停損同步上調
            { // 上調加倉停損
               g_PyramidStopPrice = newStop; // 上調加倉停損價
            } // 結束加倉停損上調
         } // 結束創新高判斷

         //--- 加多單獨立停損檢查
         if(hasPyrLong && t_close < g_PyramidStopPrice && g_PyramidStopPrice > 0) // 收盤跌破加倉停損但未破主停損
         { // 僅平倉加多單
            PrintFormat("🟡 [加多單獨停損] Close=%.2f < PyramidStop=%.2f", t_close, g_PyramidStopPrice); // 日誌
            ClosePositionsByMagic(InpMagicPyramid); // 僅平倉加多單
            g_PyramidStopPrice = 0.0; // 重設加倉停損價
            if(InpEnableAlerts) Alert("🟡 Gold 8H: 加多單單獨停損平倉"); // 發送提醒
         } // 結束加多單獨平倉
         //--- 加多單建倉邏輯 (若尚未加倉且日線與 Alpha 條件允許)
         else if(!hasPyrLong && InpEnablePyramid && g_PyramidLongOK && g_RegimeBull && totalEAPos < 2) // 🛡️ 加上持倉數量與 Regime 檢查
         { // 執行加多單建倉
            g_trade.SetExpertMagicNumber(InpMagicPyramid); // 切換 Magic Number 為加倉
            
            //--- 計算動態加碼手數 (當 Alpha10 > 3% 時放大至 2.0 倍)
            double pyrLot = NormalizeLot(InpLotSize); // 預設加碼手數等於基底手數
            double a1 = 0, a5 = 0, a10 = 0; // 宣告 Alpha 變數
            if(CalculateAlpha(a1, a5, a10) && a10 > InpAlphaBoostThresh) // 若計算成功且 Alpha10 > 3%
            { // 觸發強勢加碼手數放大
               pyrLot = NormalizeLot(InpLotSize * InpPyramidBoostMultiplier); // 🛡️ 使用 NormalizeLot 規範手數
            } // 結束動態手數判定

            if(g_trade.Buy(pyrLot, _Symbol, 0, 0, 0, "Pyramid_Long")) // 市價買入加多
            { // 寫入加倉初始停損
               g_PyramidStopPrice = longStopInit; // 設定加倉初始停損價
               PrintFormat("🟢 [加多單進場] 手數=%.2f (Alpha10=%.2f%%) | 停損=%.2f", pyrLot, a10 * 100.0, g_PyramidStopPrice); // 日誌
               if(InpEnableAlerts) Alert("🟢 Gold 8H: 加多單進場 (手數:", DoubleToString(pyrLot, 2), ")"); // 發送提醒
            } // 結束買入
            g_trade.SetExpertMagicNumber(InpMagicMain); // 切換回主部位 Magic Number
         } // 結束加多建倉
      } // 結束持倉保留處理
   } // 結束多頭持倉管理

   //=================================================================
   // 2. 空頭持倉管理 (獨立執行，不受 Regime 限制)
   //=================================================================
   if(hasMainShort) // 已持有主空單
   { // 開始處理空頭持倉
      //--- 檢查空單出場條件
      bool exitByStop   = (t_close > g_MainStopPrice);        // 主停損破位
      bool exitBySignal = (sig_long_8h);                       // 8H 信號轉多

      if(exitByStop || exitBySignal) // 滿足任一出場條件
      { // 執行空單全數平倉
         string reason = exitByStop ? "主停損破位" : "8H 信號轉多"; // 出場原因
         PrintFormat("🔴 [空單出場] 原因: %s | Close=%.2f | StopPrice=%.2f", reason, t_close, g_MainStopPrice); // 印出出場日誌

         ClosePositionsByMagic(InpMagicMain);    // 平倉主空單
         ClosePositionsByMagic(InpMagicPyramid);  // 平倉加空單 (若有)
         g_MainStopPrice = 0.0;    // 重設主部位停損價
         g_PyramidStopPrice = 0.0;  // 重設加倉停損價

         if(InpEnableAlerts) Alert("🔴 Gold 8H: 空單全數平倉 - ", reason); // 發送提醒
      } // 結束空單全數平倉
      else // 持倉保留，更新移動停損與加倉
      { // 處理移動停損與加倉
         //--- 移動停損下調邏輯 (當期收盤 < 前期最低價時觸發)
         if(t_close < t_prev_low) // 創新低條件
         { // 下調停損價位
            double newStop = MathMax(t_high, t_prev_high) + 1.0 * atr8h; // 計算新停損價
            if(newStop < g_MainStopPrice || g_MainStopPrice == 0) // 新停損價低於舊停損價 (只降不升)
            { // 下調主部位停損
               g_MainStopPrice = newStop; // 下調主部位停損價
               PrintFormat("📉 [空單停損下調] 新停損=%.2f | ATR=%.2f", g_MainStopPrice, atr8h); // 日誌
            } // 結束主部位停損下調
            if(hasPyrShort && (newStop < g_PyramidStopPrice || g_PyramidStopPrice == 0)) // 加空部位停損同步下調
            { // 下調加倉停損
               g_PyramidStopPrice = newStop; // 下調加倉停損價
            } // 結束加倉停損下調
         } // 結束創新低判斷

         //--- 加空單獨立停損檢查
         if(hasPyrShort && t_close > g_PyramidStopPrice && g_PyramidStopPrice > 0) // 收盤突破加倉停損但未破主停損
         { // 僅平倉加空單
            PrintFormat("🟡 [加空單獨停損] Close=%.2f > PyramidStop=%.2f", t_close, g_PyramidStopPrice); // 日誌
            ClosePositionsByMagic(InpMagicPyramid); // 僅平倉加空單
            g_PyramidStopPrice = 0.0; // 重設加倉停損價
            if(InpEnableAlerts) Alert("🟡 Gold 8H: 加空單單獨停損平倉"); // 發送提醒
         } // 結束加空單獨平倉
         //--- 加空單建倉邏輯 (若尚未加倉且日線與 Alpha 條件允許)
         else if(!hasPyrShort && InpEnablePyramid && g_PyramidShortOK && !g_RegimeBull && totalEAPos < 2) // 🛡️ 加上持倉數量與 Regime 檢查
         { // 執行加空單建倉
            g_trade.SetExpertMagicNumber(InpMagicPyramid); // 切換 Magic Number 為加倉
            
            //--- 計算動態加碼手數 (當 Alpha10 < -3% 時放大至 2.0 倍)
            double pyrLot = NormalizeLot(InpLotSize); // 預設加碼手數等於基底手數
            double a1 = 0, a5 = 0, a10 = 0; // 宣告 Alpha 變數
            if(CalculateAlpha(a1, a5, a10) && a10 < -InpAlphaBoostThresh) // 若計算成功且 Alpha10 < -3%
            { // 觸發強勢加碼手數放大
               pyrLot = NormalizeLot(InpLotSize * InpPyramidBoostMultiplier); // 🛡️ 使用 NormalizeLot 規範手數
            } // 結束動態手數判定

            if(g_trade.Sell(pyrLot, _Symbol, 0, 0, 0, "Pyramid_Short")) // 市價賣出開空
            { // 寫入加倉初始停損
               g_PyramidStopPrice = shortStopInit; // 設定加倉初始停損價
               PrintFormat("🔻 [加空單進場] 手數=%.2f (Alpha10=%.2f%%) | 停損=%.2f", pyrLot, a10 * 100.0, g_PyramidStopPrice); // 日誌
               if(InpEnableAlerts) Alert("🔻 Gold 8H: 加空單進場 (手數:", DoubleToString(pyrLot, 2), ")"); // 發送提醒
            } // 結束賣出
            g_trade.SetExpertMagicNumber(InpMagicMain); // 切換回主部位 Magic Number
         } // 結束加空建倉
      } // 結束持倉保留處理
   } // 結束空頭持倉管理

   //=================================================================
   // 3. 新建主部位邏輯 (當前無持倉時，依據 Regime 與 8H 動能入場)
   //=================================================================
   totalEAPos = CountPositionsByEA(); // 重新統計最新總持倉數
   if(totalEAPos == 0) // 當前無任何持倉
   { // 開始檢查新建主部位
      double mainLot = NormalizeLot(InpLotSize); // 🛡️ 規範主部位手數
      if(g_RegimeBull && sig_long_8h) // 牛市環境且 8H 動能做多
      { // 執行買入主多單
         g_trade.SetExpertMagicNumber(InpMagicMain); // 確保使用主部位 Magic Number
         if(g_trade.Buy(mainLot, _Symbol, 0, 0, 0, "Main_Long")) // 市價買入
         { // 寫入初始停損
            g_MainStopPrice = longStopInit; // 設定主多單初始停損價
            PrintFormat("🟢 [主多單進場] 手數=%.2f | 停損=%.2f | MA8H=%.2f", mainLot, g_MainStopPrice, ma8h); // 日誌
            if(InpEnableAlerts) Alert("🟢 Gold 8H: 主多單進場 @ ", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_ASK), 2)); // 提醒
         } // 結束買入
      } // 結束主多單建倉
      else if(!g_RegimeBull && !sig_long_8h) // 熊市環境且 8H 動能做空
      { // 執行賣出主空單
         g_trade.SetExpertMagicNumber(InpMagicMain); // 確保使用主部位 Magic Number
         if(g_trade.Sell(mainLot, _Symbol, 0, 0, 0, "Main_Short")) // 市價賣出開空
         { // 寫入初始停損
            g_MainStopPrice = shortStopInit; // 設定主空單初始停損價
            PrintFormat("🔻 [主空單進場] 手數=%.2f | 停損=%.2f | MA8H=%.2f", mainLot, g_MainStopPrice, ma8h); // 日誌
            if(InpEnableAlerts) Alert("🔻 Gold 8H: 主空單進場 @ ", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_BID), 2)); // 提醒
         } // 結束賣出
      } // 結束主空單建倉
   } // 結束新建主部位判斷
}

//+------------------------------------------------------------------+
//| 檢查是否持有指定 Magic Number 與方向的部位                        |
//+------------------------------------------------------------------+
bool HasPositionByMagic(ulong magic, ENUM_POSITION_TYPE posType)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--) // 遍歷所有持倉 (倒序)
   {
      ulong ticket = PositionGetTicket(i); // 取得持倉票號
      if(ticket == 0) continue; // 無效票號則跳過

      if(PositionGetString(POSITION_SYMBOL) == _Symbol && // 確認商品一致
         PositionGetInteger(POSITION_MAGIC) == (long)magic && // 確認 Magic Number 一致
         PositionGetInteger(POSITION_TYPE) == posType) // 確認方向一致
      {
         return true; // 找到符合條件的持倉
      }
   }
   return false; // 未找到符合條件的持倉
}

//+------------------------------------------------------------------+
//| 平倉所有指定 Magic Number 的持倉 (含重試與驗證)                    |
//+------------------------------------------------------------------+
void ClosePositionsByMagic(ulong magic)
{
   int maxRetry = 3; // 最大重試次數
   for(int attempt = 0; attempt < maxRetry; attempt++) // 重試迴圈
   {
      bool foundAny = false; // 是否找到需要平倉的部位
      for(int i = PositionsTotal() - 1; i >= 0; i--) // 遍歷所有持倉 (倒序)
      {
         ulong ticket = PositionGetTicket(i); // 取得持倉票號
         if(ticket == 0) continue; // 無效票號則跳過

         if(PositionGetString(POSITION_SYMBOL) == _Symbol && // 確認商品一致
            PositionGetInteger(POSITION_MAGIC) == (long)magic) // 確認 Magic Number 一致
         {
            foundAny = true; // 標記找到部位
            bool result = g_trade.PositionClose(ticket); // 市價平倉此持倉
            if(result) // 平倉成功
            {
               PrintFormat("   ✂️ 平倉成功 Ticket=%d | Magic=%d", ticket, magic); // 成功日誌
            }
            else // 平倉失敗
            {
               PrintFormat("   ❌ 平倉失敗 Ticket=%d | Magic=%d | Error=%d | 第 %d 次嘗試", // 失敗日誌
                           ticket, magic, GetLastError(), attempt + 1); // 印出錯誤碼
            }
         }
      }
      if(!foundAny) break; // 若沒有找到任何需要平倉的部位則結束重試
      Sleep(200); // 等待 200ms 讓伺服器處理完畢再重試
   }
}

//+------------------------------------------------------------------+
//| 🛡️ 統計本 EA 在當前商品上的總持倉數量                            |
//+------------------------------------------------------------------+
int CountPositionsByEA()
{
   int count = 0; // 持倉計數器
   for(int i = PositionsTotal() - 1; i >= 0; i--) // 遍歷所有持倉
   {
      ulong ticket = PositionGetTicket(i); // 取得持倉票號
      if(ticket == 0) continue; // 無效票號則跳過

      if(PositionGetString(POSITION_SYMBOL) == _Symbol) // 確認商品一致
      {
         long posMagic = PositionGetInteger(POSITION_MAGIC); // 取得 Magic Number
         if(posMagic == (long)InpMagicMain || posMagic == (long)InpMagicPyramid) // 屬於本 EA
         {
            count++; // 計數加一
         }
      }
   }
   return count; // 回傳持倉數量
}

//+------------------------------------------------------------------+
//| 儲存持久化狀態至 GlobalVariable (防止 EA 重啟遺失數據)            |
//+------------------------------------------------------------------+
void SavePersistentState()
{
   GlobalVariableSet(g_gvKeyMainStop, g_MainStopPrice);       // 儲存主部位停損價
   GlobalVariableSet(g_gvKeyPyramidStop, g_PyramidStopPrice); // 儲存加倉停損價
   GlobalVariableSet(g_gvKeyLastBar8H, (double)g_LastBar8H);  // 儲存上次 8H 時間
}

//+------------------------------------------------------------------+
//| 從 GlobalVariable 載入持久化狀態                                  |
//+------------------------------------------------------------------+
void LoadPersistentState()
{
   if(GlobalVariableCheck(g_gvKeyMainStop)) // 檢查主停損鍵是否存在
   {
      g_MainStopPrice = GlobalVariableGet(g_gvKeyMainStop); // 載入主部位停損價
   }
   if(GlobalVariableCheck(g_gvKeyPyramidStop)) // 檢查加倉停損鍵是否存在
   {
      g_PyramidStopPrice = GlobalVariableGet(g_gvKeyPyramidStop); // 載入加倉停損價
   }
   if(GlobalVariableCheck(g_gvKeyLastBar8H)) // 檢查上次 8H 時間鍵是否存在
   {
      g_LastBar8H = (datetime)GlobalVariableGet(g_gvKeyLastBar8H); // 載入上次 8H 時間
   }

   PrintFormat("💾 [狀態恢復] MainStop=%.2f | PyramidStop=%.2f | LastBar8H=%s", // 印出恢復日誌
               g_MainStopPrice, g_PyramidStopPrice, TimeToString(g_LastBar8H)); // 印出狀態值
}

//+------------------------------------------------------------------+
//| 取得指定 Shift 處的 8H ATR14 值                                  |
//+------------------------------------------------------------------+
double GetATRValue(int shift)
{
   double atr_buf[1]; // 宣告緩衝陣列
   if(CopyBuffer(g_hATR8H, 0, shift, 1, atr_buf) < 1) // 複製指標數據
   {
      return 0.0; // 複製失敗回傳 0
   }
   return atr_buf[0]; // 回傳 ATR 值
}

//+------------------------------------------------------------------+
//| 計算指定開倉時間在歷史上的移動停損價                               |
//+------------------------------------------------------------------+
double CalculateStopPriceAtTime(ENUM_POSITION_TYPE posType, datetime entryTime)
{
   int entryShift = iBarShift(_Symbol, PERIOD_H8, entryTime, false); // 取得開倉時間對應的 8H K 線 shift
   if(entryShift == -1) return 0.0; // 取得失敗回傳 0

   int sigShift = entryShift; // 訊號 K 線預設為開倉 K 線
   datetime entryBarTime = iTime(_Symbol, PERIOD_H8, entryShift); // 取得開倉 K 線時間
   if(entryTime <= entryBarTime) // 如果剛好在開盤時開倉
   {
      sigShift = entryShift + 1; // 訊號為前一根 K 線
   }

   double atr_val = GetATRValue(sigShift); // 取得訊號 K 線的 ATR
   if(atr_val == 0) return 0.0; // 指標數據未就緒

   double stopPrice = 0.0; // 初始化停損價

   if(posType == POSITION_TYPE_BUY) // 多單
   {
      double low1 = iLow(_Symbol, PERIOD_H8, sigShift); // 訊號低點
      double low2 = iLow(_Symbol, PERIOD_H8, sigShift + 1); // 前一期低點
      stopPrice = MathMin(low1, low2) - 1.0 * atr_val; // 初始多單停損

      for(int s = sigShift - 1; s >= 1; s--) // 從訊號下一期向現在滾動更新
      {
         double s_close = iClose(_Symbol, PERIOD_H8, s); // 當期收盤價
         double s_prev_high = iHigh(_Symbol, PERIOD_H8, s + 1); // 前一期高點
         if(s_close > s_prev_high) // 突破最高價
         {
            double s_low1 = iLow(_Symbol, PERIOD_H8, s); // 當期低點
            double s_low2 = iLow(_Symbol, PERIOD_H8, s + 1); // 前期低點
            double s_atr = GetATRValue(s); // 當期 ATR
            if(s_atr > 0) // ATR 有效
            {
               double newStop = MathMin(s_low1, s_low2) - 1.0 * s_atr; // 新停損價
               if(newStop > stopPrice) stopPrice = newStop; // 只升不降
            }
         }
      }
   }
   else if(posType == POSITION_TYPE_SELL) // 空單
   {
      double high1 = iHigh(_Symbol, PERIOD_H8, sigShift); // 訊號高點
      double high2 = iHigh(_Symbol, PERIOD_H8, sigShift + 1); // 前一期高點
      stopPrice = MathMax(high1, high2) + 1.0 * atr_val; // 初始空單停損

      for(int s = sigShift - 1; s >= 1; s--) // 從訊號下一期向現在滾動更新
      {
         double s_close = iClose(_Symbol, PERIOD_H8, s); // 當期收盤價
         double s_prev_low = iLow(_Symbol, PERIOD_H8, s + 1); // 前一期低點
         if(s_close < s_prev_low) // 跌破最低價
         {
            double s_high1 = iHigh(_Symbol, PERIOD_H8, s); // 當期高點
            double s_high2 = iHigh(_Symbol, PERIOD_H8, s + 1); // 前期高點
            double s_atr = GetATRValue(s); // 當期 ATR
            if(s_atr > 0) // ATR 有效
            {
               double newStop = MathMax(s_high1, s_high2) + 1.0 * s_atr; // 新停損價
               if(newStop < stopPrice || stopPrice == 0.0) stopPrice = newStop; // 只降不升
            }
         }
      }
   }

   return stopPrice; // 回傳重構的停損價
}

//+------------------------------------------------------------------+
//| 當斷線重啟或數據遺失時，自動重構當前持倉的移動停損價             |
//+------------------------------------------------------------------+
void ReconstructStopPrices()
{
   Print("🔄 [狀態重構] 偵測到有持倉但停損價為零，啟動歷史軌跡重構..."); // 日誌

   bool mainFound = false; // 是否找到主部位
   bool pyrFound = false; // 是否找到加倉部位

   for(int i = PositionsTotal() - 1; i >= 0; i--) // 遍歷所有持倉
   {
      ulong ticket = PositionGetTicket(i); // 取得持倉票號
      if(ticket == 0) continue; // 無效票號
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue; // 確認商品一致

      long magic = PositionGetInteger(POSITION_MAGIC); // 取得 Magic Number
      ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE); // 取得持倉方向
      datetime entryTime = (datetime)PositionGetInteger(POSITION_TIME); // 取得開倉時間

      if(magic == (long)InpMagicMain) // 主部位
      {
         double stop = CalculateStopPriceAtTime(posType, entryTime); // 計算歷史停損
         if(stop > 0) // 成功計算
         {
            g_MainStopPrice = stop; // 更新主部位停損價
            mainFound = true; // 標記找到
            PrintFormat("🛡️ 成功重構主部位停損價: %.2f (開倉時間: %s)", g_MainStopPrice, TimeToString(entryTime)); // 成功日誌
         }
      }
      else if(magic == (long)InpMagicPyramid) // 加倉部位
      {
         double stop = CalculateStopPriceAtTime(posType, entryTime); // 計算歷史停損
         if(stop > 0) // 成功計算
         {
            g_PyramidStopPrice = stop; // 更新加倉部位停損價
            pyrFound = true; // 標記找到
            PrintFormat("🛡️ 成功重構加倉部位停損價: %.2f (開倉時間: %s)", g_PyramidStopPrice, TimeToString(entryTime)); // 成功日誌
         }
      }
   }

   if(!mainFound) g_MainStopPrice = 0.0; // 若沒找到則清零
   if(!pyrFound) g_PyramidStopPrice = 0.0; // 若沒找到則清零

   SavePersistentState(); // 立即儲存狀態至持久化空間
}
//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
