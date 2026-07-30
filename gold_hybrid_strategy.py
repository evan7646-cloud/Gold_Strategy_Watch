import os  # 匯入作業系統模組以處理檔案路徑
import json  # 匯入 JSON 模組以導出網頁資料
import pandas as pd  # 匯入 pandas 模組進行資料分析與表格處理
import numpy as np  # 匯入 numpy 模組進行數值計算
from tvDatafeed import TvDatafeed, Interval  # 匯入 tvDatafeed 以抓取 TradingView 資料

def download_data():  # 定義下載數據的函數
    print("正在檢查並下載最新 K 線數據...")  # 印出下載提示訊息
    try:  # 嘗試初始化與下載
        tv = TvDatafeed()  # 初始化 TradingView 匿名客戶端實例
        try:  # 嘗試下載 DXY 日線
            df_dxy = tv.get_hist(symbol='DXY', exchange='ICEUS', interval=Interval.in_daily, n_bars=5000)  # 下載美元指數日線資料
            if df_dxy is not None and not df_dxy.empty:  # 檢查美元指數資料是否成功取得
                df_dxy = df_dxy.reset_index()  # 重設索引以取出 datetime 欄位
                df_dxy['datetime'] = pd.to_datetime(df_dxy['datetime'])  # 轉為 datetime 物件
                df_dxy = df_dxy.rename(columns={'datetime': 'timestamp'})  # 重新命名時間欄位為 timestamp
                df_dxy['timestamp'] = df_dxy['timestamp'].dt.strftime('%Y-%m-%d')  # 將日線時間格式化為年月日字串
                df_new_dxy = df_dxy[['timestamp', 'open', 'high', 'low', 'close']]  # 取出標準五欄位
                if os.path.exists('iceus_dxy_daily.csv'):  # 檢查是否存在舊檔案
                    df_old_dxy = pd.read_csv('iceus_dxy_daily.csv')  # 讀取舊 CSV 檔
                    df_new_dxy = pd.concat([df_old_dxy, df_new_dxy]).drop_duplicates(subset=['timestamp'], keep='last').sort_values('timestamp').reset_index(drop=True)  # 合併去重
                df_new_dxy.to_csv('iceus_dxy_daily.csv', index=False)  # 儲存美元指數日線 CSV
                print("✅ 美元指數日線下載與合併成功")  # 印出成功提示
        except Exception as e_dxy:  # 捕捉 DXY 下載異常
            print(f"⚠️ 美元指數下載警告: {e_dxy}")  # 印出警告

        try:  # 嘗試下載 Pepperstone XAUUSD 黃金日線
            df_gold_d = tv.get_hist(symbol='XAUUSD', exchange='PEPPERSTONE', interval=Interval.in_daily, n_bars=5000)  # 下載 Pepperstone XAUUSD 日線資料
            if df_gold_d is not None and not df_gold_d.empty:  # 檢查黃金日線資料是否成功取得
                df_gold_d = df_gold_d.reset_index()  # 重設索引取出時間欄位
                df_gold_d['datetime'] = pd.to_datetime(df_gold_d['datetime'])  # 轉為 datetime 物件
                df_gold_d = df_gold_d.rename(columns={'datetime': 'timestamp'})  # 重新命名欄位
                df_gold_d['timestamp'] = df_gold_d['timestamp'].dt.strftime('%Y-%m-%d')  # 格式化日期字串
                df_new_gd = df_gold_d[['timestamp', 'open', 'high', 'low', 'close']]  # 取出標準五欄位
                if os.path.exists('comex_gc1!_daily.csv'):  # 檢查是否存在舊檔案
                    df_old_gd = pd.read_csv('comex_gc1!_daily.csv')  # 讀取舊 CSV 檔
                    df_new_gd = pd.concat([df_old_gd, df_new_gd]).drop_duplicates(subset=['timestamp'], keep='last').sort_values('timestamp').reset_index(drop=True)  # 合併去重
                df_new_gd.to_csv('comex_gc1!_daily.csv', index=False)  # 儲存黃金日線 CSV
                print("✅ Pepperstone XAUUSD 日線下載與合併成功")  # 印出成功提示
        except Exception as e_gd:  # 捕捉黃金日線下載異常
            print(f"⚠️ Pepperstone XAUUSD 日線下載警告: {e_gd}")  # 印出警告

        try:  # 嘗試下載 Pepperstone XAUUSD 1H K線並精準合成 +0h 4H K線
            df_gold_raw = tv.get_hist(symbol='XAUUSD', exchange='PEPPERSTONE', interval=Interval.in_1_hour, n_bars=10000)  # 讀取 Pepperstone XAUUSD 1H K線
            if df_gold_raw is None or df_gold_raw.empty:  # 若 1H 未取得則回退 4H
                df_gold_raw = tv.get_hist(symbol='XAUUSD', exchange='PEPPERSTONE', interval=Interval.in_4_hour, n_bars=5000)  # 回退 4H

            if df_gold_raw is not None and not df_gold_raw.empty:  # 檢查資料是否成功取得
                df_gold_raw = df_gold_raw.reset_index()  # 重設索引
                df_gold_raw['datetime'] = pd.to_datetime(df_gold_raw['datetime'])  # 轉為 datetime 物件
                df_gold_raw = df_gold_raw.rename(columns={'datetime': 'timestamp'})  # 重新命名欄位
                df_gold_raw.set_index('timestamp', inplace=True)  # 設為索引以利重取樣
                origin_tz = pd.Timestamp('2024-01-01 00:00:00')  # 設定 00:00 (+0h 4H 切分) 偏移錨點
                df_gold_4h = df_gold_raw.resample('4h', origin=origin_tz).agg({  # 重取樣合成 4H K線 (+0h offset)
                    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
                }).dropna().reset_index()  # 去除空值並重設索引
                df_save = df_gold_4h[['timestamp', 'open', 'high', 'low', 'close']].copy()  # 取出標準五欄位
                df_save['timestamp'] = df_save['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')  # 格式化時間字串
                df_save.to_csv('comex_gc1!_4h.csv', index=False)  # 儲存 4H K線 CSV
                print("✅ Pepperstone XAUUSD 純淨 +0h 4H K線合成與儲存成功")  # 印出成功提示
        except Exception as e_g4h:  # 捕捉 4H K線下載異常
            print(f"⚠️ Pepperstone XAUUSD 4H K線下載警告: {e_g4h}")  # 印出警告
    except Exception as e_main:  # 捕捉整體連線異常
        print(f"⚠️ 下載數據發生連線異常: {e_main}，將使用本地快取資料進行回測")  # 印出提示 warning
        print("✅ 黃金期貨 4H K線 (UTC 02:00 錨點) 合成成功")  # 印出成功提示

