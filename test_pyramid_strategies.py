import os  # 匯入作業系統模組
import pandas as pd  # 匯入 pandas 模組
import numpy as np  # 匯入 numpy 模組

def calculate_atr(df, period=14):  # 定義 ATR 計算函數
    high = df['high']  # 取得當期最高價
    low = df['low']  # 取得當期最低價
    close_prev = df['close'].shift(1)  # 取得前一期收盤價
    tr1 = high - low  # 計算當期高低差
    tr2 = (high - close_prev).abs()  # 計算最高價與前收絕對差
    tr3 = (low - close_prev).abs()  # 計算最低價與前收絕對差
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)  # 取三者最大值 TR
    return tr.rolling(period).mean()  # 回傳 ATR 序列

def prepare_data():  # 準備數據資料集
    daily_gc = 'comex_gc1!_daily.csv'  # 黃金日線路徑
    dxy_daily = 'iceus_dxy_daily.csv'  # 美元指數路徑
    tf_file = 'comex_gc1!_8h.csv'  # 8H K線路徑

    gold_df = pd.read_csv(daily_gc).rename(columns={'close': 'gold_close', 'open': 'gold_open', 'high': 'gold_high', 'low': 'gold_low'})[['timestamp', 'gold_open', 'gold_high', 'gold_low', 'gold_close']]  # 載入黃金
    dxy_df = pd.read_csv(dxy_daily).rename(columns={'close': 'dxy_close', 'open': 'dxy_open', 'high': 'dxy_high', 'low': 'dxy_low'})[['timestamp', 'dxy_open', 'dxy_high', 'dxy_low', 'dxy_close']]  # 載入美元

    df_daily = pd.merge(gold_df, dxy_df, on='timestamp', how='inner')  # 合併日線
    df_daily['timestamp'] = pd.to_datetime(df_daily['timestamp'])  # 轉 datetime
    df_daily = df_daily.sort_values('timestamp').reset_index(drop=True)  # 排序

    for n in [1, 5, 10]:  # 計算 Alpha 動能
        df_daily[f'gold_ret_{n}'] = df_daily['gold_close'].pct_change(n)  # 黃金報酬率
        df_daily[f'dxy_ret_{n}'] = df_daily['dxy_close'].pct_change(n)  # 美元報酬率
        df_daily[f'alpha_{n}'] = df_daily[f'gold_ret_{n}'] - df_daily[f'dxy_ret_{n}']  # Alpha 指標

    df_daily['ma20'] = df_daily['gold_close'].rolling(20).mean()  # 20MA
    df_daily['ma60'] = df_daily['gold_close'].rolling(60).mean()  # 60MA
    df_daily['ma50'] = df_daily['gold_close'].rolling(50).mean()  # 50MA
    df_daily['date'] = df_daily['timestamp'].dt.date  # 日期

    # 建立 T-1 可用日線指標
    df_daily['daily_close_avail'] = df_daily['gold_close'].shift(1)  # 昨日收盤
    df_daily['daily_ma50_avail'] = df_daily['ma50'].shift(1)  # 昨日 50MA
    df_daily['daily_alpha1_avail'] = df_daily['alpha_1'].shift(1)  # 昨日 Alpha1
    df_daily['daily_alpha5_avail'] = df_daily['alpha_5'].shift(1)  # 昨日 Alpha5
    df_daily['daily_alpha10_avail'] = df_daily['alpha_10'].shift(1)  # 昨日 Alpha10
    df_daily['daily_ma20_avail'] = df_daily['ma20'].shift(1)  # 昨日 20MA
    df_daily['daily_ma60_avail'] = df_daily['ma60'].shift(1)  # 昨日 60MA

    df_tf = pd.read_csv(tf_file)  # 讀取 8H
    df_tf['timestamp'] = pd.to_datetime(df_tf['timestamp'])  # 轉 datetime
    df_tf = df_tf.sort_values('timestamp').reset_index(drop=True)  # 排序
    df_tf['date'] = df_tf['timestamp'].dt.date  # 提取日期

    df = pd.merge(df_tf, df_daily[[  # 合併欄位
        'date', 'daily_close_avail', 'daily_ma50_avail',
        'daily_alpha1_avail', 'daily_alpha5_avail', 'daily_alpha10_avail',
        'daily_ma20_avail', 'daily_ma60_avail'
    ]], on='date', how='left')  # 左連結

    for col in ['daily_close_avail', 'daily_ma50_avail', 'daily_alpha1_avail', 'daily_alpha5_avail', 'daily_alpha10_avail', 'daily_ma20_avail', 'daily_ma60_avail']:  # 填充
        df[col] = df[col].ffill()  # 向上填充

    df['dy_raw'] = df['close'].diff()  # 差分
    df['ma'] = df['close'].rolling(30).mean()  # 30MA
    df['atr14'] = calculate_atr(df, 14)  # ATR
    df['sig_long'] = (df['close'] > df['ma']) & (df['dy_raw'] > 0)  # 時區多頭信號

    df = df.dropna().reset_index(drop=True)  # 去除缺失值
    df = df[df['timestamp'] >= '2024-07-07'].reset_index(drop=True)  # 過濾時間
    return df  # 回傳資料集

