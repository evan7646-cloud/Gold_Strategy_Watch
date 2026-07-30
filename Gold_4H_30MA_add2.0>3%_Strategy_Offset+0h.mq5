//+------------------------------------------------------------------+
//|                        Gold_4H_30MA_add2.0>3%_Strategy_Offset0h.mq5 |
//|                               黃金 4H 30MA 多空混合策略 EA (+0h Offset) |
//|                               Version 2.00                        |
//+------------------------------------------------------------------+
#property copyright "Gold 4H 30MA Strategy (+0h Offset)" // 版權宣告
#property version   "2.00" // 版本號
#property description "黃金 4H 30MA 多空混合策略 EA (+0h 台北時間 00:00 偏移對齊)" // EA 描述文字
#property description "建議掛載至 XAUUSD 1H 圖表以精準在台北時間 00, 04, 08, 12, 16, 20 觸發" // 描述第二行

#include <Trade/Trade.mqh> // 引入 MQL5 標準交易函式庫

//+------------------------------------------------------------------+
//| 輸入參數 (Input Parameters)                                       |
//+------------------------------------------------------------------+
input group "===== 商品與圖表設定 =====" // 商品與圖表設定群組
// 📌 建議將此 EA 掛載到 XAUUSD 1H 圖表，程式會自動於台北時間 00, 04, 08, 12, 16, 20 時間點觸發 +0h 4H 邏輯
// 📌 DXY 僅用於計算 Alpha 動能指標（加倉過濾），不會對 DXY 下單
input string   InpDXYSymbol      = "USDX";          // DXY 商品名稱 (僅用於讀取報價計算 Alpha，不交易此商品)
input double   InpLotSize        = 0.10;             // 每筆交易手數 (預設改為 0.1 手，主部位與加倉各用此手數)

input group "===== 指標參數 =====" // 指標參數群組
input int      InpMA4H_Period    = 30;               // 4H 均線 (SMA) 週期 (預設 30MA)
input int      InpATR4H_Period   = 14;               // 4H ATR 週期 (預設 14ATR)
input int      InpMA50_Period    = 50;               // 日線 50MA 週期 (大趨勢過濾)
input int      InpMA20_Period    = 20;               // 日線 20MA 週期 (加倉過濾)
input int      InpMA60_Period    = 60;               // 日線 60MA 週期 (加倉過濾)

input group "===== 交易識別 =====" // 交易識別群組
input ulong    InpMagicMain      = 44440001;         // 主部位 Magic Number (專屬 4H 識別碼)
input ulong    InpMagicPyramid   = 44440002;         // 加倉部位 Magic Number (專屬 4H 識別碼)

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
datetime g_LastBar4H        = 0;      // 上一次已處理的 4H K 線開盤時間
datetime g_LastBarDaily     = 0;      // 上一次已處理的日線開盤時間

//--- 日線過濾器狀態 (Daily Filter State)
bool     g_RegimeBull       = false;  // 日線大趨勢是否為牛市 (Bull = true, Bear = false)
bool     g_PyramidLongOK    = false;  // 日線是否允許加多
bool     g_PyramidShortOK   = false;  // 日線是否允許加空
bool     g_DailyReady       = false;  // 日線指標是否已完成首次計算

//--- 指標句柄 (Indicator Handles)
int      g_hMA4H   = INVALID_HANDLE; // 4H 30SMA 指標句柄
int      g_hATR4H  = INVALID_HANDLE; // 4H ATR14 指標句柄
int      g_hMA50D  = INVALID_HANDLE; // 日線 50SMA 指標句柄
int      g_hMA20D  = INVALID_HANDLE; // 日線 20SMA 指標句柄
int      g_hMA60D  = INVALID_HANDLE; // 日線 60SMA 指標句柄

//--- 交易物件 (Trade Object)
CTrade   g_trade;                     // CTrade 交易執行物件

