//+------------------------------------------------------------------+
//|                                   Indicator_UTC0h_4H_30MA.mq5 |
//|                     在 1H 圖表上繪製 +0h 時間之 4H 30MA 均線指標    |
//|                               Version 2.00                        |
//+------------------------------------------------------------------+
#property copyright "Gold UTC+0h 4H 30MA Indicator" // 版權宣告
#property version   "2.00" // 版本號
#property indicator_chart_window // 在主圖表視窗繪製
#property indicator_buffers 1 // 使用 1 個指標緩衝區
#property indicator_plots   1 // 繪製 1 條指標線

#property indicator_label1  "4H 30MA (+0h)" // 指標線標籤
#property indicator_type1   DRAW_LINE // 繪製線條
#property indicator_color1  clrOrangeRed // 高對比鮮艷深橘紅色
#property indicator_style1  STYLE_SOLID // 實線
#property indicator_width1  3 // 線條粗細 3

//--- 指標緩衝區
double   BufferMA4H[]; // 4H 30MA 數據緩衝區

//+------------------------------------------------------------------+
//| 指標初始化函數 (OnInit)                                           |
//+------------------------------------------------------------------+
int OnInit()
{
   SetIndexBuffer(0, BufferMA4H, INDICATOR_DATA); // 綁定緩衝區 0
   PlotIndexSetString(0, PLOT_LABEL, "4H 30MA (+0h Offset)"); // 設定圖例說明
   PlotIndexSetDouble(0, PLOT_EMPTY_VALUE, EMPTY_VALUE); // 設定空值標誌
   return(INIT_SUCCEEDED); // 回傳成功
}

//+------------------------------------------------------------------+
//| 計算主函數 (OnCalculate)                                         |
//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   if(rates_total < 200) return 0; // K 線數量不足跳過

   int start = prev_calculated - 1; // 計算起始位置
   if(start < 120) start = 120; // 確保前 120 根有數據

   for(int i = start; i < rates_total; i++) // 遍歷每根 1H K 線
   {
      // 尋找當前 1H (i) 所在或之前的最新 +0h 4H 開盤點 (MT5 小時為 03, 07, 11, 15, 19, 23)
      int startIdx = i;
      while(startIdx >= 0)
      {
         MqlDateTime dt;
         TimeToStruct(time[startIdx], dt); // 解析 MT5 K 線時間
         if(dt.hour % 4 == 3) break; // 找到 +0h 4H 開盤點 (MT5 03,07,11,15,19,23)
         startIdx--; // 向前移動 1 小時
      }

      if(startIdx < 120) // 前方歷史數據不足 30 根 4H (120 小時) 則跳過
      {
         BufferMA4H[i] = EMPTY_VALUE;
         continue;
      }

      // startIdx - 1 即為最新完結 +0h 4H 之末端 1H 收盤價
      double sumClose = 0.0;
      for(int k = 0; k < 30; k++)
      {
         int closeIdx = (startIdx - 1) - (k * 4); // 每隔 4 小時前推一次 4H 收盤價
         if(closeIdx >= 0)
            sumClose += close[closeIdx];
         else
            sumClose += close[0];
      }

      BufferMA4H[i] = sumClose / 30.0; // 計算精準對齊台北時間 +0h 之 4H 30MA
   }

   return(rates_total); // 回傳已計算數量
}