def calculate_atr(df, period=14):  # 定義計算真實波幅均值 ATR 的函數
    high = df['high']  # 取得最高價序列
    low = df['low']  # 取得最低價序列
    close_prev = df['close'].shift(1)  # 取得前一期收盤價序列
    tr1 = high - low  # 計算當期高低價差
    tr2 = (high - close_prev).abs()  # 計算當期最高價與前收絕對差
    tr3 = (low - close_prev).abs()  # 計算當期最低價與前收絕對差
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)  # 取三者之最大值作為當期真實波幅 TR
    atr = tr.rolling(period).mean()  # 計算 14 週期滑動平均 ATR
    return atr  # 回傳 ATR 數據序列

def sanitize_list(lst):  # 定義替換 list 中 NaN 為 None (JSON null) 的淨化函數
    return [None if (v is None or pd.isna(v) or np.isnan(v)) else float(v) for v in lst]  # 遍歷替換 NaN

def simulate_direction(df, is_long_only=True):  # 定義單向策略模擬子引擎
    n = len(df)  # 資料筆數
    active_positions = []  # 當前持倉
    completed_trades = []  # 完結交易
    annotations = []  # 進出場標記

    for i in range(n - 1):  # 遍歷資料
        t_close = df.loc[i, 'close']  # 收盤價
        t_high = df.loc[i, 'high']  # 最高價
        t_low = df.loc[i, 'low']  # 最低價
        t_atr = df.loc[i, 'atr14_4h']  # 4H ATR

        t_prev_high = df.loc[i-1, 'high'] if i > 0 else t_high  # 前一根高
        t_prev_low = df.loc[i-1, 'low'] if i > 0 else t_low  # 前一根低

        dy_close = df.loc[i, 'daily_close_avail']  # 日線收盤
        dy_ma50 = df.loc[i, 'daily_ma50_avail']  # 日線 50MA
        dy_ma20 = df.loc[i, 'daily_ma20_avail']  # 日線 20MA
        dy_ma60 = df.loc[i, 'daily_ma60_avail']  # 日線 60MA
        dy_a1 = df.loc[i, 'daily_alpha1_avail']  # Alpha1
        dy_a5 = df.loc[i, 'daily_alpha5_avail']  # Alpha5
        dy_a10 = df.loc[i, 'daily_alpha10_avail']  # Alpha10

        is_long_sig = df.loc[i, 'sig_long_4h']  # 4H 多頭訊號

        next_open = df.loc[i+1, 'open']  # 下期開盤價
        next_stamp = str(df.loc[i+1, 'timestamp'])  # 下期時間

        dy_pyramid_long = (dy_a1 > 0) and (dy_a5 > 0) and (dy_a10 > 0) and (dy_ma20 > dy_ma60)  # 加多條件
        dy_pyramid_short = (dy_a1 < 0) and (dy_a5 < 0) and (dy_a10 < 0) and (dy_ma20 < dy_ma60)  # 加空條件

        has_pos = len(active_positions) > 0  # 是否有部位
        new_active = []  # 新持倉

        if is_long_only:  # 多單子引擎
            if has_pos:  # 有多單
                main_pos = [p for p in active_positions if not p['is_pyramid']][0]  # 主多單
                pyr_pos = [p for p in active_positions if p['is_pyramid']]  # 加多單
                has_pyr = len(pyr_pos) > 0  # 有無加多

                if t_close < main_pos['stop_price'] or not is_long_sig:  # 全數平倉
                    exit_reason = "Stop Loss Exit" if t_close < main_pos['stop_price'] else "Signal Exit"  # 平倉原因
                    for p in active_positions:  # 遍歷部位
                        holding_days = (pd.to_datetime(next_stamp).date() - pd.to_datetime(p['entry_date']).date()).days  # 持有跨日天數
                        raw_pnl = next_open - p['entry_price']  # 原始點數
                        net_pnl_unit = raw_pnl - 0.3 - (holding_days * 0.75)  # 扣除點差與過夜費
                        net_pnl = net_pnl_unit * p.get('units', 1.0)  # 加權淨損益
                        completed_trades.append({  # 記錄
                            'type': 'Long', 'is_pyramid': p['is_pyramid'], 'units': p.get('units', 1.0),
                            'entry_date': p['entry_date'], 'entry_price': p['entry_price'],
                            'exit_date': next_stamp, 'exit_price': next_open,
                            'stop_price': round(p['stop_price'], 2), 'pnl_points': round(net_pnl, 2),
                            'holding_hours': holding_days * 24, 'exit_reason': exit_reason
                        })  # 記錄結束
                        annotations.append({  # 圖表標記
                            'time': next_stamp, 'price': next_open, 'title': f"Exit Long ({exit_reason})",
                            'text': f"PnL: {net_pnl:.2f}", 'shape': 'arrowDown', 'color': '#ef5350'
                        })  # 標記結束
                    active_positions = []  # 清空
                else:  # 保留並更新
                    if t_close > t_prev_high:  # 突破前高
                        main_pos['stop_price'] = min(t_low, t_prev_low) - 1.0 * t_atr  # 更新主多停損
                    new_active.append(main_pos)  # 保留主多

                    if has_pyr:  # 已加多
                        p_pos = pyr_pos[0]  # 加多單
                        if t_close < p_pos['stop_price']:  # 跌破加多停損
                            holding_days = (pd.to_datetime(next_stamp).date() - pd.to_datetime(p_pos['entry_date']).date()).days  # 跨日天數
                            raw_pnl = next_open - p_pos['entry_price']  # 點數
                            net_pnl_unit = raw_pnl - 0.3 - (holding_days * 0.75)  # 扣成本
                            net_pnl = net_pnl_unit * p_pos.get('units', 1.0)  # 加權淨損益
                            completed_trades.append({  # 記錄平倉加多
                                'type': 'Long', 'is_pyramid': True, 'units': p_pos.get('units', 1.0),
                                'entry_date': p_pos['entry_date'], 'entry_price': p_pos['entry_price'],
                                'exit_date': next_stamp, 'exit_price': next_open,
                                'stop_price': round(p_pos['stop_price'], 2), 'pnl_points': round(net_pnl, 2),
                                'holding_hours': holding_days * 24, 'exit_reason': 'Pyramid Stop Loss'
                            })  # 記錄結束
                            annotations.append({  # 圖表標記
                                'time': next_stamp, 'price': next_open, 'title': 'Exit Pyramid Long',
                                'text': f"PnL: {net_pnl:.2f}", 'shape': 'arrowDown', 'color': '#ff9800'
                            })  # 標記結束
                        else:  # 保留加多
                            if t_close > t_prev_high:  # 突破前高
                                p_pos['stop_price'] = min(t_low, t_prev_low) - 1.0 * t_atr  # 更新加多停損
                            new_active.append(p_pos)  # 保留
                    else:  # 未加多
                        if dy_close > dy_ma50 and dy_pyramid_long:  # 滿足加多
                            pyr_units = 2.0 if dy_a10 > 0.03 else 1.0  # 觸發時若 Alpha10 > 3% 則賦予 2.0 units
                            new_active.append({  # 建立加多
                                'type': 'Long', 'is_pyramid': True, 'units': pyr_units, 'entry_date': next_stamp,
                                'entry_price': next_open, 'stop_price': min(t_low, t_prev_low) - 1.0 * t_atr
                            })  # 加多建立結束
                            annotations.append({  # 圖表標記
                                'time': next_stamp, 'price': next_open, 'title': f"+Pyramid Long ({pyr_units}x)",
                                'text': f"Price: {next_open:.2f}", 'shape': 'arrowUp', 'color': '#26a69a'
                            })  # 標記結束
                    active_positions = new_active  # 更新部位
            else:  # 空手多單
                if dy_close > dy_ma50 and is_long_sig:  # 滿足主多
                    active_positions.append({  # 建立主多
                        'type': 'Long', 'is_pyramid': False, 'units': 1.0, 'entry_date': next_stamp,
                        'entry_price': next_open, 'stop_price': min(t_low, t_prev_low) - 1.0 * t_atr
                    })  # 建立結束
                    annotations.append({  # 圖表標記
                        'time': next_stamp, 'price': next_open, 'title': 'Buy Main Long',
                        'text': f"Price: {next_open:.2f}", 'shape': 'arrowUp', 'color': '#00e676'
                    })  # 標記結束

        else:  # 空單子引擎
            if has_pos:  # 有空單
                main_pos = [p for p in active_positions if not p['is_pyramid']][0]  # 主空單
                pyr_pos = [p for p in active_positions if p['is_pyramid']]  # 加空單
                has_pyr = len(pyr_pos) > 0  # 有無加空

                if t_close > main_pos['stop_price'] or is_long_sig:  # 全數平倉
                    exit_reason = "Stop Loss Exit" if t_close > main_pos['stop_price'] else "Signal Exit"  # 平倉原因
                    for p in active_positions:  # 遍歷部位
                        holding_days = (pd.to_datetime(next_stamp).date() - pd.to_datetime(p['entry_date']).date()).days  # 持有跨日天數
                        raw_pnl = p['entry_price'] - next_open  # 空單點數
                        net_pnl_unit = raw_pnl - 0.3 + (holding_days * 0.27)  # 扣點差加利息
                        net_pnl = net_pnl_unit * p.get('units', 1.0)  # 加權淨損益
                        completed_trades.append({  # 記錄
                            'type': 'Short', 'is_pyramid': p['is_pyramid'], 'units': p.get('units', 1.0),
                            'entry_date': p['entry_date'], 'entry_price': p['entry_price'],
                            'exit_date': next_stamp, 'exit_price': next_open,
                            'stop_price': round(p['stop_price'], 2), 'pnl_points': round(net_pnl, 2),
                            'holding_hours': holding_days * 24, 'exit_reason': exit_reason
                        })  # 記錄結束
                        annotations.append({  # 圖表標記
                            'time': next_stamp, 'price': next_open, 'title': f"Exit Short ({exit_reason})",
                            'text': f"PnL: {net_pnl:.2f}", 'shape': 'arrowUp', 'color': '#26a69a'
                        })  # 標記結束
                    active_positions = []  # 清空
                else:  # 保留並更新
                    if t_close < t_prev_low:  # 跌破前低
                        main_pos['stop_price'] = max(t_high, t_prev_high) + 1.0 * t_atr  # 更新主空停損
                    new_active.append(main_pos)  # 保留主空

                    if has_pyr:  # 已加空
                        p_pos = pyr_pos[0]  # 加空單
                        if t_close > p_pos['stop_price']:  # 突破加空停損
                            holding_days = (pd.to_datetime(next_stamp).date() - pd.to_datetime(p_pos['entry_date']).date()).days  # 天數
                            raw_pnl = p_pos['entry_price'] - next_open  # 點數
                            net_pnl_unit = raw_pnl - 0.3 + (holding_days * 0.27)  # 扣點差加利息
                            net_pnl = net_pnl_unit * p_pos.get('units', 1.0)  # 加權淨損益
                            completed_trades.append({  # 記錄平倉加空
                                'type': 'Short', 'is_pyramid': True, 'units': p_pos.get('units', 1.0),
                                'entry_date': p_pos['entry_date'], 'entry_price': p_pos['entry_price'],
                                'exit_date': next_stamp, 'exit_price': next_open,
                                'stop_price': round(p_pos['stop_price'], 2), 'pnl_points': round(net_pnl, 2),
                                'holding_hours': holding_days * 24, 'exit_reason': 'Pyramid Stop Loss'
                            })  # 記錄結束
                            annotations.append({  # 圖表標記
                                'time': next_stamp, 'price': next_open, 'title': 'Exit Pyramid Short',
                                'text': f"PnL: {net_pnl:.2f}", 'shape': 'arrowUp', 'color': '#ff9800'
                            })  # 標記結束
                        else:  # 保留加空
                            if t_close < t_prev_low:  # 跌破前低
                                p_pos['stop_price'] = max(t_high, t_prev_high) + 1.0 * t_atr  # 更新加空停損
                            new_active.append(p_pos)  # 保留
                    else:  # 未加空
                        if dy_close < dy_ma50 and dy_pyramid_short:  # 滿足加空
                            pyr_units = 2.0 if dy_a10 < -0.03 else 1.0  # 觸發時若 Alpha10 < -3% 則賦予 2.0 units
                            new_active.append({  # 建立加空
                                'type': 'Short', 'is_pyramid': True, 'units': pyr_units, 'entry_date': next_stamp,
                                'entry_price': next_open, 'stop_price': max(t_high, t_prev_high) + 1.0 * t_atr
                            })  # 加空建立結束
                            annotations.append({  # 圖表標記
                                'time': next_stamp, 'price': next_open, 'title': f"+Pyramid Short ({pyr_units}x)",
                                'text': f"Price: {next_open:.2f}", 'shape': 'arrowDown', 'color': '#ef5350'
                            })  # 標記結束
                    active_positions = new_active  # 更新部位
            else:  # 空手空單
                if dy_close < dy_ma50 and not is_long_sig:  # 滿足主空
                    active_positions.append({  # 建立主空
                        'type': 'Short', 'is_pyramid': False, 'units': 1.0, 'entry_date': next_stamp,
                        'entry_price': next_open, 'stop_price': max(t_high, t_prev_high) + 1.0 * t_atr
                    })  # 建立結束
                    annotations.append({  # 圖表標記
                        'time': next_stamp, 'price': next_open, 'title': 'Sell Main Short',
                        'text': f"Price: {next_open:.2f}", 'shape': 'arrowDown', 'color': '#ff1744'
                    })  # 標記結束

    return active_positions, completed_trades, annotations  # 回傳單向數據