def run_strategy_sim(df, is_long_only=True, max_pyramid_count=1, min_profit_atr=0.0, require_breakout=False):  # 執行加倉測試模擬
    n = len(df)  # 資料筆數
    active_positions = []  # 持倉列表
    completed_trades = []  # 已完成交易

    for i in range(n - 1):  # 遍歷 K 線
        t_close = df.loc[i, 'close']  # 當期收盤
        t_high = df.loc[i, 'high']  # 當期最高
        t_low = df.loc[i, 'low']  # 當期最低
        t_atr = df.loc[i, 'atr14']  # 當期 ATR

        t_prev_high = df.loc[i-1, 'high'] if i > 0 else t_high  # 前一期最高
        t_prev_low = df.loc[i-1, 'low'] if i > 0 else t_low  # 前一期最低

        dy_close = df.loc[i, 'daily_close_avail']  # 日線收盤
        dy_ma50 = df.loc[i, 'daily_ma50_avail']  # 日線 50MA
        dy_a1 = df.loc[i, 'daily_alpha1_avail']  # 日線 Alpha1
        dy_a5 = df.loc[i, 'daily_alpha5_avail']  # 日線 Alpha5
        dy_a10 = df.loc[i, 'daily_alpha10_avail']  # 日線 Alpha10
        dy_ma20 = df.loc[i, 'daily_ma20_avail']  # 日線 20MA
        dy_ma60 = df.loc[i, 'daily_ma60_avail']  # 日線 60MA

        is_long_sig = df.loc[i, 'sig_long']  # 信號
        next_open = df.loc[i+1, 'open']  # 出場與進場價（下期開盤）
        next_date = pd.Timestamp(df.loc[i+1, 'timestamp'])  # 下期時間

        has_pos = len(active_positions) > 0  # 是否有持倉

        dy_pyramid_long = (dy_a1 > 0) & (dy_a5 > 0) & (dy_a10 > 0) & (dy_ma20 > dy_ma60)  # 加多條件
        dy_pyramid_short = (dy_a1 < 0) & (dy_a5 < 0) & (dy_a10 < 0) & (dy_ma20 < dy_ma60)  # 加空條件

        new_active = []  # 更新後的活躍部位

        if is_long_only:  # 多單邏輯
            if has_pos:  # 已持有部位
                main_pos = [p for p in active_positions if not p['is_pyramid']][0]  # 主部位
                pyr_positions = [p for p in active_positions if p['is_pyramid']]  # 加倉部位列表

                # 主部位觸發止損或趨勢轉空 -> 全清
                if t_close < main_pos['stop_price'] or not is_long_sig:  # 出場條件
                    for p in active_positions:  # 結算全部部位
                        holding_days = (next_date.date() - p['entry_date'].date()).days  # 持有天數
                        raw_pnl = next_open - p['entry_price']  # 原始損益
                        net_pnl = raw_pnl - 0.3 - (holding_days * 0.75)  # 扣點差過夜費
                        completed_trades.append({'type': 'Long', 'pnl': net_pnl, 'exit_date': next_date})  # 記錄
                    active_positions = []  # 清空部位
                else:  # 保留並檢查個別加倉部位
                    if t_close > t_prev_high:  # 移動止損
                        main_pos['stop_price'] = min(t_low, t_prev_low) - 1 * t_atr  # 更新主部位止損
                    new_active.append(main_pos)  # 保留主部位

                    for p_pos in pyr_positions:  # 檢查現有加倉部位
                        if t_close < p_pos['stop_price']:  # 加倉部位單獨止損
                            holding_days = (next_date.date() - p_pos['entry_date'].date()).days  # 持有天數
                            raw_pnl = next_open - p_pos['entry_price']  # 原始損益
                            net_pnl = raw_pnl - 0.3 - (holding_days * 0.75)  # 扣點差過夜費
                            completed_trades.append({'type': 'Long', 'pnl': net_pnl, 'exit_date': next_date})  # 記錄
                        else:  # 保留加倉部位
                            if t_close > t_prev_high:  # 移動止損
                                p_pos['stop_price'] = min(t_low, t_prev_low) - 1 * t_atr  # 更新加倉止損
                            new_active.append(p_pos)  # 保留

                    # 判斷是否滿足新加倉條件 (最多加至 max_pyramid_count 次)
                    current_pyr_count = len([p for p in new_active if p['is_pyramid']])  # 目前加倉次數
                    if current_pyr_count < max_pyramid_count and dy_close > dy_ma50 and dy_pyramid_long:  # 基本加倉條件
                        # 浮盈門檻檢查：上一筆部位（主部位或最新加倉）必須浮盈 >= min_profit_atr * ATR
                        last_pos = new_active[-1]  # 最新建立的部位
                        float_profit = t_close - last_pos['entry_price']  # 最新部位浮盈
                        pass_profit_check = (float_profit >= min_profit_atr * t_atr)  # 檢查浮盈門檻

                        # 突破門檻檢查：收盤價是否突破前高
                        pass_breakout_check = (not require_breakout) or (t_close > t_prev_high)  # 檢查突破門檻

                        if pass_profit_check and pass_breakout_check:  # 通過所有門檻
                            new_active.append({  # 建立新加倉部位
                                'type': 'Long', 'is_pyramid': True, 'pyr_idx': current_pyr_count + 1,
                                'entry_date': next_date, 'entry_price': next_open,
                                'stop_price': min(t_low, t_prev_low) - 1 * t_atr  # 加倉止損價
                            })  # 建立結束

                    active_positions = new_active  # 更新部位
            else:  # 空手建立主多單
                if dy_close > dy_ma50 and is_long_sig:  # 建倉條件
                    active_positions.append({  # 建立主多單
                        'type': 'Long', 'is_pyramid': False, 'pyr_idx': 0,
                        'entry_date': next_date, 'entry_price': next_open,
                        'stop_price': min(t_low, t_prev_low) - 1 * t_atr  # 止損價
                    })  # 建立結束

        else:  # 空單邏輯
            if has_pos:  # 持有空單
                main_pos = [p for p in active_positions if not p['is_pyramid']][0]  # 主部位
                pyr_positions = [p for p in active_positions if p['is_pyramid']]  # 加倉部位列表

                if t_close > main_pos['stop_price'] or is_long_sig:  # 止損或轉多
                    for p in active_positions:  # 結算全部部位
                        holding_days = (next_date.date() - p['entry_date'].date()).days  # 持有天數
                        raw_pnl = p['entry_price'] - next_open  # 原始損益
                        net_pnl = raw_pnl - 0.3 + (holding_days * 0.27)  # 扣點差加利息
                        completed_trades.append({'type': 'Short', 'pnl': net_pnl, 'exit_date': next_date})  # 記錄
                    active_positions = []  # 清空部位
                else:  # 保留並檢查個別加倉部位
                    if t_close < t_prev_low:  # 移動止損
                        main_pos['stop_price'] = max(t_high, t_prev_high) + 1 * t_atr  # 更新主部位止損
                    new_active.append(main_pos)  # 保留主部位

                    for p_pos in pyr_positions:  # 檢查現有加空部位
                        if t_close > p_pos['stop_price']:  # 加空部位單獨止損
                            holding_days = (next_date.date() - p_pos['entry_date'].date()).days  # 持有天數
                            raw_pnl = p_pos['entry_price'] - next_open  # 原始損益
                            net_pnl = raw_pnl - 0.3 + (holding_days * 0.27)  # 扣點差加利息
                            completed_trades.append({'type': 'Short', 'pnl': net_pnl, 'exit_date': next_date})  # 記錄
                        else:  # 保留加空部位
                            if t_close < t_prev_low:  # 移動止損
                                p_pos['stop_price'] = max(t_high, t_prev_high) + 1 * t_atr  # 更新加空止損
                            new_active.append(p_pos)  # 保留

                    current_pyr_count = len([p for p in new_active if p['is_pyramid']])  # 目前加空次數
                    if current_pyr_count < max_pyramid_count and dy_close < dy_ma50 and dy_pyramid_short:  # 基本加空條件
                        last_pos = new_active[-1]  # 最新部位
                        float_profit = last_pos['entry_price'] - t_close  # 浮盈點數
                        pass_profit_check = (float_profit >= min_profit_atr * t_atr)  # 浮盈門檻
                        pass_breakout_check = (not require_breakout) or (t_close < t_prev_low)  # 跌破門檻

                        if pass_profit_check and pass_breakout_check:  # 通過門檻
                            new_active.append({  # 建立新加空部位
                                'type': 'Short', 'is_pyramid': True, 'pyr_idx': current_pyr_count + 1,
                                'entry_date': next_date, 'entry_price': next_open,
                                'stop_price': max(t_high, t_prev_high) + 1 * t_atr  # 加空止損價
                            })  # 建立結束

                    active_positions = new_active  # 更新部位
            else:  # 空手建立主空單
                if dy_close < dy_ma50 and not is_long_sig:  # 建倉條件
                    active_positions.append({  # 建立主空單
                        'type': 'Short', 'is_pyramid': False, 'pyr_idx': 0,
                        'entry_date': next_date, 'entry_price': next_open,
                        'stop_price': max(t_high, t_prev_high) + 1 * t_atr  # 止損價
                    })  # 建立結束

    if len(active_positions) > 0:  # 未平倉強制結算
        last_close = df.loc[n-1, 'close']  # 最後價格
        last_date = pd.Timestamp(df.loc[n-1, 'timestamp'])  # 最後日期
        for p in active_positions:  # 遍歷部位
            holding_days = (last_date.date() - p['entry_date'].date()).days  # 持有天數
            raw_pnl = (last_close - p['entry_price']) if p['type'] == 'Long' else (p['entry_price'] - last_close)  # 點數
            ov_fee = 0.75 if p['type'] == 'Long' else -0.27  # 隔夜費
            net_pnl = raw_pnl - 0.3 - (holding_days * ov_fee)  # 淨損益
            completed_trades.append({'type': p['type'], 'pnl': net_pnl, 'exit_date': last_date})  # 記錄

    return completed_trades  # 回傳交易紀錄

