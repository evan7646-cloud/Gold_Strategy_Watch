import os  # 匯入作業系統模組
import pandas as pd  # 匯入 pandas 模組
import numpy as np  # 匯入 numpy 模組
import matplotlib.pyplot as plt  # 匯入 matplotlib 繪圖模組

def calculate_atr(df, period=14):  # 定義 ATR 計算函數
    high = df['high']  # 取得當期最高價
    low = df['low']  # 取得當期最低價
    close_prev = df['close'].shift(1)  # 取得前一期收盤價
    tr1 = high - low  # 計算當期高低差
    tr2 = (high - close_prev).abs()  # 計算當期最高價與前一期收盤價的絕對差值
    tr3 = (low - close_prev).abs()  # 計算當期最低價與前一期收盤價的絕對差值
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)  # 取三者最大值作為 TR
    atr = tr.rolling(period).mean()  # 計算 ATR
    return atr  # 回傳 ATR 序列

def run_strategy(tf_file, ma_period, tf_name, df_daily, is_long_only=True):  # 執行單向策略回測
    df_tf = pd.read_csv(tf_file)  # 載入時區資料 CSV
    df_tf['timestamp'] = pd.to_datetime(df_tf['timestamp'])  # 將 timestamp 轉為 datetime 格式
    df_tf = df_tf.sort_values('timestamp').reset_index(drop=True)  # 依時間排序並重設索引
    df_tf['date'] = df_tf['timestamp'].dt.date  # 提取日期

    # 合併日線過濾與加倉指標
    df = pd.merge(df_tf, df_daily[[
        'date', 'daily_close_avail', 'daily_ma50_avail',
        'daily_alpha1_avail', 'daily_alpha5_avail', 'daily_alpha10_avail',
        'daily_ma20_avail', 'daily_ma60_avail'
    ]], on='date', how='left')  # 合併欄位

    # 填充缺失值
    df['daily_close_avail'] = df['daily_close_avail'].ffill()  # 填充收盤價
    df['daily_ma50_avail'] = df['daily_ma50_avail'].ffill()  # 填充 50MA
    df['daily_alpha1_avail'] = df['daily_alpha1_avail'].ffill()  # 填充 Alpha1
    df['daily_alpha5_avail'] = df['daily_alpha5_avail'].ffill()  # 填充 Alpha5
    df['daily_alpha10_avail'] = df['daily_alpha10_avail'].ffill()  # 填充 Alpha10
    df['daily_ma20_avail'] = df['daily_ma20_avail'].ffill()  # 填充 20MA
    df['daily_ma60_avail'] = df['daily_ma60_avail'].ffill()  # 填充 60MA

    df['dy_raw'] = df['close'].diff()  # 計算時區收盤價一階差分
    df['ma'] = df['close'].rolling(ma_period).mean()  # 計算 MA
    df['atr14'] = calculate_atr(df, 14)  # 計算 ATR
    df['sig_long'] = (df['close'] > df['ma']) & (df['dy_raw'] > 0)  # 判斷時區多頭信號

    df = df.dropna().reset_index(drop=True)  # 刪除缺失值
    df = df[df['timestamp'] >= '2024-07-07'].reset_index(drop=True)  # 篩選回測時間

    n = len(df)  # 資料長度
    active_positions = []  # 持倉列表
    completed_trades = []  # 已完成交易

    # 交易模擬主迴圈
    for i in range(n - 1):  # 遍歷每日資料
        t_close = df.loc[i, 'close']  # 當期收盤價
        t_high = df.loc[i, 'high']  # 當期最高價
        t_low = df.loc[i, 'low']  # 當期最低價
        t_atr = df.loc[i, 'atr14']  # 當期 ATR

        t_prev_high = df.loc[i-1, 'high'] if i > 0 else t_high  # 昨日最高價
        t_prev_low = df.loc[i-1, 'low'] if i > 0 else t_low  # 昨日最低價

        # 今日可用日線指標
        dy_close = df.loc[i, 'daily_close_avail']  # 日線收盤價
        dy_ma50 = df.loc[i, 'daily_ma50_avail']  # 日線 50MA
        dy_a1 = df.loc[i, 'daily_alpha1_avail']  # 日線 Alpha1
        dy_a5 = df.loc[i, 'daily_alpha5_avail']  # 日線 Alpha5
        dy_a10 = df.loc[i, 'daily_alpha10_avail']  # 日線 Alpha10
        dy_ma20 = df.loc[i, 'daily_ma20_avail']  # 日線 20MA
        dy_ma60 = df.loc[i, 'daily_ma60_avail']  # 日線 60MA

        is_long_sig = df.loc[i, 'sig_long']  # 多頭信號

        next_open = df.loc[i+1, 'open']  # 下期開盤價（實際出場價格）
        next_date = pd.Timestamp(df.loc[i+1, 'timestamp'])  # 下期日期

        has_pos = len(active_positions) > 0  # 是否持有部位

        # 加多與加空訊號定義
        dy_pyramid_long = (dy_a1 > 0) & (dy_a5 > 0) & (dy_a10 > 0) & (dy_ma20 > dy_ma60)  # 加多
        dy_pyramid_short = (dy_a1 < 0) & (dy_a5 < 0) & (dy_a10 < 0) & (dy_ma20 < dy_ma60)  # 加空

        new_active = []  # 新持倉

        if is_long_only:  # 多單方向策略
            if has_pos:  # 持有多單
                main_pos = [p for p in active_positions if not p['is_pyramid']][0]  # 主部位
                pyr_pos = [p for p in active_positions if p['is_pyramid']]  # 加倉部位
                has_pyr = len(pyr_pos) > 0  # 是否有加多部位

                # 出場條件（8H 止損或 8H 動能轉空）
                if t_close < main_pos['stop_price'] or not is_long_sig:  # 止損或信號轉空
                    for p in active_positions:  # 平倉所有部位
                        p_holding_days = (next_date.date() - p['entry_date'].date()).days  # 計算持有跨日天數
                        raw_pnl = next_open - p['entry_price']  # 原始平倉損益（用 i+1 open 出場）
                        net_pnl = raw_pnl - 0.3 - (p_holding_days * 0.75)  # 扣除點差與過夜費
                        completed_trades.append({  # 記錄交易
                            'type': 'Long', 'is_pyramid': p['is_pyramid'],
                            'entry_date': p['entry_date'], 'exit_date': next_date,
                            'entry_price': p['entry_price'], 'exit_price': next_open,
                            'raw_pnl': round(raw_pnl, 2), 'pnl': round(net_pnl, 2),
                            'holding_days': p_holding_days
                        })  # 記錄結束
                    active_positions = []  # 清空持倉
                else:  # 保留並更新止損
                    if t_close > t_prev_high:  # 突破最高價
                        main_pos['stop_price'] = min(t_low, t_prev_low) - 1 * t_atr  # 更新主部位移動止損價
                    new_active.append(main_pos)  # 保留主部位

                    if has_pyr:  # 已有加多
                        p_pos = pyr_pos[0]  # 加倉部位
                        if t_close < p_pos['stop_price']:  # 跌破加倉部位止損
                            p_holding_days = (next_date.date() - p_pos['entry_date'].date()).days  # 持有天數
                            raw_pnl = next_open - p_pos['entry_price']  # 原始損益
                            net_pnl = raw_pnl - 0.3 - (p_holding_days * 0.75)  # 扣除成本
                            completed_trades.append({  # 記錄加多平倉
                                'type': 'Long', 'is_pyramid': True,
                                'entry_date': p_pos['entry_date'], 'exit_date': next_date,
                                'entry_price': p_pos['entry_price'], 'exit_price': next_open,
                                'raw_pnl': round(raw_pnl, 2), 'pnl': round(net_pnl, 2),
                                'holding_days': p_holding_days
                            })  # 記錄結束
                        else:  # 保留加多
                            if t_close > t_prev_high:  # 突破最高價
                                p_pos['stop_price'] = min(t_low, t_prev_low) - 1 * t_atr  # 更新加多止損
                            new_active.append(p_pos)  # 保留加多部位
                    else:  # 未加多
                        if dy_close > dy_ma50 and dy_pyramid_long:  # 滿足牛市及加多條件
                            new_active.append({  # 新增加多部位
                                'type': 'Long', 'is_pyramid': True,
                                'entry_date': next_date, 'entry_price': next_open,
                                'stop_price': min(t_low, t_prev_low) - 1 * t_atr  # 設定加多止損
                            })  # 加多部位建立結束
                    active_positions = new_active  # 更新持倉
            else:  # 空手
                if dy_close > dy_ma50 and is_long_sig:  # 滿足多頭建倉
                    active_positions.append({  # 建立主多單
                        'type': 'Long', 'is_pyramid': False,
                        'entry_date': next_date, 'entry_price': next_open,
                        'stop_price': min(t_low, t_prev_low) - 1 * t_atr  # 設定多單止損
                    })  # 建立結束

        else:  # 空單方向策略（Short Only）
            if has_pos:  # 持有空單
                main_pos = [p for p in active_positions if not p['is_pyramid']][0]  # 主部位
                pyr_pos = [p for p in active_positions if p['is_pyramid']]  # 加倉部位
                has_pyr = len(pyr_pos) > 0  # 是否有加倉部位

                # 出場條件（8H 止損或 8H 動能轉多）
                if t_close > main_pos['stop_price'] or is_long_sig:  # 止損或信號轉多
                    for p in active_positions:  # 平倉所有部位
                        p_holding_days = (next_date.date() - p['entry_date'].date()).days  # 計算持有跨日天數
                        raw_pnl = p['entry_price'] - next_open  # 原始平倉損益（用 i+1 open 出場）
                        net_pnl = raw_pnl - 0.3 + (p_holding_days * 0.27)  # 扣除點差並加計利息
                        completed_trades.append({  # 記錄交易
                            'type': 'Short', 'is_pyramid': p['is_pyramid'],
                            'entry_date': p['entry_date'], 'exit_date': next_date,
                            'entry_price': p['entry_price'], 'exit_price': next_open,
                            'raw_pnl': round(raw_pnl, 2), 'pnl': round(net_pnl, 2),
                            'holding_days': p_holding_days
                        })  # 記錄結束
                    active_positions = []  # 清空持倉
                else:  # 保留並更新止損
                    if t_close < t_prev_low:  # 跌破最低價
                        main_pos['stop_price'] = max(t_high, t_prev_high) + 1 * t_atr  # 更新主部位移動止損
                    new_active.append(main_pos)  # 保留主部位

                    if has_pyr:  # 已有加空
                        p_pos = pyr_pos[0]  # 加倉部位
                        if t_close > p_pos['stop_price']:  # 突破加倉部位止損
                            p_holding_days = (next_date.date() - p_pos['entry_date'].date()).days  # 持有天數
                            raw_pnl = p_pos['entry_price'] - next_open  # 原始損益
                            net_pnl = raw_pnl - 0.3 + (p_holding_days * 0.27)  # 扣除點差並加利息
                            completed_trades.append({  # 記錄加空平倉
                                'type': 'Short', 'is_pyramid': True,
                                'entry_date': p_pos['entry_date'], 'exit_date': next_date,
                                'entry_price': p_pos['entry_price'], 'exit_price': next_open,
                                'raw_pnl': round(raw_pnl, 2), 'pnl': round(net_pnl, 2),
                                'holding_days': p_holding_days
                            })  # 記錄結束
                        else:  # 保留加空
                            if t_close < t_prev_low:  # 跌破最低價
                                p_pos['stop_price'] = max(t_high, t_prev_high) + 1 * t_atr  # 更新加空止損
                            new_active.append(p_pos)  # 保留加空部位
                    else:  # 未加空
                        if dy_close < dy_ma50 and dy_pyramid_short:  # 滿足熊市及加空條件
                            new_active.append({  # 新增加空部位
                                'type': 'Short', 'is_pyramid': True,
                                'entry_date': next_date, 'entry_price': next_open,
                                'stop_price': max(t_high, t_prev_high) + 1 * t_atr  # 設定加空止損
                            })  # 加空部位建立結束
                    active_positions = new_active  # 更新持倉
            else:  # 空手
                if dy_close < dy_ma50 and not is_long_sig:  # 滿足空頭建倉
                    active_positions.append({  # 建立主空單
                        'type': 'Short', 'is_pyramid': False,
                        'entry_date': next_date, 'entry_price': next_open,
                        'stop_price': max(t_high, t_prev_high) + 1 * t_atr  # 設定空單止損
                    })  # 建立結束

    # 若回測結束時仍持有部位，強制以最後收盤價結算平倉
    if len(active_positions) > 0:  # 若有持倉
        last_close = df.loc[n-1, 'close']  # 最後收盤價
        last_date = pd.Timestamp(df.loc[n-1, 'timestamp'])  # 最後日期
        for p in active_positions:  # 遍歷持倉
            p_holding_days = (last_date.date() - p['entry_date'].date()).days  # 計算持有跨日天數
            raw_pnl = (last_close - p['entry_price']) if p['type'] == 'Long' else (p['entry_price'] - last_close)  # 點數盈虧
            if p['type'] == 'Long':  # 多單
                net_pnl = raw_pnl - 0.3 - (p_holding_days * 0.75)  # 扣除點差與過夜費
            else:  # 空單
                net_pnl = raw_pnl - 0.3 + (p_holding_days * 0.27)  # 扣除點差並加利息
            completed_trades.append({  # 記錄強制平倉
                'type': p['type'], 'is_pyramid': p['is_pyramid'],
                'entry_date': p['entry_date'], 'exit_date': last_date,
                'entry_price': p['entry_price'], 'exit_price': last_close,
                'raw_pnl': round(raw_pnl, 2), 'pnl': round(net_pnl, 2),
                'holding_days': p_holding_days
            })  # 記錄結束

    return completed_trades  # 直接回傳交易清單（移除 MTM，改用 per-trade PnL）


