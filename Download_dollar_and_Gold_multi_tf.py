import os  # 匯入作業系統模組以處理路徑
import pandas as pd  # 匯入 pandas 模組進行資料分析
import warnings  # 匯入警告模組以忽略不必要的警示
from tvDatafeed import TvDatafeed, Interval  # 匯入 tvDatafeed 客戶端與頻率枚舉

warnings.filterwarnings("ignore")  # 忽略所有警告訊息

def main():
    print("初始化 TradingView 客戶端 (多頻率匿名下載)...")  # 印出初始化提示
    tv = TvDatafeed()  # 建立匿名 tvDatafeed 客戶端實例
    
    # 定義要下載的商品與交易所資訊
    assets = [
        ('DXY', 'ICEUS'),  # 美元指數
        ('GC1!', 'COMEX')  # 黃金期貨商品
    ]  # 商品定義結束
    
    for symbol, exchange in assets:  # 迴圈下載每個商品
        print(f"正在下載 {exchange}:{symbol} 的 4H K線資料...")  # 印出下載提示
        df = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_4_hour, n_bars=5000)  # 下載 5000 根 4H K線
        
        if df is not None and not df.empty:  # 確保取得資料且不為空
            df = df.reset_index()  # 重設索引以將 datetime 轉為一般欄位
            df['datetime'] = df['datetime'].dt.tz_localize('UTC').dt.tz_convert('Asia/Taipei')  # 轉換為台北時間
            df = df.rename(columns={'datetime': 'timestamp'})  # 將 datetime 欄位命名為 timestamp
            df = df[['timestamp', 'open', 'high', 'low', 'close']]  # 篩選出需要的五個 OHLC 欄位
            
            # 格式化 4H 時間戳為字串以利儲存
            df_4h_save = df.copy()  # 複製一份 DataFrame 用於儲存 4H
            df_4h_save['timestamp'] = df_4h_save['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')  # 格式化時間字串
            filename_4h = f"{exchange}_{symbol}_4h.csv".lower()  # 定義 4H 資料檔案名稱
            df_4h_save.to_csv(filename_4h, index=False)  # 將 4H 資料儲存為 CSV 檔案
            print(f"✅ 成功！4H 資料儲存為 {filename_4h}")  # 印出成功存檔訊息
            
            # 使用 4H 資料重取樣合成 8H K線
            df.set_index('timestamp', inplace=True)  # 將 timestamp 設為 DataFrame 的索引以進行 resample
            # 採用 origin='start' 以便以資料起始時間精準切分 8 小時區間
            df_8h = df.resample('8h', origin='start').agg({
                'open': 'first',  # open 取該 8 小時區間內第一筆 K線開盤價
                'high': 'max',  # high 取該 8 小時區間內最高價
                'low': 'min',  # low 取該 8 小時區間內最低價
                'close': 'last'  # close 取該 8 小時區間內最後一筆 K線收盤價
            }).dropna().reset_index()  # 移除 NaN 值並還原 timestamp 欄位
            
            # 格式化 8H 時間戳為字串以利儲存
            df_8h['timestamp'] = df_8h['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')  # 格式化時間字串
            filename_8h = f"{exchange}_{symbol}_8h.csv".lower()  # 定義 8H 資料檔案名稱
            df_8h.to_csv(filename_8h, index=False)  # 將 8H 資料儲存為 CSV 檔案
            print(f"✅ 成功！8H 合成資料儲存為 {filename_8h}\n")  # 印出成功存檔與換行訊息
        else:  # 若下載失敗
            print(f"❌ 失敗！無法獲取 {exchange}:{symbol} 的 4H 資料\n")  # 印出錯誤訊息

if __name__ == "__main__":  # 若為直接執行
    main()  # 執行主程式