//--- GlobalVariable 持久化鍵名 (Persistence Keys)
string   g_gvKeyMainStop;            // 主部位停損價的 GlobalVariable 鍵名
string   g_gvKeyPyramidStop;         // 加倉部位停損價的 GlobalVariable 鍵名
string   g_gvKeyLastBar4H;           // 上次 4H K 線時間的 GlobalVariable 鍵名

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
   string prefix = "G4H_" + IntegerToString(InpMagicMain) + "_"; // 建立前綴字串
   g_gvKeyMainStop    = prefix + "MainStop"; // 主部位停損鍵名
   g_gvKeyPyramidStop = prefix + "PyramidStop"; // 加倉停損鍵名
   g_gvKeyLastBar4H   = prefix + "LastBar4H"; // 上次 4H 時間鍵名

   //--- 嘗試將 DXY 商品加入 Market Watch (確保可取得跨市場數據)
   if(!SymbolSelect(InpDXYSymbol, true)) // 加入 DXY 至 Market Watch
   {
      PrintFormat("⚠️ 警告：無法將 %s 加入 Market Watch，加倉過濾器將尋找備用商品", InpDXYSymbol); // 印出警告
   }

   //--- 建立 4H 時區指標句柄
   g_hMA4H = iMA(_Symbol, PERIOD_H4, InpMA4H_Period, 0, MODE_SMA, PRICE_CLOSE); // 建立 4H SMA 句柄
   if(g_hMA4H == INVALID_HANDLE) // 若建立失敗
   {
      PrintFormat("❌ 錯誤：無法建立 4H MA(%d) 指標句柄", InpMA4H_Period); // 印出錯誤
      return(INIT_FAILED); // 回傳初始化失敗
   }

   g_hATR4H = iATR(_Symbol, PERIOD_H4, InpATR4H_Period); // 建立 4H ATR 句柄
   if(g_hATR4H == INVALID_HANDLE) // 若建立失敗
   {
      Print("❌ 錯誤：無法建立 4H ATR 指標句柄"); // 印出錯誤
      return(INIT_FAILED); // 回傳初始化失敗
   }

   //--- 建立日線指標句柄
   g_hMA50D = iMA(_Symbol, PERIOD_D1, InpMA50_Period, 0, MODE_SMA, PRICE_CLOSE); // 建立日線 50SMA 句柄
   g_hMA20D = iMA(_Symbol, PERIOD_D1, InpMA20_Period, 0, MODE_SMA, PRICE_CLOSE); // 建立日線 20SMA 句柄
   g_hMA60D = iMA(_Symbol, PERIOD_D1, InpMA60_Period, 0, MODE_SMA, PRICE_CLOSE); // 建立日線 60SMA 句柄

   if(g_hMA50D == INVALID_HANDLE || g_hMA20D == INVALID_HANDLE || g_hMA60D == INVALID_HANDLE) // 若任意日線句柄建立失敗
   {
      Print("❌ 錯誤：無法建立日線 MA 指標句柄"); // 印出錯誤
      return(INIT_FAILED); // 回傳初始化失敗
   }

   //--- 設定交易參數
   g_trade.SetExpertMagicNumber(InpMagicMain); // 設定主部位預設 Magic Number
   g_trade.SetTypeFilling(GetValidFillingMode()); // 動態設定相符之訂單成交模式

   //--- 載入 GlobalVariable 持久化狀態 (重啟防失憶)
   LoadPersistentState(); // 載入停損價與狀態

   //--- 開機自動補單檢查：若當前無持倉，初始化時立即檢查最新完結 4H 訊號並自動補單
   UpdateDailyFilters(); // 預先更新日線趨勢過濾器
   ProcessNew4HBar(); // 立即執行 4H 訊號判定 (若無持倉且符合 12:00 空頭條件將自動補單)

   PrintFormat("🚀 Gold 4H 30MA Hybrid Strategy EA (+0h Offset) 初始化成功！[MagicMain=%d, MagicPyramid=%d]", InpMagicMain, InpMagicPyramid); // 印出成功日誌
   return(INIT_SUCCEEDED); // 回傳成功
}

//+------------------------------------------------------------------+
//| EA 反初始化函數 (OnDeinit)                                        |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   //--- 儲存當前狀態
   SavePersistentState(); // 儲存狀態至持久化空間

   //--- 釋放指標句柄
   if(g_hMA4H   != INVALID_HANDLE) IndicatorRelease(g_hMA4H); // 釋放 4H MA
   if(g_hATR4H  != INVALID_HANDLE) IndicatorRelease(g_hATR4H); // 釋放 4H ATR
   if(g_hMA50D  != INVALID_HANDLE) IndicatorRelease(g_hMA50D); // 釋放日 50MA
   if(g_hMA20D  != INVALID_HANDLE) IndicatorRelease(g_hMA20D); // 釋放日 20MA
   if(g_hMA60D  != INVALID_HANDLE) IndicatorRelease(g_hMA60D); // 釋放日 60MA

   PrintFormat("👋 EA 已終止執行 (原因碼=%d)，狀態已自動保存。", reason); // 日誌
}