def compute_stats(trades, label):
    """從 per-trade 清單計算績效指標，並計算最大回撤點數（Max Drawdown Points）"""
    if not trades:  # 無交易
        return {}, pd.Series(dtype=float)  # 回傳空值

    df_t = pd.DataFrame(trades)  # 轉為 DataFrame
    df_t = df_t.sort_values('exit_date').reset_index(drop=True)  # 依出場日排序

    pnl_series = df_t['pnl']  # 逐筆損益序列
    cum_pnl = pnl_series.cumsum()  # 累積損益（點數）

    # 最大回撤點數（從波峰到波谷的最大點數回落）
    running_max = cum_pnl.cummax()  # 歷史累積最高點
    drawdown_pts = running_max - cum_pnl  # 每筆距波峰的回撤點數
    max_dd_pts = drawdown_pts.max()  # 最大回撤點數

    # 百分比 MDD（以波峰為基準）
    base = 2000.0  # 假設本金 2000 pts（可視需要調整）
    equity = base + cum_pnl  # 絕對淨值
    equity_peak = equity.cummax()  # 歷史峰值
    max_dd_pct = ((equity - equity_peak) / equity_peak).min()  # 百分比最大回撤

    # 時間軸用 exit_date 構建（每筆出場日期）
    n_trades = len(df_t)  # 總筆數
    wins = (pnl_series > 0).sum()  # 獲利筆數
    losses = (pnl_series <= 0).sum()  # 虧損筆數
    win_rate = wins / n_trades if n_trades > 0 else 0  # 勝率
    avg_win = pnl_series[pnl_series > 0].mean() if wins > 0 else 0  # 平均獲利
    avg_loss = pnl_series[pnl_series <= 0].mean() if losses > 0 else 0  # 平均虧損
    profit_factor = abs(pnl_series[pnl_series > 0].sum() / pnl_series[pnl_series <= 0].sum()) if losses > 0 else float('inf')  # 獲利因子

    # 年化指標（以回測天數推算）
    date_range_days = (pd.Timestamp(df_t['exit_date'].max()).date() - pd.Timestamp(df_t['exit_date'].min()).date()).days  # 回測天數
    years = date_range_days / 365.25  # 回測年數
    ann_pnl = cum_pnl.iloc[-1] / years if years > 0 else cum_pnl.iloc[-1]  # 年化損益點數
    calmar = ann_pnl / max_dd_pts if max_dd_pts > 0 else float('inf')  # 卡瑪比率（年化損益 / 最大回撤點數）

    # Sharpe Ratio（假設無風險利率 = 0，以逐筆損益的年化均值 / 年化標準差計算）
    # 以「每年平均交易筆數」作為年化因子
    trades_per_year = n_trades / years if years > 0 else n_trades  # 每年平均交易筆數
    ann_mean = pnl_series.mean() * trades_per_year  # 年化平均損益
    ann_std = pnl_series.std() * np.sqrt(trades_per_year)  # 年化標準差
    sharpe = ann_mean / ann_std if ann_std > 0 else 0.0  # 夏普比率

    stats = {  # 整理指標字典
        'label': label,  # 名稱
        'total_trades': n_trades,  # 總筆數
        'total_pnl_pts': round(cum_pnl.iloc[-1], 2),  # 累積損益點數
        'total_raw_pts': round(df_t['raw_pnl'].sum(), 2),  # 原始損益（未扣成本）
        'win_rate': f'{win_rate:.1%}',  # 勝率
        'avg_win': round(avg_win, 2),  # 平均獲利
        'avg_loss': round(avg_loss, 2),  # 平均虧損
        'profit_factor': round(profit_factor, 2),  # 獲利因子
        'max_dd_pts': round(max_dd_pts, 2),  # 最大回撤點數
        'max_dd_pct': f'{max_dd_pct:.2%}',  # 最大回撤百分比
        'sharpe': round(sharpe, 3),  # 夏普比率
        'calmar_pts': round(calmar, 3),  # 卡瑪比率（基於點數）
        'years': round(years, 2),  # 回測年數
        'ann_pnl_pts': round(ann_pnl, 2),  # 年化損益點數
    }  # 指標結束

    return stats, cum_pnl  # 回傳指標與累積損益序列