def eval_trades(trades):  # 計算指標摘要
    if not trades: return {'total_pnl': 0, 'max_dd': 0, 'sharpe': 0, 'trades': 0, 'win_rate': '0%'}  # 空值保護
    df_t = pd.DataFrame(trades).sort_values('exit_date').reset_index(drop=True)  # 轉 DataFrame
    pnl = df_t['pnl']  # PnL
    cum_pnl = pnl.cumsum()  # 累積損益
    max_dd = (cum_pnl.cummax() - cum_pnl).max()  # 最大回撤點數
    n = len(df_t)  # 筆數
    win_rate = (pnl > 0).mean()  # 勝率
    years = (pd.Timestamp(df_t['exit_date'].max()).date() - pd.Timestamp(df_t['exit_date'].min()).date()).days / 365.25  # 回測年數
    ann_mean = pnl.mean() * (n / years) if years > 0 else 0  # 年化平均
    ann_std = pnl.std() * np.sqrt(n / years) if years > 0 else 0  # 年化標差
    sharpe = ann_mean / ann_std if ann_std > 0 else 0  # 夏普
    return {
        'total_pnl': round(cum_pnl.iloc[-1], 2),  # 累積點數
        'max_dd': round(max_dd, 2),  # 最大回撤
        'sharpe': round(sharpe, 3),  # 夏普
        'win_rate': f'{win_rate:.1%}',  # 勝率
        'trades': n  # 總筆數
    }