//+------------------------------------------------------------------+
//| 持久化狀態載入 (LoadPersistentState)                             |
//+------------------------------------------------------------------+
void LoadPersistentState()
{
   if(GlobalVariableCheck(g_gvKeyMainStop)) // 檢查是否有主停損記錄
      g_MainStopPrice = GlobalVariableGet(g_gvKeyMainStop); // 讀取主停損
   if(GlobalVariableCheck(g_gvKeyPyramidStop)) // 檢查是否有加倉停損記錄
      g_PyramidStopPrice = GlobalVariableGet(g_gvKeyPyramidStop); // 讀取加倉停損
   if(GlobalVariableCheck(g_gvKeyLastBar4H)) // 檢查是否有 4H 時間記錄
      g_LastBar4H = (datetime)GlobalVariableGet(g_gvKeyLastBar4H); // 讀取 4H 時間

   PrintFormat("💾 [狀態載入] 主停損=%.2f | 加倉停損=%.2f | 上次4H時間=%s", 
               g_MainStopPrice, g_PyramidStopPrice, TimeToString(g_LastBar4H)); // 印出日誌
}

//+------------------------------------------------------------------+
//| 持久化狀態儲存 (SavePersistentState)                             |
//+------------------------------------------------------------------+
void SavePersistentState()
{
   GlobalVariableSet(g_gvKeyMainStop, g_MainStopPrice); // 寫入主停損
   GlobalVariableSet(g_gvKeyPyramidStop, g_PyramidStopPrice); // 寫入加倉停損
   GlobalVariableSet(g_gvKeyLastBar4H, (double)g_LastBar4H); // 寫入 4H 時間
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
//+------------------------------------------------------------------+
bool CalculateAlpha(double &alpha1, double &alpha5, double &alpha10)
{
   string dxySym = GetValidDXYSymbol(); // 取得有效的 DXY 商品代號

   double goldCloses[12]; // 宣告黃金收盤價陣列
   for(int i = 0; i < 12; i++) // 迴圈讀取 12 根日線收盤價
   {
      goldCloses[i] = iClose(_Symbol, PERIOD_D1, i + 1); // 從 bar[1] 開始讀取
      if(goldCloses[i] == 0) return false; // 若未準備好則回傳失敗
   }

   double dxyCloses[12]; // 宣告 DXY 收盤價陣列
   for(int i = 0; i < 12; i++) // 迴圈讀取 12 根 DXY 日線收盤價
   {
      dxyCloses[i] = iClose(dxySym, PERIOD_D1, i + 1); // 從 bar[1] 開始讀取
      if(dxyCloses[i] == 0) return false; // 若未準備好則回傳失敗
   }

   double g_ret1  = (goldCloses[0] - goldCloses[1])  / goldCloses[1]; // 黃金 1日收益
   double g_ret5  = (goldCloses[0] - goldCloses[5])  / goldCloses[5]; // 黃金 5日收益
   double g_ret10 = (goldCloses[0] - goldCloses[10]) / goldCloses[10]; // 黃金 10日收益

   double d_ret1  = (dxyCloses[0] - dxyCloses[1])  / dxyCloses[1]; // DXY 1日收益
   double d_ret5  = (dxyCloses[0] - dxyCloses[5])  / dxyCloses[5]; // DXY 5日收益
   double d_ret10 = (dxyCloses[0] - dxyCloses[10]) / dxyCloses[10]; // DXY 10日收益

   alpha1  = g_ret1  - d_ret1;  // Alpha 1D
   alpha5  = g_ret5  - d_ret5;  // Alpha 5D
   alpha10 = g_ret10 - d_ret10; // Alpha 10D

   return true; // 回傳成功
}

//+------------------------------------------------------------------+
//| 更新日線過濾器 (UpdateDailyFilters)                              |
//+------------------------------------------------------------------+
void UpdateDailyFilters()
{
   double ma50Array[1], ma20Array[1], ma60Array[1], dailyCloseArray[1]; // 宣告快取陣列

   if(CopyBuffer(g_hMA50D, 0, 1, 1, ma50Array) <= 0) return; // 讀取已完結之昨日 50MA (bar[1])
   if(CopyBuffer(g_hMA20D, 0, 1, 1, ma20Array) <= 0) return; // 讀取已完結之昨日 20MA (bar[1])
   if(CopyBuffer(g_hMA60D, 0, 1, 1, ma60Array) <= 0) return; // 讀取已完結之昨日 60MA (bar[1])

   dailyCloseArray[0] = iClose(_Symbol, PERIOD_D1, 1); // 讀取已完結之昨日日線收盤價
   if(dailyCloseArray[0] == 0) return; // 防零值

   double alpha1 = 0, alpha5 = 0, alpha10 = 0; // 宣告 Alpha 變數
   bool alphaOK = CalculateAlpha(alpha1, alpha5, alpha10); // 計算 Alpha

   g_RegimeBull = (dailyCloseArray[0] > ma50Array[0]); // 判定大趨勢 (牛市/熊市)

   if(alphaOK) // 若 Alpha 計算成功
   {
      g_PyramidLongOK  = (alpha1 > 0) && (alpha5 > 0) && (alpha10 > 0) && (ma20Array[0] > ma60Array[0]); // 判定加多過濾器
      g_PyramidShortOK = (alpha1 < 0) && (alpha5 < 0) && (alpha10 < 0) && (ma20Array[0] < ma60Array[0]); // 判定加空過濾器
   }
   else // 若 Alpha 數據不可用
   {
      g_PyramidLongOK  = (ma20Array[0] > ma60Array[0]); // 回退純 MA 過濾器
      g_PyramidShortOK = (ma20Array[0] < ma60Array[0]); // 回退純 MA 過濾器
   }

   g_DailyReady = true; // 標記日線過濾器已準備就緒
}

//+------------------------------------------------------------------+
//| 統計 EA 持倉數 (CountPositionsByEA)                               |
//+------------------------------------------------------------------+
int CountPositionsByEA(ulong &mainTicket, ulong &pyrTicket)
{
   int count = 0; // 初始化持倉計數
   mainTicket = 0; // 清空主部位票號
   pyrTicket  = 0; // 清空加倉部位票號

   for(int i = PositionsTotal() - 1; i >= 0; i--) // 遍歷當前所有持倉
   {
      ulong ticket = PositionGetTicket(i); // 取得持倉票號
      if(ticket <= 0) continue; // 若票號無效跳過

      if(PositionGetString(POSITION_SYMBOL) == _Symbol) // 確保為當前交易商品
      {
         ulong magic = PositionGetInteger(POSITION_MAGIC); // 取得 Magic Number
         if(magic == InpMagicMain) // 若為主部位
         {
            mainTicket = ticket; // 記錄主部位票號
            count++; // 計數加一
         }
         else if(magic == InpMagicPyramid) // 若為加倉部位
         {
            pyrTicket = ticket; // 記錄加倉部位票號
            count++; // 計數加一
         }
      }
   }
   return count; // 回傳持倉數量
}

//+------------------------------------------------------------------+
//| 平倉指定 Magic Number 之所有部位 (ClosePositionsByMagic)          |
//+------------------------------------------------------------------+
bool ClosePositionsByMagic(ulong magic)
{
   bool allClosed = true; // 預設全數成功
   g_trade.SetExpertMagicNumber(magic); // 切換 CTrade 之 Magic Number

   for(int i = PositionsTotal() - 1; i >= 0; i--) // 遍歷當前所有持倉
   {
      ulong ticket = PositionGetTicket(i); // 取得票號
      if(ticket <= 0) continue; // 若無效跳過

      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == magic) // 匹配商品與 Magic
      {
         if(!g_trade.PositionClose(ticket)) // 執行平倉
         {
            PrintFormat("❌ 平倉失敗 [Ticket=%d, Magic=%d]: %s", ticket, magic, g_trade.ResultComment()); // 日誌
            allClosed = false; // 標記失敗
         }
      }
   }
   return allClosed; // 回傳結果
}

