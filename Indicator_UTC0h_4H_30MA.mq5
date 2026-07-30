//+------------------------------------------------------------------+
//|                                   Indicator_UTC0h_4H_30MA.mq5 |
//|                     在 1H 圖表上繪製 +0h 時間之 4H 30MA 均線指標    |
//|                               Version 1.00                        |
//+------------------------------------------------------------------+
#property copyright "Gold UTC+0h 4H 30MA Indicator" // 版權宣告
#property version   "1.00" // 版本號
#property indicator_chart_window // 在主圖表視窗繪製
#property indicator_buffers 1 // 使用 1 個指標緩衝區
#property indicator_plots   1 // 繪製 1 條指標線

#property indicator_label1  "4H 30MA (+0h)" // 指標線標籤
#property indicator_type1   DRAW_LINE // 繪製線條
#property indicator_color1  clrGold // 金黃色線條
#property indicator_style1  STYLE_SOLID // 實線
#property indicator_width1  2 // 線條寬度 2

//--- 指標緩衝區 (Buffer)
double   BufferMA4H[]; // 4H 30MA 數據緩衝區

//+------------------------------------------------------------------+
//| 指標初始化函數 (OnInit)                                           |
//+------------------------------------------------------------------+
int OnInit()
{
   SetIndexBuffer(0, BufferMA4H, INDICATOR_DATA); // 綁定緩衝區 0
   PlotIndexSetString(0, PLOT_LABEL, "4H 30MA (+0h Offset)"); // 設定圖例說明
   PlotIndexSetDouble(0, PLOT_EMPTY_VALUE, 0.0); // 設空值為 0
   return(INIT_SUCCEEDED); // 回傳成功
}

//+------------------------------------------------------------------+
//| 判斷當前 1H K 線是否為 UTC +0h (00, 04, 08, 12, 16, 20) 新 4H 開盤 |
//+------------------------------------------------------------------+
bool IsUTC0hStart(datetime barTime1H)
{
   int gmtOffset = TimeGMTOffset(); // 讀取 MT5 伺服器與 GMT 偏移秒數
   datetime utcTime = barTime1H - gmtOffset; // 轉為 UTC 時間
   MqlDateTime dt;
   TimeToStruct(utcTime, dt); // 解析時間結構
   return (dt.hour % 4 == 0); // 判斷 UTC 小時是否為 00, 04, 08, 12, 16, 20
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
   if(start < 0) start = 0; // 首次全量計算

   for(int i = start; i < rates_total; i++) // 遍歷每根 1H K 線
   {
      double sumClose = 0.0; // 30 根完結 +0h 4H 收盤價總和
      int count = 0; // 計數器
      int cur = i; // 追蹤游標

      // 先尋找當前 1H 所在之已完結 +0h 4H 區間末端
      while(cur >= 3)
      {
         if(IsUTC0hStart(time[cur - 3])) // cur-3 為 +0h 4H 第一根 1H，則 cur 為該 4H 第四根 1H (末端)
         {
            break;
         }
         cur--;
      }

      // 倒序累加前 30 根完結 +0h 4H 之實際收盤價 (第 4 根 1H 之 close)
      while(cur >= 3 && count < 30)
      {
         if(IsUTC0hStart(time[cur - 3])) // 判定符合 +0h 4H 區間
         {
            sumClose += close[cur]; // 累加該 4H 之真正收盤價
            count++; // 計數加一
            cur -= 4; // 跳到上一個 4H 的末端 1H
         }
         else
         {
            cur--; // 移動游標
         }
      }

      if(count == 30)
         BufferMA4H[i] = sumClose / 30.0; // 計算精準對齊之 4H 30MA 平滑線
      else
         BufferMA4H[i] = 0.0; // 數據不足填 0
   }

   return(rates_total); // 回傳已計算數量
}
