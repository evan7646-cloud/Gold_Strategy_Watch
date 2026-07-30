import pandas as pd # 匯入 pandas 模組處理數據
import numpy as np # 匯入 numpy 模組進行數值運算
from tvDatafeed import TvDatafeed, Interval # 匯入 tvDatafeed 抓取歷史 K 線

def calculate_atr(df, period=14): # 定義計算 14 週期 ATR 函數
    high = df['high'] # 最高價
    low = df['low'] # 最低價
    close_prev = df['close'].shift(1) # 前收價
    tr1 = high - low # 當期幅
    tr2 = (high - close_prev).abs() # 高前收差絕對值
    tr3 = (low - close_prev).abs() # 低前收差絕對值
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1) # 取最大值為 TR
    return tr.rolling(period).mean() # 回傳滑動 14 週期均值

def run_backtest_simulation(df, ma_col='ma', atr_col='atr'): # 定義通用雙向交易回測引擎
    n = len(df) # 資料筆數
    
    def simulate_direction(is_long_only=True): # 單向模擬子函數
        active_positions = [] # 當前部位
        completed_trades = [] # 完結交易
        
        for i in range(n - 1): # 遍歷資料列
            t_close = df.loc[i, 'close'] # 當前收盤價
            t_high = df.loc[i, 'high'] # 當前最高價
            t_low = df.loc[i, 'low'] # 當前最低價
            t_atr = df.loc[i, atr_col] # 當前 ATR
            t_prev_high = df.loc[i-1, 'high'] if i > 0 else t_high # 前一根高
            t_prev_low = df.loc[i-1, 'low'] if i > 0 else t_low # 前一根低
            
            dy_close = df.loc[i, 'daily_close_avail'] # 日線前收
            dy_ma50 = df.loc[i, 'daily_ma50_avail'] # 日線前 50MA
            dy_ma20 = df.loc[i, 'daily_ma20_avail'] # 日線前 20MA
            dy_ma60 = df.loc[i, 'daily_ma60_avail'] # 日線前 60MA
            dy_a1 = df.loc[i, 'daily_alpha1_avail'] # Alpha1
            dy_a5 = df.loc[i, 'daily_alpha5_avail'] # Alpha5
            dy_a10 = df.loc[i, 'daily_alpha10_avail'] # Alpha10
            
            is_long_sig = df.loc[i, 'sig_long'] # 當前買入訊號
            next_open = df.loc[i+1, 'open'] # 下一根開盤價
            next_stamp = str(df.loc[i+1, 'timestamp']) # 下一根時間戳
            
            dy_pyramid_long = (dy_a1 > 0) and (dy_a5 > 0) and (dy_a10 > 0) and (dy_ma20 > dy_ma60) # 加多條件
            dy_pyramid_short = (dy_a1 < 0) and (dy_a5 < 0) and (dy_a10 < 0) and (dy_ma20 < dy_ma60) # 加空條件
            
            has_pos = len(active_positions) > 0 # 是否有部位
            new_active = [] # 新部位串列
            
            if is_long_only: # 多單邏輯
                if has_pos: # 有持倉
                    main_pos = [p for p in active_positions if not p['is_pyramid']][0] # 主多單
                    pyr_pos = [p for p in active_positions if p['is_pyramid']] # 加多單
                    has_pyr = len(pyr_pos) > 0 # 是否有加多
                    
                    if t_close < main_pos['stop_price'] or not is_long_sig: # 觸發平倉
                        exit_reason = "Stop Loss Exit" if t_close < main_pos['stop_price'] else "Signal Exit" # 平倉原因
                        for p in active_positions: # 遍歷部位計算 PnL
                            holding_days = (pd.to_datetime(next_stamp).date() - pd.to_datetime(p['entry_date']).date()).days # 持有天數
                            raw_pnl = next_open - p['entry_price'] # 原始點數
                            net_pnl_unit = raw_pnl - 0.3 - (holding_days * 0.75) # 扣除成本與隔夜利息
                            net_pnl = net_pnl_unit * p.get('units', 1.0) # 加權 PnL
                            completed_trades.append({ # 紀錄平倉
                                'type': 'Long', 'is_pyramid': p['is_pyramid'], 'units': p.get('units', 1.0),
                                'entry_date': p['entry_date'], 'exit_date': next_stamp, 'pnl_points': net_pnl
                            })
                        active_positions = [] # 清空持倉
                    else: # 未平倉
                        if t_close > t_prev_high: # 創新高移動停損
                            main_pos['stop_price'] = min(t_low, t_prev_low) - 1.0 * t_atr # 移動停損
                        new_active.append(main_pos) # 保留主多
                        
                        if has_pyr: # 處理加多單
                            p_pos = pyr_pos[0] # 加多部位
                            if t_close < p_pos['stop_price']: # 觸發加多停損
                                holding_days = (pd.to_datetime(next_stamp).date() - pd.to_datetime(p_pos['entry_date']).date()).days # 天數
                                raw_pnl = next_open - p_pos['entry_price'] # 點數
                                net_pnl_unit = raw_pnl - 0.3 - (holding_days * 0.75) # 淨點數
                                net_pnl = net_pnl_unit * p_pos.get('units', 1.0) # 加權 PnL
                                completed_trades.append({ # 紀錄平倉加多
                                    'type': 'Long', 'is_pyramid': True, 'units': p_pos.get('units', 1.0),
                                    'entry_date': p_pos['entry_date'], 'exit_date': next_stamp, 'pnl_points': net_pnl
                                })
                            else: # 創新高移動加多停損
                                if t_close > t_prev_high:
                                    p_pos['stop_price'] = min(t_low, t_prev_low) - 1.0 * t_atr # 更新停損
                                new_active.append(p_pos) # 保留加多
                        else: # 檢查加多條件
                            if dy_close > dy_ma50 and dy_pyramid_long: # 滿足加多
                                pyr_units = 2.0 if dy_a10 > 0.03 else 1.0 # 強勢倍數
                                new_active.append({ # 新增加多部位
                                    'type': 'Long', 'is_pyramid': True, 'units': pyr_units, 'entry_date': next_stamp,
                                    'entry_price': next_open, 'stop_price': min(t_low, t_prev_low) - 1.0 * t_atr
                                })
                        active_positions = new_active # 更新部位
                else: # 空手檢查主多建倉
                    if dy_close > dy_ma50 and is_long_sig: # 滿足主多條件
                        active_positions.append({ # 建立主多
                            'type': 'Long', 'is_pyramid': False, 'units': 1.0, 'entry_date': next_stamp,
                            'entry_price': next_open, 'stop_price': min(t_low, t_prev_low) - 1.0 * t_atr
                        })
            else: # 空單邏輯
                if has_pos: # 有空單
                    main_pos = [p for p in active_positions if not p['is_pyramid']][0] # 主空單
                    pyr_pos = [p for p in active_positions if p['is_pyramid']] # 加空單
                    has_pyr = len(pyr_pos) > 0 # 是否有加空
                    
                    if t_close > main_pos['stop_price'] or is_long_sig: # 觸發平倉
                        exit_reason = "Stop Loss Exit" if t_close > main_pos['stop_price'] else "Signal Exit" # 原因
                        for p in active_positions: # 遍歷計算 PnL
                            holding_days = (pd.to_datetime(next_stamp).date() - pd.to_datetime(p['entry_date']).date()).days # 天數
                            raw_pnl = p['entry_price'] - next_open # 點數
                            net_pnl_unit = raw_pnl - 0.3 + (holding_days * 0.27) # 扣成本加利息
                            net_pnl = net_pnl_unit * p.get('units', 1.0) # 加權 PnL
                            completed_trades.append({ # 紀錄平倉
                                'type': 'Short', 'is_pyramid': p['is_pyramid'], 'units': p.get('units', 1.0),
                                'entry_date': p['entry_date'], 'exit_date': next_stamp, 'pnl_points': net_pnl
                            })
                        active_positions = [] # 清空
                    else: # 保留空單
                        if t_close < t_prev_low: # 創新低移動停損
                            main_pos['stop_price'] = max(t_high, t_prev_high) + 1.0 * t_atr # 移動停損
                        new_active.append(main_pos) # 保留主空
                        
                        if has_pyr: # 處理加空單
                            p_pos = pyr_pos[0] # 加空部位
                            if t_close > p_pos['stop_price']: # 觸發加空停損
                                holding_days = (pd.to_datetime(next_stamp).date() - pd.to_datetime(p_pos['entry_date']).date()).days # 天數
                                raw_pnl = p_pos['entry_price'] - next_open # 點數
                                net_pnl_unit = raw_pnl - 0.3 + (holding_days * 0.27) # 淨 PnL
                                net_pnl = net_pnl_unit * p_pos.get('units', 1.0) # 加權 PnL
                                completed_trades.append({ # 紀錄平倉
                                    'type': 'Short', 'is_pyramid': True, 'units': p_pos.get('units', 1.0),
                                    'entry_date': p_pos['entry_date'], 'exit_date': next_stamp, 'pnl_points': net_pnl
                                })
                            else: # 創新低移動加空停損
                                if t_close < t_prev_low:
                                    p_pos['stop_price'] = max(t_high, t_prev_high) + 1.0 * t_atr # 更新停損
                                new_active.append(p_pos) # 保留加空
                        else: # 檢查加空條件
                            if dy_close < dy_ma50 and dy_pyramid_short: # 滿足加空
                                pyr_units = 2.0 if dy_a10 < -0.03 else 1.0 # 強勢倍數
                                new_active.append({ # 新增加空部位
                                    'type': 'Short', 'is_pyramid': True, 'units': pyr_units, 'entry_date': next_stamp,
                                    'entry_price': next_open, 'stop_price': max(t_high, t_prev_high) + 1.0 * t_atr
                                })
                        active_positions = new_active # 更新部位
                else: # 空手檢查主空建倉
                    if dy_close < dy_ma50 and not is_long_sig: # 滿足主空條件
                        active_positions.append({ # 建立主空
                            'type': 'Short', 'is_pyramid': False, 'units': 1.0, 'entry_date': next_stamp,
                            'entry_price': next_open, 'stop_price': max(t_high, t_prev_high) + 1.0 * t_atr
                        })
        return completed_trades # 回傳完成交易列表
        
    trades_l = simulate_direction(is_long_only=True) # 跑多單回測
    trades_s = simulate_direction(is_long_only=False) # 跑空單回測
    all_trades = trades_l + trades_s # 合併多空交易
    
    if not all_trades: # 若無交易
        return {
            'total_trades': 0, 'total_pnl': 0.0, 'win_rate': 0.0, 'max_dd': 0.0,
            'profit_factor': 0.0, 'sharpe_ratio': 0.0, 'calmar_ratio': 0.0
        }
        
    df_trades = pd.DataFrame(all_trades).sort_values('entry_date').reset_index(drop=True) # 轉成 DataFrame 排序
    df_trades['cum_pnl'] = df_trades['pnl_points'].cumsum() # 計算累積損益
    
    total_trades = len(df_trades) # 總交易數
    total_pnl = df_trades['pnl_points'].sum() # 總淨損益
    win_trades = len(df_trades[df_trades['pnl_points'] > 0]) # 勝場數
    win_rate = (win_trades / total_trades) * 100 # 勝率
    
    # 計算最大回撤 (Max Drawdown)
    cum_pnl = df_trades['cum_pnl'] # 累積點數
    running_max = cum_pnl.cummax() # 累積最高點
    dd = running_max - cum_pnl # 當前點數回撤
    max_dd = dd.max() # 最大點數回撤
    
    # Profit Factor
    gross_profit = df_trades[df_trades['pnl_points'] > 0]['pnl_points'].sum() # 總盈利
    gross_loss = abs(df_trades[df_trades['pnl_points'] < 0]['pnl_points'].sum()) # 總虧損
    pf = (gross_profit / gross_loss) if gross_loss > 0 else np.nan # 風險獲利比 PF
    
    # 計算每日 PnL 序列以計算年化夏普比率 (Sharpe Ratio)
    df_trades['exit_date_dt'] = pd.to_datetime(df_trades['exit_date']) # 轉 datetime
    df_trades['exit_day'] = df_trades['exit_date_dt'].dt.date # 轉日期
    daily_pnl = df_trades.groupby('exit_day')['pnl_points'].sum() # 依日期聚合每日 PnL
    
    mean_daily_pnl = daily_pnl.mean() # 日均 PnL
    std_daily_pnl = daily_pnl.std() # 日 PnL 標準差
    
    if std_daily_pnl > 0:
        sharpe_ratio = (mean_daily_pnl / std_daily_pnl) * np.sqrt(252) # 夏普比率公式
    else:
        sharpe_ratio = 0.0
        
    start_dt = pd.to_datetime(df_trades['entry_date'].min()) # 首筆交易時間
    end_dt = pd.to_datetime(df_trades['exit_date'].max()) # 末筆交易時間
    total_years = max((end_dt - start_dt).days / 365.25, 0.5) # 回測年數
    
    annualized_pnl = total_pnl / total_years # 年化點數收益
    calmar_ratio = (annualized_pnl / max_dd) if max_dd > 0 else 0.0 # 卡爾瑪比率
    
    return {
        'total_trades': total_trades,
        'total_pnl': round(total_pnl, 2),
        'win_rate': round(win_rate, 2),
        'max_dd': round(max_dd, 2),
        'profit_factor': round(pf, 2) if not np.isnan(pf) else 0.0,
        'sharpe_ratio': round(sharpe_ratio, 2),
        'calmar_ratio': round(calmar_ratio, 2)
    }