//+------------------------------------------------------------------+
//| 歷史軌跡停損重構 (ReconstructStopPrices)                          |
//+------------------------------------------------------------------+
void ReconstructStopPrices()
{
   ulong mainTicket = 0, pyrTicket = 0; // 宣告票號變數
   int totalEAPos = CountPositionsByEA(mainTicket, pyrTicket); // 統計當前 EA 部位
   if(totalEAPos == 0) return; // 無持倉無需重構

   Print("🔄 [狀態重構] 正在為當前持倉重構歷史軌跡停損價..."); // 提示日誌

   datetime entryTime = 0; // 持倉進場時間
   ENUM_POSITION_TYPE posType = POSITION_TYPE_BUY; // 持倉方向

   if(mainTicket > 0 && PositionSelectByTicket(mainTicket)) // 選擇主部位
   {
      entryTime = (datetime)PositionGetInteger(POSITION_TIME); // 讀取進場時間
      posType   = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE); // 讀取方向
   }
   else if(pyrTicket > 0 && PositionSelectByTicket(pyrTicket)) // 若只有加倉部位
   {
      entryTime = (datetime)PositionGetInteger(POSITION_TIME); // 讀取進場時間
      posType   = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE); // 讀取方向
   }

   int startBarIndex = iBarShift(_Symbol, PERIOD_H4, entryTime, false); // 計算進場對應之 4H K 線索引
   if(startBarIndex < 0) startBarIndex = 100; // 防錯保護

   double stopPrice = 0.0; // 停損價變數
   for(int i = startBarIndex; i >= 1; i--) // 從進場 K 線正向重放至上一根完結 K 線
   {
      double h = iHigh(_Symbol, PERIOD_H4, i); // 取當時 High
      double l = iLow(_Symbol, PERIOD_H4, i); // 取當時 Low
      double h_prev = iHigh(_Symbol, PERIOD_H4, i + 1); // 取前 High
      double l_prev = iLow(_Symbol, PERIOD_H4, i + 1); // 取前 Low

      double atrArray[1]; // ATR 陣列
      if(CopyBuffer(g_hATR4H, 0, i, 1, atrArray) <= 0) continue; // 讀取當時 ATR
      double atr = atrArray[0]; // ATR 值

      if(posType == POSITION_TYPE_BUY) // 多頭軌跡
      {
         double initStop = MathMin(l, l_prev) - 1.0 * atr; // 計算初始停損
         if(stopPrice == 0.0 || initStop > stopPrice) stopPrice = initStop; // 首根賦值
         else if(iClose(_Symbol, PERIOD_H4, i) > h_prev) // 若突破前高
         {
            double newStop = MathMin(l, l_prev) - 1.0 * atr; // 計算新停損
            if(newStop > stopPrice) stopPrice = newStop; // 上移停損
         }
      }
      else // 空頭軌跡
      {
         double initStop = MathMax(h, h_prev) + 1.0 * atr; // 計算初始停損
         if(stopPrice == 0.0 || initStop < stopPrice) stopPrice = initStop; // 首根賦值
         else if(iClose(_Symbol, PERIOD_H4, i) < l_prev) // 若跌破前低
         {
            double newStop = MathMax(h, h_prev) + 1.0 * atr; // 計算新停損
            if(newStop < stopPrice) stopPrice = newStop; // 下移停損
         }
      }
   }

   if(mainTicket > 0) g_MainStopPrice = stopPrice; // 寫入主停損
   if(pyrTicket > 0)  g_PyramidStopPrice = stopPrice; // 寫入加倉停損

   SavePersistentState(); // 儲存持久化狀態
   PrintFormat("✅ [狀態重構完成] 計算出之移動停損價: %.2f", stopPrice); // 日誌
}