def main():  # 主測試進入點
    df = prepare_data()  # 準備數據

    experiments = [  # 實驗配置列表
        ("1. 不加倉 (僅建主單 1 筆)", 0, 0.0, False),  # 方案1
        ("2. 現行方案 (最多加倉 1 次，無浮盈限制)", 1, 0.0, False),  # 方案2 (現行基準)
        ("3. 最多加倉 2 次 (無浮盈限制)", 2, 0.0, False),  # 方案3
        ("4. 最多加倉 3 次 (無浮盈限制)", 3, 0.0, False),  # 方案4
        ("5. 最多加倉 2 次 (需目前部位浮盈 >= 1.0 * ATR)", 2, 1.0, False),  # 方案5 (浮盈1ATR)
        ("6. 最多加倉 2 次 (需目前部位浮盈 >= 1.5 * ATR)", 2, 1.5, False),  # 方案6 (浮盈1.5ATR)
        ("7. 最多加倉 2 次 (需浮盈 >= 1.0*ATR 且突破新高/新低)", 2, 1.0, True),  # 方案7 (突破+浮盈)
    ]

    print("========================================================================================")
    print(" 🧪 黃金混合策略加倉機制 (Pyramiding) 測試結果對比 (2024/07 - 至今)")
    print("========================================================================================")
    header = f"{'實驗方案':<45} | {'總損益 (pts)':>12} | {'MDD (pts)':>10} | {'Sharpe':>8} | {'勝率':>8} | {'總筆數':>6}"
    print(header)
    print("-" * len(header))

    for label, max_p, min_prof, req_bk in experiments:
        t_l = run_strategy_sim(df, is_long_only=True, max_pyramid_count=max_p, min_profit_atr=min_prof, require_breakout=req_bk)  # 多單
        t_s = run_strategy_sim(df, is_long_only=False, max_pyramid_count=max_p, min_profit_atr=min_prof, require_breakout=req_bk)  # 空單
        res = eval_trades(t_l + t_s)  # 合併評估
        print(f"{label:<45} | {res['total_pnl']:>12.2f} | {res['max_dd']:>10.2f} | {res['sharpe']:>8.3f} | {res['win_rate']:>8} | {res['trades']:>6}")

if __name__ == '__main__':
    main()