def main():  # 主程式進入點
    daily_gc = 'comex_gc1!_daily.csv'  # 黃金日線路徑
    dxy_daily = 'iceus_dxy_daily.csv'  # 美元指數路徑
    if not os.path.exists(daily_gc) or not os.path.exists(dxy_daily):  # 檢查檔案
        print("錯誤：找不到日線或美元指數資料！")  # 錯誤提示
        return  # 結束

    gold_df = pd.read_csv(daily_gc)  # 載入黃金
    dxy_df = pd.read_csv(dxy_daily)  # 載入美元

    gold_df = gold_df.rename(columns={'close': 'gold_close', 'open': 'gold_open', 'high': 'gold_high', 'low': 'gold_low'})  # 重新命名
    dxy_df = dxy_df.rename(columns={'close': 'dxy_close', 'open': 'dxy_open', 'high': 'dxy_high', 'low': 'dxy_low'})  # 重新命名

    gold_df = gold_df[['timestamp', 'gold_open', 'gold_high', 'gold_low', 'gold_close']]  # 篩選欄位
    dxy_df = dxy_df[['timestamp', 'dxy_open', 'dxy_high', 'dxy_low', 'dxy_close']]  # 篩選欄位

    # 日線資料合併與時間格式轉換
    df_daily = pd.merge(gold_df, dxy_df, on='timestamp', how='inner')  # 合併日線
    df_daily['timestamp'] = pd.to_datetime(df_daily['timestamp'])  # 轉 datetime
    df_daily = df_daily.sort_values('timestamp').reset_index(drop=True)  # 排序

    for n in [1, 5, 10]:  # 計算日線報酬率與 Alpha
        df_daily[f'gold_ret_{n}'] = df_daily['gold_close'].pct_change(n)  # 黃金報酬率
        df_daily[f'dxy_ret_{n}'] = df_daily['dxy_close'].pct_change(n)  # 美元指數報酬率
        df_daily[f'alpha_{n}'] = df_daily[f'gold_ret_{n}'] - df_daily[f'dxy_ret_{n}']  # Alpha 動能指標

    df_daily['ma20'] = df_daily['gold_close'].rolling(20).mean()  # 日線 20MA
    df_daily['ma60'] = df_daily['gold_close'].rolling(60).mean()  # 日線 60MA
    df_daily['ma50'] = df_daily['gold_close'].rolling(50).mean()  # 日線 50MA
    df_daily['date'] = df_daily['timestamp'].dt.date  # 提取日期

    # 建立 T-1 可用日線指標（避免未來偏誤）
    df_daily['daily_close_avail'] = df_daily['gold_close'].shift(1)  # 昨日收盤
    df_daily['daily_ma50_avail'] = df_daily['ma50'].shift(1)  # 昨日 50MA
    df_daily['daily_alpha1_avail'] = df_daily['alpha_1'].shift(1)  # 昨日 Alpha1
    df_daily['daily_alpha5_avail'] = df_daily['alpha_5'].shift(1)  # 昨日 Alpha5
    df_daily['daily_alpha10_avail'] = df_daily['alpha_10'].shift(1)  # 昨日 Alpha10
    df_daily['daily_ma20_avail'] = df_daily['ma20'].shift(1)  # 昨日 20MA
    df_daily['daily_ma60_avail'] = df_daily['ma60'].shift(1)  # 昨日 60MA

    # 執行 8H 30MA Long-Only 回測
    trades_long = run_strategy('comex_gc1!_8h.csv', 30, '8H', df_daily, is_long_only=True)  # 多單回測
    # 執行 8H 30MA Short-Only 回測
    trades_short = run_strategy('comex_gc1!_8h.csv', 30, '8H', df_daily, is_long_only=False)  # 空單回測

    # 合併所有交易，依出場日期排序
    all_trades = sorted(trades_long + trades_short, key=lambda x: str(x['exit_date']))  # 依出場時間排序

    # 計算各組績效
    stats_l, cum_l = compute_stats(trades_long, '8H 30MA Long-Only')  # 多單績效
    stats_s, cum_s = compute_stats(trades_short, '8H 30MA Short-Only')  # 空單績效
    stats_c, cum_c = compute_stats(all_trades, 'Combined Portfolio')  # 合併績效

    # ---- 控制台輸出 ----
    print("=== 混合組合策略 (8H Long-Only + 8H Short-Only) 績效結果 ===")  # 印出標題
    header = f"{'指標':<28} | {'8H 30MA Long-Only':>20} | {'8H 30MA Short-Only':>20} | {'Combined Portfolio':>20}"  # 表頭
    print(header)  # 印出表頭
    print("-" * len(header))  # 印出分割線

    rows = [  # 定義要印出的指標列
        ('累積損益 (點數)',      'total_pnl_pts'),  # 累積損益
        ('原始損益 (未扣成本)', 'total_raw_pts'),  # 原始損益
        ('最大回撤點數',        'max_dd_pts'),  # 最大回撤點數
        ('最大回撤百分比',      'max_dd_pct'),  # 最大回撤百分比
        ('夏普比率 (Sharpe)',   'sharpe'),  # 夏普比率
        ('卡瑪比率(損益/MDD)',  'calmar_pts'),  # 卡瑪比率
        ('勝率',               'win_rate'),  # 勝率
        ('平均獲利',           'avg_win'),  # 平均獲利
        ('平均虧損',           'avg_loss'),  # 平均虧損
        ('獲利因子',           'profit_factor'),  # 獲利因子
        ('年化損益點數',        'ann_pnl_pts'),  # 年化損益點數
        ('回測年數',           'years'),  # 回測年數
        ('總交易次數',         'total_trades'),  # 總交易次數
    ]  # 指標列結束

    for label, key in rows:  # 逐列印出
        vl = str(stats_l.get(key, 'N/A'))  # 多單值
        vs = str(stats_s.get(key, 'N/A'))  # 空單值
        vc = str(stats_c.get(key, 'N/A'))  # 合併值
        print(f"{label:<28} | {vl:>20} | {vs:>20} | {vc:>20}")  # 印出一列

    # ---- 繪製 per-trade 累積損益曲線 ----
    fig, ax = plt.subplots(figsize=(14, 7))  # 建立圖表

    # 以出場日期為 x 軸繪製累積損益
    df_l = pd.DataFrame(trades_long).sort_values('exit_date')  # 多單排序
    df_s = pd.DataFrame(trades_short).sort_values('exit_date')  # 空單排序
    df_a = pd.DataFrame(all_trades).sort_values('exit_date')  # 合併排序

    ax.plot(pd.to_datetime(df_a['exit_date']), df_a['pnl'].cumsum(), label='Combined Portfolio', color='#9c27b0', linewidth=2.0)  # 合併
    ax.plot(pd.to_datetime(df_l['exit_date']), df_l['pnl'].cumsum(), label='Long-Only', color='#2e7d32', linewidth=1.5, alpha=0.8)  # 多單
    ax.plot(pd.to_datetime(df_s['exit_date']), df_s['pnl'].cumsum(), label='Short-Only', color='#c62828', linewidth=1.5, alpha=0.8)  # 空單

    ax.set_title('Hybrid Gold Strategy — Per-Trade Cumulative PnL (Spread 0.3 + Overnight Cost)', fontsize=14, fontweight='bold')  # 標題
    ax.set_xlabel('Exit Date', fontsize=12)  # X軸
    ax.set_ylabel('Cumulative PnL (Points)', fontsize=12)  # Y軸
    ax.legend(loc='upper left')  # 圖例
    ax.grid(True, linestyle='--', alpha=0.5)  # 網格
    fig.tight_layout()  # 自動排版
    fig.savefig('backtest_combined_hybrid_comparison.png', dpi=300)  # 儲存圖片
    plt.close(fig)  # 關閉

    # ---- 輸出績效摘要 CSV ----
    summary_rows = []  # 績效摘要列表
    for label, key in rows:  # 逐指標
        summary_rows.append({  # 加入一列
            'Metric': label,  # 指標名稱
            '8H 30MA Long-Only': stats_l.get(key, ''),  # 多單
            '8H 30MA Short-Only': stats_s.get(key, ''),  # 空單
            'Combined Portfolio': stats_c.get(key, ''),  # 合併
        })  # 結束
    pd.DataFrame(summary_rows).to_csv('combined_hybrid_performance.csv', index=False)  # 儲存
    print("\n合併績效已儲存至 combined_hybrid_performance.csv")  # 成功提示

    # ---- 輸出逐筆交易明細 CSV（含最大回撤點數欄位）----
    df_detail = pd.DataFrame(all_trades)  # 建立交易明細 DataFrame
    df_detail = df_detail.sort_values('exit_date').reset_index(drop=True)  # 依出場日排序
    df_detail['trade_no'] = range(1, len(df_detail) + 1)  # 流水號
    df_detail['cum_pnl'] = df_detail['pnl'].cumsum()  # 累積損益點數
    df_detail['running_peak'] = df_detail['cum_pnl'].cummax()  # 歷史波峰
    df_detail['drawdown_from_peak_pts'] = df_detail['running_peak'] - df_detail['cum_pnl']  # 距波峰回撤點數（此即最大回撤點數的逐筆追蹤值）
    df_detail['max_drawdown_pts_so_far'] = df_detail['drawdown_from_peak_pts'].cummax()  # 截至本筆的歷史最大回撤點數

    detail_cols = [  # 選擇輸出欄位
        'trade_no', 'type', 'is_pyramid', 'entry_date', 'exit_date',
        'entry_price', 'exit_price', 'holding_days',
        'raw_pnl', 'pnl', 'cum_pnl',
        'drawdown_from_peak_pts', 'max_drawdown_pts_so_far'
    ]  # 欄位列表結束
    df_detail[detail_cols].to_csv('all_trades_detail.csv', index=False)  # 儲存逐筆明細
    print("逐筆交易明細已儲存至 all_trades_detail.csv（含最大回撤點數欄位）")  # 成功提示

    # ---- 最終核心數字快速確認 ----
    print(f"\n{'='*60}")  # 分割線
    print(f"✅ 正確回測結果（per-trade 加總，排除 MTM bug）")  # 標題
    print(f"  Long  : {stats_l['total_pnl_pts']:>10.2f} pts  ({stats_l['total_trades']} 筆)  MDD: {stats_l['max_dd_pts']} pts")  # 多單
    print(f"  Short : {stats_s['total_pnl_pts']:>10.2f} pts  ({stats_s['total_trades']} 筆)  MDD: {stats_s['max_dd_pts']} pts")  # 空單
    print(f"  Combined: {stats_c['total_pnl_pts']:>8.2f} pts  ({stats_c['total_trades']} 筆)  MDD: {stats_c['max_dd_pts']} pts")  # 合併
    print(f"{'='*60}")  # 分割線


if __name__ == '__main__':  # 判斷入口
    main()  # 執行