//+------------------------------------------------------------------+
//| 從 1H 數據精準合成 UTC +0h (00, 04, 08, 12, 16, 20) 之 N 根 4H K線數據 |
//+------------------------------------------------------------------+
bool GetUTC0h4H_BarData(int nBars, double &outOpen[], double &outHigh[], double &outLow[], double &outClose[])
{
   ArrayResize(outOpen, nBars);
   ArrayResize(outHigh, nBars);
   ArrayResize(outLow, nBars);
   ArrayResize(outClose, nBars);

   MqlRates rates1H[600]; // 宣告 1H 數據陣列
   int copied = CopyRates(_Symbol, PERIOD_H1, 0, 600, rates1H); // 從當前 K 線向後讀取 600 根 1H 數據
   if(copied < (nBars * 4 + 20)) return false; // 數據不足跳過

   // 步驟 1: 尋找當前 1H (bar[0]) 所在或之前的最新 +0h 4H 開盤點
   int startIdx = copied - 1;
   while(startIdx >= 0)
   {
      int gmtOffset = TimeGMTOffset(); // 讀取 GMT 偏移秒數
      datetime utcTime = rates1H[startIdx].time - gmtOffset; // 轉為 UTC 時間
      MqlDateTime dt;
      TimeToStruct(utcTime, dt); // 解析時間結構
      if(dt.hour % 4 == 0) break; // 找到最新 +0h 4H 開盤點
      startIdx--;
   }

   if(startIdx < nBars * 4 + 4) return false; // 數據不足跳過

   // startIdx - 1 即為最新完結之 +0h 4H 的末端 1H！
   int lastClosedEnd = startIdx - 1;

   for(int k = 0; k < nBars; k++)
   {
      int idx = nBars - 1 - k; // 寫入陣列索引
      int end1H = lastClosedEnd - (k * 4); // 該 4H 末端 1H
      int start1H = end1H - 3; // 該 4H 開頭 1H

      outOpen[idx]  = rates1H[start1H].open; // 開盤價
      outClose[idx] = rates1H[end1H].close;   // 收盤價
      outHigh[idx]  = rates1H[start1H].high; // 最高價初始化
      outLow[idx]   = rates1H[start1H].low;  // 最低價初始化
      for(int m = start1H + 1; m <= end1H; m++) // 取 4 小時內極值
      {
         if(rates1H[m].high > outHigh[idx]) outHigh[idx] = rates1H[m].high; // 最高價
         if(rates1H[m].low < outLow[idx])   outLow[idx]  = rates1H[m].low;  // 最低價
      }
   }
   return true; // 合成成功
}