def main(): # 主流程函數
    print("🚀 開始執行 XAUUSD (Spot Gold) 全動態 4H vs 8H 包括 Sharpe Ratio & Calmar Ratio 完整比較...") # 提示訊息
    
    tv = TvDatafeed() # 初始化 TradingView
    df_gold_1h = tv.get_hist(symbol='XAUUSD', exchange='PEPPERSTONE', interval=Interval.in_1_hour, n_bars=10000) # 抓取 Pepperstone XAUUSD 1H K線以合成各 Offset K線
    if df_gold_1h is None or df_gold_1h.empty: # 降級處理
        df_gold_1h = pd.read_csv('comex_gc1!_4h.csv') # Local fallback

    df_gold_1h = df_gold_1h.reset_index() # 重設索引
    df_gold_1h['datetime'] = df_gold_1h['datetime'].dt.tz_localize('UTC').dt.tz_convert('Asia/Taipei') # 轉台北時間
    df_gold_1h = df_gold_1h.rename(columns={'datetime': 'timestamp'}) # 欄位重命名
    
    df_gold_d = pd.read_csv('comex_gc1!_daily.csv') # 讀取日線黃金
    df_dxy_d = pd.read_csv('iceus_dxy_daily.csv') # 讀取日線美元
    
    df_gold_d = df_gold_d.rename(columns={'close': 'gold_close'}) # 重命名欄位
    df_dxy_d = df_dxy_d.rename(columns={'close': 'dxy_close'}) # 重命名欄位
    
    df_daily = pd.merge(df_gold_d, df_dxy_d, on='timestamp', how='inner') # 合併日線
    df_daily['timestamp'] = pd.to_datetime(df_daily['timestamp']) # 轉 datetime
    df_daily = df_daily.sort_values('timestamp').reset_index(drop=True) # 排序
    
    for n in [1, 5, 10]: # 計算 Alpha
        df_daily[f'gold_ret_{n}'] = df_daily['gold_close'].pct_change(n) # 黃金收益
        df_daily[f'dxy_ret_{n}'] = df_daily['dxy_close'].pct_change(n) # 美元收益
        df_daily[f'alpha_{n}'] = df_daily[f'gold_ret_{n}'] - df_daily[f'dxy_ret_{n}'] # Alpha
        
    df_daily['ma20'] = df_daily['gold_close'].rolling(20).mean() # 日 20MA
    df_daily['ma50'] = df_daily['gold_close'].rolling(50).mean() # 日 50MA
    df_daily['ma60'] = df_daily['gold_close'].rolling(60).mean() # 日 60MA
    df_daily['date'] = df_daily['timestamp'].dt.date # 日期
    
    df_daily['daily_close_avail'] = df_daily['gold_close'].shift(1) # T-1
    df_daily['daily_ma50_avail'] = df_daily['ma50'].shift(1) # T-1
    df_daily['daily_ma20_avail'] = df_daily['ma20'].shift(1) # T-1
    df_daily['daily_ma60_avail'] = df_daily['ma60'].shift(1) # T-1
    df_daily['daily_alpha1_avail'] = df_daily['alpha_1'].shift(1) # T-1
    df_daily['daily_alpha5_avail'] = df_daily['alpha_5'].shift(1) # T-1
    df_daily['daily_alpha10_avail'] = df_daily['alpha_10'].shift(1) # T-1

    results = [] # 儲存結果矩陣
    
    # 測試維度定義
    configs = [
        ('4H', 30, [0, 1, 2, 3]),
        ('4H', 50, [0, 1, 2, 3]),
        ('8H', 30, [0, 2, 4, 6]),
        ('8H', 50, [0, 2, 4, 6])
    ]
    
    for tf, ma_period, offsets in configs: # 遍歷所有配置
        for offset in offsets: # 遍歷時間偏移
            df_base = df_gold_1h.copy() # 複製基礎數據
            df_base.set_index('timestamp', inplace=True) # 設為索引
            
            origin_tz = pd.Timestamp(f'2024-01-01 {offset:02d}:00:00', tz='Asia/Taipei') # 建立 offset 時間戳
            rule = '4h' if tf == '4H' else '8h' # 規則名稱
            
            df_res = df_base.resample(rule, origin=origin_tz).agg({ # 重取樣
                'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
            }).dropna().reset_index() # 去除空值
            
            df_res['date'] = df_res['timestamp'].dt.date # 提日期
            
            # 合併日線狀態
            df_merged = pd.merge(df_res, df_daily[[
                'date', 'daily_close_avail', 'daily_ma50_avail', 'daily_ma20_avail', 'daily_ma60_avail',
                'daily_alpha1_avail', 'daily_alpha5_avail', 'daily_alpha10_avail'
            ]], on='date', how='left')
            
            # 前向填充日線數據
            cols_to_ffill = ['daily_close_avail', 'daily_ma50_avail', 'daily_ma20_avail', 'daily_ma60_avail',
                             'daily_alpha1_avail', 'daily_alpha5_avail', 'daily_alpha10_avail']
            df_merged[cols_to_ffill] = df_merged[cols_to_ffill].ffill() # 填充
            
            # 計算指標
            df_merged['ma_val'] = df_merged['close'].rolling(ma_period).mean() # MA 均線
            df_merged['atr_val'] = calculate_atr(df_merged, 14) # ATR
            df_merged['dy_raw'] = df_merged['close'].diff() # 一階動能
            df_merged['sig_long'] = (df_merged['close'] > df_merged['ma_val']) & (df_merged['dy_raw'] > 0) # 多頭訊號
            
            df_merged = df_merged.dropna().reset_index(drop=True) # 刪除 NaN
            df_merged = df_merged[df_merged['timestamp'] >= '2024-07-07'].reset_index(drop=True) # 對齊 2024-07-07 起始回測期
            
            metrics = run_backtest_simulation(df_merged, ma_col='ma_val', atr_col='atr_val') # 執行回測
            
            results.append({
                'Timeframe': tf,
                'MA_Period': ma_period,
                'Offset_Hours': f"+{offset}h",
                'Total_PnL': metrics['total_pnl'],
                'Sharpe_Ratio': metrics['sharpe_ratio'],
                'Calmar_Ratio': metrics['calmar_ratio'],
                'Profit_Factor': metrics['profit_factor'],
                'Win_Rate_%': metrics['win_rate'],
                'Max_Drawdown': metrics['max_dd'],
                'Total_Trades': metrics['total_trades']
            })

    res_df = pd.DataFrame(results) # 轉成 Pandas DataFrame
    res_df = res_df.sort_values(by='Sharpe_Ratio', ascending=False).reset_index(drop=True) # 依 Sharpe Ratio 排序
    
    print("\n================ 📊 XAUUSD (Spot Gold 2024-07起) 指標比較排行榜 (依 Sharpe Ratio 排序) ================")
    print(res_df.to_string(index=False)) # 印出完整結果表格
    res_df.to_csv('backtest_4h_8h_full_metrics_xauusd.csv', index=False) # 儲存完整比較 CSV
    print("\n✅ XAUUSD 風險收益指標比較已匯出至 backtest_4h_8h_full_metrics_xauusd.csv")

if __name__ == '__main__':
    main() # 執行主程式
