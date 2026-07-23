import os
import time
os.environ['TZ'] = 'UTC'
if hasattr(time, 'tzset'):
    time.tzset()

from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import warnings

warnings.filterwarnings("ignore")

def main():
    print("初始化 TradingView 客戶端 (匿名登入)...")
    tv = TvDatafeed()
    
    # 定義要抓取的商品與交易所
    assets = [
        ('DXY', 'ICEUS'),
        ('GC1!', 'COMEX'),
        ('DFII10', 'FRED')
    ]
    
    for symbol, exchange in assets:
        print(f"正在下載 {exchange}:{symbol} 的 Daily K線資料...")
        df = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_daily, n_bars=5000)
        
        if df is not None and not df.empty:
            df = df.reset_index()
            # 確保取得的時間為 UTC，並轉換為台北時間
            df['datetime'] = df['datetime'].dt.tz_localize('UTC').dt.tz_convert('Asia/Taipei')
            
            df = df.rename(columns={'datetime': 'timestamp'})
            df = df[['timestamp', 'open', 'high', 'low', 'close']]
            
            # 日線資料格式化為 YYYY-MM-DD
            df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%d')
                
            filename = f"{exchange}_{symbol}_daily.csv".lower()
            df.to_csv(filename, index=False)
            print(f"✅ 成功！資料已儲存為 {filename}\n")
        else:
            print(f"❌ 失敗！無法獲取 {exchange}:{symbol} 資料\n")

if __name__ == "__main__":
    main()