//+------------------------------------------------------------------+
//| 處理新完結之 4H K 線邏輯 (ProcessNew4HBar)                       |
//+------------------------------------------------------------------+
void ProcessNew4HBar()
{
   double c1, c2, h1, l1, h2, l2, ma4h, atr4h; // 宣告核心指標與 OHLC 變數

   if(_Period == PERIOD_H1) // 掛載在 H1 圖表上時，完全從 1H 數據精準合成 UTC +0h 4H 四價與指標
   {
      double oBars[35], hBars[35], lBars[35], cBars[35]; // 宣告 35 根 4H 暫存陣列
      if(!GetUTC0h4H_BarData(35, oBars, hBars, lBars, cBars)) // 精準合成 35 根 +0h 4H K 線
      {
         Print("⚠️ [+0h 數據合成中] 等待 1H 數據加載..."); // 日誌
         return; // 未就緒跳過
      }

      c1 = cBars[34]; // bar[1] 完結 4H 收盤價
      c2 = cBars[33]; // bar[2] 完結 4H 收盤價
      h1 = hBars[34]; // bar[1] 完結 4H 最高價
      l1 = lBars[34]; // bar[1] 完結 4H 最低價
      h2 = hBars[33]; // bar[2] 完結 4H 最高價
      l2 = lBars[33]; // bar[2] 完結 4H 最低價

      // 計算 30MA
      double sumClose = 0; // 30MA 累積和
      for(int k = 5; k < 35; k++) sumClose += cBars[k]; // 累加前 30 根 4H 收盤價
      ma4h = sumClose / 30.0; // 4H 30MA 值

      // 計算 14ATR
      double sumTR = 0; // 14ATR 累積和
      for(int k = 21; k < 35; k++) // 累加前 14 根 4H 真實波幅 TR
      {
         double tr1 = hBars[k] - lBars[k]; // 高低差
         double tr2 = MathAbs(hBars[k] - cBars[k-1]); // 高前收差
         double tr3 = MathAbs(lBars[k] - cBars[k-1]); // 低前收差
         double tr  = MathMax(tr1, MathMax(tr2, tr3)); // 取最大值為 TR
         sumTR += tr; // 累加 TR
      }
      atr4h = sumTR / 14.0; // 4H 14ATR 值
   }
   else // 原 H4 圖表相容模式
   {
      double ma4hArray[1], atr4hArray[1]; // 宣告 4H 快取陣列
      if(CopyBuffer(g_hMA4H, 0, 1, 1, ma4hArray) <= 0) return; // 讀取已完結 bar[1] 4H MA
      if(CopyBuffer(g_hATR4H, 0, 1, 1, atr4hArray) <= 0) return; // 讀取已完結 bar[1] 4H ATR

      c1 = iClose(_Symbol, PERIOD_H4, 1); // 讀取 bar[1] 收盤價
      c2 = iClose(_Symbol, PERIOD_H4, 2); // 讀取 bar[2] 收盤價
      h1 = iHigh(_Symbol, PERIOD_H4, 1);  // 讀取 bar[1] 最高價
      l1 = iLow(_Symbol, PERIOD_H4, 1);   // 讀取 bar[1] 最低價
      h2 = iHigh(_Symbol, PERIOD_H4, 2);  // 讀取 bar[2] 最高價
      l2 = iLow(_Symbol, PERIOD_H4, 2);   // 讀取 bar[2] 最低價
      ma4h = ma4hArray[0]; // 4H MA 值
      atr4h = atr4hArray[0]; // 4H ATR 值
   }

   bool sig_long_4h = (c1 > ma4h) && (c1 > c2); // 計算 4H 多頭觸發訊號 (Close > 30MA 且 動能 > 0)

   double longStopInit  = MathMin(l1, l2) - 1.0 * atr4h; // 初始多單停損價
   double shortStopInit = MathMax(h1, h2) + 1.0 * atr4h; // 初始空單停損價

   ulong mainTicket = 0, pyrTicket = 0; // 宣告持倉票號
   int totalEAPos = CountPositionsByEA(mainTicket, pyrTicket); // 統計當前 EA 持倉

   if(totalEAPos > 0 && g_MainStopPrice == 0.0) // 若有持倉但停損為零 (防失憶)
   {
      ReconstructStopPrices(); // 重構停損
   }

   //--- CASE A: 當前持有【主多單】
   if(mainTicket > 0 && PositionSelectByTicket(mainTicket) && PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
   {
      if(c1 < g_MainStopPrice || !sig_long_4h) // 觸發停損或多頭訊號消失
      {
         string reason = (c1 < g_MainStopPrice) ? "跌破移動停損" : "4H多頭訊號消失"; // 出場原因
         PrintFormat("🔴 [主多單平倉] 收盤=%.2f | 停損=%.2f | 原因=%s", c1, g_MainStopPrice, reason); // 日誌
         ClosePositionsByMagic(InpMagicMain); // 平倉主多
         ClosePositionsByMagic(InpMagicPyramid); // 一併平倉加多
         g_MainStopPrice = 0.0; // 清空主停損
         g_PyramidStopPrice = 0.0; // 清空加倉停損
         SavePersistentState(); // 儲存狀態
         return; // 結束
      }
      else // 未平倉，進行移動停損與加倉檢查
      {
         if(c1 > h2) // 突破前高
         {
            g_MainStopPrice = longStopInit; // 向上移動主多停損
            SavePersistentState(); // 儲存狀態
         }

         if(InpEnablePyramid && pyrTicket > 0 && PositionSelectByTicket(pyrTicket)) // 若持有加多單
         {
            if(c1 < g_PyramidStopPrice) // 觸發加多單停損
            {
               PrintFormat("🟠 [加多單平倉] 收盤=%.2f | 停損=%.2f", c1, g_PyramidStopPrice); // 日誌
               ClosePositionsByMagic(InpMagicPyramid); // 單獨平倉加多單
               g_PyramidStopPrice = 0.0; // 清空加多停損
               SavePersistentState(); // 儲存狀態
            }
            else if(c1 > h2) // 突破前高
            {
               g_PyramidStopPrice = longStopInit; // 向上移動加多單停損
               SavePersistentState(); // 儲存狀態
            }
         }
         else if(InpEnablePyramid && pyrTicket == 0 && g_RegimeBull && g_PyramidLongOK) // 滿足加多條件
         {
            g_trade.SetExpertMagicNumber(InpMagicPyramid); // 切換 Magic Number
            double pyrLot = NormalizeLot(InpLotSize); // 預設加碼手數
            double a1 = 0, a5 = 0, a10 = 0; // Alpha 變數
            if(CalculateAlpha(a1, a5, a10) && a10 > InpAlphaBoostThresh) // 若 Alpha10 > 3%
            {
               pyrLot = NormalizeLot(InpLotSize * InpPyramidBoostMultiplier); // 加碼 2.0 倍
            }

            if(g_trade.Buy(pyrLot, _Symbol, 0, 0, 0, "Pyramid_Long")) // 買入加多
            {
               g_PyramidStopPrice = longStopInit; // 設定加多停損
               PrintFormat("🟢 [加多單進場] 手數=%.2f | 停損=%.2f", pyrLot, g_PyramidStopPrice); // 日誌
               SavePersistentState(); // 儲存狀態
            }
         }
      }
   }
   //--- CASE B: 當前持有【主空單】
   else if(mainTicket > 0 && PositionSelectByTicket(mainTicket) && PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_SELL)
   {
      if(c1 > g_MainStopPrice || sig_long_4h) // 觸發停損或轉多頭訊號
      {
         string reason = (c1 > g_MainStopPrice) ? "突破移動停損" : "4H訊號轉多"; // 原因
         PrintFormat("🔴 [主空單平倉] 收盤=%.2f | 停損=%.2f | 原因=%s", c1, g_MainStopPrice, reason); // 日誌
         ClosePositionsByMagic(InpMagicMain); // 平倉主空
         ClosePositionsByMagic(InpMagicPyramid); // 一併平倉加空
         g_MainStopPrice = 0.0; // 清空停損
         g_PyramidStopPrice = 0.0; // 清空加倉停損
         SavePersistentState(); // 儲存狀態
         return; // 結束
      }
      else // 未平倉，進行移動停損與加空檢查
      {
         if(c1 < l2) // 跌破前低
         {
            g_MainStopPrice = shortStopInit; // 向下移動主空停損
            SavePersistentState(); // 儲存狀態
         }

         if(InpEnablePyramid && pyrTicket > 0 && PositionSelectByTicket(pyrTicket)) // 若持有加空單
         {
            if(c1 > g_PyramidStopPrice) // 觸發加空單停損
            {
               PrintFormat("🟠 [加空單平倉] 收盤=%.2f | 停損=%.2f", c1, g_PyramidStopPrice); // 日誌
               ClosePositionsByMagic(InpMagicPyramid); // 單獨平倉加空單
               g_PyramidStopPrice = 0.0; // 清空加空停損
               SavePersistentState(); // 儲存狀態
            }
            else if(c1 < l2) // 跌破前低
            {
               g_PyramidStopPrice = shortStopInit; // 向下移動加空停損
               SavePersistentState(); // 儲存狀態
            }
         }
         else if(InpEnablePyramid && pyrTicket == 0 && !g_RegimeBull && g_PyramidShortOK) // 滿足加空條件
         {
            g_trade.SetExpertMagicNumber(InpMagicPyramid); // 切換 Magic Number
            double pyrLot = NormalizeLot(InpLotSize); // 預設加碼手數
            double a1 = 0, a5 = 0, a10 = 0; // Alpha 變數
            if(CalculateAlpha(a1, a5, a10) && a10 < -InpAlphaBoostThresh) // 若 Alpha10 < -3%
            {
               pyrLot = NormalizeLot(InpLotSize * InpPyramidBoostMultiplier); // 加碼 2.0 倍
            }

            if(g_trade.Sell(pyrLot, _Symbol, 0, 0, 0, "Pyramid_Short")) // 賣出開空
            {
               g_PyramidStopPrice = shortStopInit; // 設定加空停損
               PrintFormat("🔻 [加空單平倉] 手數=%.2f | 停損=%.2f", pyrLot, g_PyramidStopPrice); // 日誌
               SavePersistentState(); // 儲存狀態
            }
         }
      }
   }

   //--- CASE C: 當前無持倉，檢查建倉
   totalEAPos = CountPositionsByEA(mainTicket, pyrTicket); // 重新統計持倉
   if(totalEAPos == 0) // 當前無持倉
   {
      double mainLot = NormalizeLot(InpLotSize); // 規範主部位手數
      if(g_RegimeBull && sig_long_4h) // 牛市環境且 4H 動能做多
      {
         g_trade.SetExpertMagicNumber(InpMagicMain); // 主部位 Magic Number
         if(g_trade.Buy(mainLot, _Symbol, 0, 0, 0, "Main_Long")) // 市價買入主多
         {
            g_MainStopPrice = longStopInit; // 設定主多停損
            PrintFormat("🟢 [主多單進場] 手數=%.2f | 停損=%.2f | MA4H=%.2f", mainLot, g_MainStopPrice, ma4h); // 日誌
            SavePersistentState(); // 儲存狀態
            if(InpEnableAlerts) Alert("🟢 Gold 4H: 主多單進場 @ ", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_ASK), 2)); // 提醒
         }
      }
      else if(!g_RegimeBull && !sig_long_4h) // 熊市環境且 4H 動能做空
      {
         g_trade.SetExpertMagicNumber(InpMagicMain); // 主部位 Magic Number
         if(g_trade.Sell(mainLot, _Symbol, 0, 0, 0, "Main_Short")) // 市價賣出主空
         {
            g_MainStopPrice = shortStopInit; // 設定主空停損
            PrintFormat("🔻 [主空單進場] 手數=%.2f | 停損=%.2f | MA4H=%.2f", mainLot, g_MainStopPrice, ma4h); // 日誌
            SavePersistentState(); // 儲存狀態
            if(InpEnableAlerts) Alert("🔻 Gold 4H: 主空單進場 @ ", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_BID), 2)); // 提醒
         }
      }
   }
}