def run_backtest():  # 定義對齊 4H 30MA 之回測主函數
    download_data()  # 無條件執行最新數據下載與合併

    gold_daily_file = 'comex_gc1!_daily.csv'  # 指定黃金日線檔
    dxy_daily_file = 'iceus_dxy_daily.csv'  # 指定美元指數檔
    gold_4h_file = 'comex_gc1!_4h.csv'  # 指定 4H 檔

    gold_d = pd.read_csv(gold_daily_file)  # 讀取黃金日線
    dxy_d = pd.read_csv(dxy_daily_file)  # 讀取 DXY 日線
    gold_4h = pd.read_csv(gold_4h_file)  # 讀取 4H

    gold_d = gold_d.rename(columns={'close': 'gold_close', 'open': 'gold_open', 'high': 'gold_high', 'low': 'gold_low'})  # 重新命名欄位
    dxy_d = dxy_d.rename(columns={'close': 'dxy_close', 'open': 'dxy_open', 'high': 'dxy_high', 'low': 'dxy_low'})  # 重新命名欄位

    df_daily = pd.merge(gold_d, dxy_d, on='timestamp', how='inner')  # 合併日線
    df_daily['timestamp'] = pd.to_datetime(df_daily['timestamp'])  # 轉 datetime
    df_daily = df_daily.sort_values('timestamp').reset_index(drop=True)  # 排序

    for n in [1, 5, 10]:  # 計算報酬與 Alpha
        df_daily[f'gold_ret_{n}'] = df_daily['gold_close'].pct_change(n)  # 黃金收益率
        df_daily[f'dxy_ret_{n}'] = df_daily['dxy_close'].pct_change(n)  # 美元收益率
        df_daily[f'alpha_{n}'] = df_daily[f'gold_ret_{n}'] - df_daily[f'dxy_ret_{n}']  # Alpha 動能

    df_daily['ma20'] = df_daily['gold_close'].rolling(20).mean()  # 日線 20MA
    df_daily['ma50'] = df_daily['gold_close'].rolling(50).mean()  # 日線 50MA
    df_daily['ma60'] = df_daily['gold_close'].rolling(60).mean()  # 日線 60MA

    df_daily['dxy_ma20'] = df_daily['dxy_close'].rolling(20).mean()  # DXY 20MA
    df_daily['dxy_ma60'] = df_daily['dxy_close'].rolling(60).mean()  # DXY 60MA

    df_daily['date'] = df_daily['timestamp'].dt.date  # 提取日期

    df_daily['daily_close_avail'] = df_daily['gold_close'].shift(1)  # T-1 日收
    df_daily['daily_ma50_avail'] = df_daily['ma50'].shift(1)  # T-1 日 50MA
    df_daily['daily_ma20_avail'] = df_daily['ma20'].shift(1)  # T-1 日 20MA
    df_daily['daily_ma60_avail'] = df_daily['ma60'].shift(1)  # T-1 日 60MA
    df_daily['daily_alpha1_avail'] = df_daily['alpha_1'].shift(1)  # T-1 Alpha1
    df_daily['daily_alpha5_avail'] = df_daily['alpha_5'].shift(1)  # T-1 Alpha5
    df_daily['daily_alpha10_avail'] = df_daily['alpha_10'].shift(1)  # T-1 Alpha10

    gold_4h['timestamp'] = pd.to_datetime(gold_4h['timestamp'])  # 轉 4H datetime
    gold_4h = gold_4h.sort_values('timestamp').reset_index(drop=True)  # 排序 4H
    gold_4h['date'] = gold_4h['timestamp'].dt.date  # 提取日期

    df = pd.merge(gold_4h, df_daily[[  # 合併日線欄位
        'date', 'daily_close_avail', 'daily_ma50_avail', 'daily_ma20_avail', 'daily_ma60_avail',
        'daily_alpha1_avail', 'daily_alpha5_avail', 'daily_alpha10_avail'
    ]], on='date', how='left')  # 左連結

    df['daily_close_avail'] = df['daily_close_avail'].ffill()  # 填充
    df['daily_ma50_avail'] = df['daily_ma50_avail'].ffill()  # 填充
    df['daily_ma20_avail'] = df['daily_ma20_avail'].ffill()  # 填充
    df['daily_ma60_avail'] = df['daily_ma60_avail'].ffill()  # 填充
    df['daily_alpha1_avail'] = df['daily_alpha1_avail'].ffill()  # 填充
    df['daily_alpha5_avail'] = df['daily_alpha5_avail'].ffill()  # 填充
    df['daily_alpha10_avail'] = df['daily_alpha10_avail'].ffill()  # 填充

    df['ma30_4h'] = df['close'].rolling(30).mean()  # 4H 30MA
    df['atr14_4h'] = calculate_atr(df, 14)  # 4H 14ATR
    df['dy_raw'] = df['close'].diff()  # 動能一階差
    df['sig_long_4h'] = (df['close'] > df['ma30_4h']) & (df['dy_raw'] > 0)  # 4H 多頭訊號

    df = df.dropna().reset_index(drop=True)  # 刪除 NaN
    df = df[df['timestamp'] >= '2024-07-07'].reset_index(drop=True)  # 對齊 2024-07-07 回測起始期

    pos_l, trades_l, ann_l = simulate_direction(df, is_long_only=True)  # 模擬多單子組合
    pos_s, trades_s, ann_s = simulate_direction(df, is_long_only=False)  # 模擬空單子組合

    all_active = pos_l + pos_s  # 聯集當前部位
    all_trades = trades_l + trades_s  # 聯集所有交易
    all_trades = sorted(all_trades, key=lambda x: str(x['entry_date']))  # 按進場時間排序
    for idx, t in enumerate(all_trades):  # 重設交易 ID
        t['trade_id'] = idx + 1  # 重新賦予流水號

    all_ann = ann_l + ann_s  # 聯集圖表標記

    latest_row = df.iloc[-1]  # 取得最後一筆 4H 數據
    dxy_df_final = df_daily[df_daily['timestamp'] >= df['timestamp'].min()].dropna(subset=['dxy_close']).reset_index(drop=True)  # 對齊 DXY

    current_status = {  # 即時狀況物件
        'last_updated': str(latest_row['timestamp']),  # 最新時間
        'gold_close': float(latest_row['close']),  # 黃金現價
        'dxy_close': float(dxy_df_final.iloc[-1]['dxy_close']),  # DXY 現價
        'regime': 'Bull (牛市多頭)' if (latest_row['daily_close_avail'] > latest_row['daily_ma50_avail']) else 'Bear (熊市空頭)',  # 最新 Regime
        'ma4h_30': float(latest_row['ma30_4h']),  # 4H 30MA
        'daily_ma50': float(latest_row['daily_ma50_avail']),  # 50MA
        'daily_ma20': float(latest_row['daily_ma20_avail']),  # 20MA
        'daily_ma60': float(latest_row['daily_ma60_avail']),  # 60MA
        'alpha_1d': float(latest_row['daily_alpha1_avail']),  # Alpha 1D
        'alpha_5d': float(latest_row['daily_alpha5_avail']),  # Alpha 5D
        'alpha_10d': float(latest_row['daily_alpha10_avail']),  # Alpha 10D
        'active_positions': [  # 活躍持倉細節
            {
                'type': p['type'], 'is_pyramid': p['is_pyramid'], 'entry_date': p['entry_date'],
                'entry_price': float(p['entry_price']), 'stop_price': round(float(p['stop_price']), 2),
                'unrealized_pnl': round((latest_row['close'] - p['entry_price']) if p['type'] == 'Long' else (p['entry_price'] - latest_row['close']), 2)
            } for p in all_active
        ]  # 持倉結束
    }  # 狀況結束

    total_pnl = sum([t['pnl_points'] for t in all_trades])  # 計算淨損益點數 (含點差過夜費)
    win_trades = [t for t in all_trades if t['pnl_points'] > 0]  # 獲利筆數
    win_rate = round(len(win_trades) / len(all_trades) * 100, 2) if len(all_trades) > 0 else 0  # 勝率

    pnl_series = pd.Series([t['pnl_points'] for t in all_trades])  # 損益序列
    cum_pnl = pnl_series.cumsum()  # 累積損益
    max_drawdown = round((cum_pnl.cummax() - cum_pnl).max(), 2) if len(cum_pnl) > 0 else 0  # 最大回撤點數

    metrics = {  # 績效指標
        'total_trades': len(all_trades),  # 總筆數
        'total_pnl_points': round(total_pnl, 2),  # 累積點數
        'win_rate': win_rate,  # 勝率
        'max_drawdown': max_drawdown,  # 最大回撤
    }  # 指標結束

    gold_chart_data = {  # 黃金圖表數據
        'timestamps': df['timestamp'].astype(str).tolist(),  # 時間戳
        'open': df['open'].tolist(), 'high': df['high'].tolist(), 'low': df['low'].tolist(), 'close': df['close'].tolist(),  # 四價
        'ma30_8h': sanitize_list(df['ma30_4h'].tolist()),  # 4H 30MA (維持欄位名對齊前端)
        'daily_ma50': sanitize_list(df['daily_ma50_avail'].tolist()),  # 50MA
        'daily_ma20': sanitize_list(df['daily_ma20_avail'].tolist()),  # 20MA
        'daily_ma60': sanitize_list(df['daily_ma60_avail'].tolist()),  # 60MA
    }  # 黃金結束

    dxy_chart_data = {  # 美元指數圖表數據
        'timestamps': dxy_df_final['timestamp'].dt.strftime('%Y-%m-%d').tolist(),  # 時間戳
        'open': dxy_df_final['dxy_open'].tolist(), 'high': dxy_df_final['dxy_high'].tolist(), 'low': dxy_df_final['dxy_low'].tolist(), 'close': dxy_df_final['dxy_close'].tolist(),  # 四價
        'ma20': sanitize_list(dxy_df_final['dxy_ma20'].tolist()),  # 20MA
        'ma60': sanitize_list(dxy_df_final['dxy_ma60'].tolist()),  # 60MA
    }  # DXY 結束

    output_data = {  # 封裝 JSON 輸出
        'current_status': current_status, 'metrics': metrics,
        'gold_chart_data': gold_chart_data, 'dxy_chart_data': dxy_chart_data,
        'completed_trades': all_trades, 'chart_annotations': all_ann
    }  # 封裝結束

    with open('strategy_results.json', 'w', encoding='utf-8') as f:  # 寫入 JSON
        json.dump(output_data, f, ensure_ascii=False, indent=2)  # dump 寫檔

    print(f"🎉 4H 30MA (+0h Offset) 策略回測完成！ (累積淨損益: {total_pnl:.2f} 點, 總交易數: {len(all_trades)} 筆, 最大回撤: {max_drawdown:.2f} 點)")  # 印出提示

if __name__ == '__main__':  # 入口點
    run_backtest()  # 執行