//+------------------------------------------------------------------+
//| 判斷當前 1H K 線是否為 UTC +0h (00, 04, 08, 12, 16, 20) 新 4H 開盤 |
//+------------------------------------------------------------------+
bool IsNewUTC4HBar(datetime current1HTime)
{
   int gmtOffset = TimeGMTOffset(); // 讀取當前 MT5 伺服器的 GMT 偏移秒數 (例: 夏令為 10800 秒 = 3 小時)
   datetime utcTime = current1HTime - gmtOffset; // 轉換為標準 UTC 時間
   MqlDateTime dt; // 宣告時間結構
   TimeToStruct(utcTime, dt); // 解析時間結構
   return (dt.hour % 4 == 0); // 判斷 UTC 小時是否為 00, 04, 08, 12, 16, 20 (開盤點)
}

//+------------------------------------------------------------------+
//| 主 Tick 處理函數 (OnTick)                                         |
//+------------------------------------------------------------------+
void OnTick()
{
   //--- 檢查是否有新日線收盤
   datetime currentDailyTime = iTime(_Symbol, PERIOD_D1, 0); // 取得當前日線時間
   if(currentDailyTime != g_LastBarDaily || !g_DailyReady) // 若跳新日線或尚未完成首次計算
   {
      g_LastBarDaily = currentDailyTime; // 更新日線時間紀錄
      UpdateDailyFilters(); // 更新日線趨勢過濾器
   }

   //--- 雙相容模式：優先支持 H1 圖表之 UTC +0h 觸發，亦相容原 H4 圖表觸發
   datetime triggerTime = (_Period == PERIOD_H1) ? iTime(_Symbol, PERIOD_H1, 0) : iTime(_Symbol, PERIOD_H4, 0); // 取得當前開盤時間
   if(triggerTime != g_LastBar4H) // 若跳新 K 線
   {
      bool isTrigger = (_Period == PERIOD_H1) ? IsNewUTC4HBar(triggerTime) : true; // 若掛在 H1 圖表上則精準依 UTC +0h 點位觸發
      if(isTrigger) // 滿足觸發條件
      {
         g_LastBar4H = triggerTime; // 更新 4H 時間紀錄
         ProcessNew4HBar(); // 執行 4H 交易邏輯
         SavePersistentState(); // 儲存狀態
      }
   }
}
//+------------------------------------------------------------------+
