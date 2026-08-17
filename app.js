let globalData = null; // 全域資料儲存變數
let filteredTrades = []; // 過濾後的交易紀錄列表
let currentPage = 1; // 當前表格分頁頁碼
const pageSize = 15; // 每頁顯示的交易紀錄筆數
let selectedTradeIds = new Set(); // 記錄已被勾選顯示在主圖表上的交易單號集合

document.addEventListener('DOMContentLoaded', () => { // 網頁 DOM 內容載入完畢後觸發
    fetchData(); // 呼叫獲取數據函數
    setupEventListeners(); // 設定介面事件監聽
}); // DOM 載入監聽結束

async function fetchData() { // 非同步讀取策略 JSON 數據函數
    try { // 嘗試執行讀取與解析
        const response = await fetch('strategy_results.json?v=' + new Date().getTime()); // 向伺服器請求 strategy_results.json (加上時間戳防止瀏覽器快取舊資料)
        if (!response.ok) throw new Error('無法讀取數據'); // 檢查 HTTP 回應狀態
        globalData = await response.json(); // 解析 JSON 物件並給全域變數
        
        renderStatusCards(globalData.current_status, globalData.metrics, globalData.gold_chart_data); // 繪製頂部狀態與指標卡片
        renderGoldChart(globalData.gold_chart_data, []); // 繪製黃金 8H 主圖表 (預設傳入空陣列，不滿頁顯示所有交易標記)
        renderEquityChart(globalData.completed_trades, globalData.gold_chart_data); // 繪製策略累積權益曲線 (Equity Curve)
        renderDXYChart(globalData.dxy_chart_data); // 繪製美元指數圖表
        
        filteredTrades = [...globalData.completed_trades].sort((a, b) => b.trade_id - a.trade_id); // 複製完整歷史交易並依最新交易 (trade_id 倒序) 開始排序
        renderTradesTable(); // 渲染歷史交易紀錄表格
        updateSelectionUI(); // 更新全選狀態與已勾選計數
        
    } catch (err) { // 捕捉載入過程之例外
        console.error('資料載入失敗:', err); // 於 Console 輸出錯誤訊息
        document.getElementById('last-updated-text').textContent = '資料載入失敗，請確認 JSON 檔！'; // 於頁面顯示錯誤提示
    } // 嘗試捕捉結束
} // fetchData 結束

function renderStatusCards(status, metrics, goldChartData) { // 渲染狀態卡片數據函數
    const startStr = goldChartData.timestamps[0].substring(0, 10); // 取得回測起始年月日
    const endStr = status.last_updated.substring(0, 10); // 取得回測結束年月日
    document.getElementById('last-updated-text').textContent = `回測區間：${startStr} ~ ${endStr} (約 2.1 年)`; // 於頂部標籤顯示完整時間區間
    
    const regimeEl = document.getElementById('regime-val'); // 取得 Regime 卡片 DOM
    regimeEl.textContent = status.regime; // 填入 Regime 狀態文字
    regimeEl.className = 'card-main-val ' + (status.regime.includes('Bull') ? 'positive-val' : 'negative-val'); // 套用多空配色樣式
    
    document.getElementById('gold-price-val').textContent = `$${status.gold_close.toFixed(2)}`; // 顯示黃金最新價
    document.getElementById('dxy-price-val').textContent = status.dxy_close.toFixed(3); // 顯示 DXY 最新價
    
    const alphaStatusEl = document.getElementById('alpha-status-val'); // 取得 Alpha 狀態元素
    const isAlphaBull = status.alpha_1d > 0 && status.alpha_5d > 0 && status.alpha_10d > 0; // 多頭 Alpha 判定
    const isAlphaBear = status.alpha_1d < 0 && status.alpha_5d < 0 && status.alpha_10d < 0; // 空頭 Alpha 判定
    
    if (isAlphaBull) { // 多頭 Alpha 強勢
        alphaStatusEl.textContent = 'Alpha 多頭強勢 (Gold > DXY)'; // 文字設定 (澄清非當前部位)
        alphaStatusEl.className = 'card-main-val positive-val'; // 綠色樣式
    } else if (isAlphaBear) { // 空頭 Alpha 強勢
        alphaStatusEl.textContent = 'Alpha 空頭強勢 (Gold < DXY)'; // 文字設定 (澄清非當前部位)
        alphaStatusEl.className = 'card-main-val negative-val'; // 紅色樣式
    } else { // 動能中性
        alphaStatusEl.textContent = '動能分化中 (No Momentum)'; // 文字設定
        alphaStatusEl.className = 'card-main-val'; // 灰色樣式
    } // Alpha 判定結束
    
    document.getElementById('alpha1-val').textContent = `${(status.alpha_1d * 100).toFixed(2)}%`; // 顯示 1D Alpha
    document.getElementById('alpha5-val').textContent = `${(status.alpha_5d * 100).toFixed(2)}%`; // 顯示 5D Alpha
    document.getElementById('alpha10-val').textContent = `${(status.alpha_10d * 100).toFixed(2)}%`; // 顯示 10D Alpha
    
    const activeValEl = document.getElementById('active-pos-val'); // 取得活躍部位數量 DOM
    const activeDetailEl = document.getElementById('active-pos-detail'); // 取得部位細節容器 DOM
    
    if (status.active_positions.length === 0) { // 無活躍部位
        activeValEl.textContent = '0 筆 (空手等待)'; // 設定數量文字
        activeDetailEl.innerHTML = '<span>當前無活躍部位，系統持續監控中</span>'; // 設定細節文字
    } else { // 持有活躍部位
        activeValEl.textContent = `${status.active_positions.length} 筆活躍部位`; // 顯示筆數
        activeDetailEl.innerHTML = status.active_positions.map(p => `
            <div style="margin-top: 4px; padding: 4px 0; border-top: 1px dashed rgba(255,255,255,0.1);">
                <span class="${p.type === 'Long' ? 'badge-long' : 'badge-short'}">${p.type} ${p.is_pyramid ? '[加碼]' : '[主單]'}</span>
                <span>進場: <strong>${p.entry_price}</strong> | 停損: <strong style="color:#ffa726;">${p.stop_price}</strong></span>
                <span>未實現盈虧: <strong class="${p.unrealized_pnl >= 0 ? 'positive-val' : 'negative-val'}">${p.unrealized_pnl > 0 ? '+' : ''}${p.unrealized_pnl} pts</strong></span>
            </div>
        `).join(''); // 生成持倉清單 HTML
    } // 部位判斷結束
    
    // 計算即時未實現損益點數總和
    const unrealizedSum = (status.active_positions && status.active_positions.length > 0) 
        ? status.active_positions.reduce((acc, p) => acc + (p.unrealized_pnl || 0), 0) : 0; // 加總當前持倉未實現損益
    const closedPnl = metrics.total_pnl_points || 0; // 已平倉累積點數
    const realtimeTotalPnl = metrics.realtime_total_pnl_points !== undefined ? metrics.realtime_total_pnl_points : (closedPnl + unrealizedSum); // 即時總權益累積點數
    
    const totalPnlEl = document.getElementById('total-pnl-val'); // 取得總盈虧 DOM
    totalPnlEl.textContent = `${realtimeTotalPnl >= 0 ? '+' : ''}${realtimeTotalPnl.toFixed(2)} pts`; // 顯示即時總權益點數
    totalPnlEl.className = 'card-main-val ' + (realtimeTotalPnl >= 0 ? 'positive-val' : 'negative-val'); // 套用配色
    
    const closedEl = document.getElementById('closed-pnl-val'); // 取得已平倉點數 DOM
    if (closedEl) closedEl.textContent = `${closedPnl >= 0 ? '+' : ''}${closedPnl.toFixed(2)} pts`; // 顯示已平倉點數
    
    const unrealizedEl = document.getElementById('unrealized-pnl-val'); // 取得未實現點數 DOM
    if (unrealizedEl) unrealizedEl.textContent = `${unrealizedSum >= 0 ? '+' : ''}${unrealizedSum.toFixed(2)} pts`; // 顯示未實現點數
    
    document.getElementById('total-trades-val').textContent = metrics.total_trades; // 顯示總筆數
    document.getElementById('win-rate-val').textContent = `${metrics.win_rate}%`; // 顯示勝率
    document.getElementById('mdd-val').textContent = `${metrics.max_drawdown} pts`; // 顯示最大回撤
    
    const currDD = metrics.current_drawdown !== undefined ? metrics.current_drawdown : 0; // 取得當前即時回撤點數
    const currDDPct = metrics.current_drawdown_pct !== undefined ? metrics.current_drawdown_pct : 0; // 取得當前即時回撤百分比
    document.getElementById('current-dd-val').textContent = `${currDD} pts (${currDDPct}%)`; // 顯示目前即時回撤與百分比
} // renderStatusCards 結束

function renderGoldChart(chartData, annotations) { // 繪製 XAUUSD 4H Plotly 主圖表 (開放雙軸拉伸與重置)
    const candlestickTrace = { // K 線軌跡設定
        x: chartData.timestamps, // 時間
        open: chartData.open, high: chartData.high, low: chartData.low, close: chartData.close, // 四價
        type: 'candlestick', name: 'XAUUSD 4H K線', // 類型與名稱
        increasing: { line: { color: '#00e676', width: 1 }, fillcolor: '#00e676' }, // 上漲 K 線亮綠色
        decreasing: { line: { color: '#ff1744', width: 1 }, fillcolor: '#ff1744' } // 下跌 K 線亮紅色
    }; // K 線軌跡結束

    const ma30Trace = { // 4H 30MA 軌跡
        x: chartData.timestamps, y: chartData.ma30_8h, mode: 'lines', // 折線模式
        name: '4H 30MA', line: { color: '#29b6f6', width: 1.5 } // 藍色線條
    }; // 30MA 結束

    const dailyMa50Trace = { // Daily 50MA 軌跡
        x: chartData.timestamps, y: chartData.daily_ma50, mode: 'lines', // 折線模式
        name: 'Daily 50MA (Regime)', line: { color: '#ab47bc', width: 2 } // 紫色線條
    }; // 50MA 結束

    const dailyMa20Trace = { // Daily 20MA 軌跡
        x: chartData.timestamps, y: chartData.daily_ma20, mode: 'lines', // 折線模式
        name: 'Daily 20MA', line: { color: '#ffa726', width: 1.5, dash: 'dot' } // 橘色虛線
    }; // 20MA 結束

    const dailyMa60Trace = { // Daily 60MA 軌跡
        x: chartData.timestamps, y: chartData.daily_ma60, mode: 'lines', // 折線模式
        name: 'Daily 60MA', line: { color: '#ec407a', width: 1.5, dash: 'dot' } // 粉紅虛線
    }; // 60MA 結束

    const layout = { // 定義圖表樣式版面 (支援 Y 軸自由拖曳與對焦)
        paper_bgcolor: '#131722', plot_bgcolor: '#131722', margin: { l: 50, r: 60, t: 30, b: 40 }, // 背景色與邊距
        xaxis: { type: 'date', rangeslider: { visible: false }, gridcolor: 'rgba(255,255,255,0.05)', tickfont: { color: '#787b86', family: 'JetBrains Mono' }, fixedrange: false }, // X 軸解鎖自由縮放
        yaxis: { gridcolor: 'rgba(255,255,255,0.05)', side: 'right', tickfont: { color: '#787b86', family: 'JetBrains Mono' }, fixedrange: false, autorange: true }, // Y 軸解鎖自由拖曳與拉伸
        showlegend: false, annotations: annotations || [], shapes: [], dragmode: 'pan' // 預設隱藏圖例與依據勾選動態渲染標記
    }; // 版面定義結束

    const config = { // 圖表互動模式列設定
        responsive: true, // 自動彈性響應尺寸
        scrollZoom: true, // 允許鼠標輪滾進行 X/Y 軸同時縮放
        displayModeBar: true, // 顯示 Plotly 控制工具列
        modeBarButtonsToRemove: [] // 保留所有縮放與拉伸按鈕
    }; // 設定結束

    Plotly.newPlot('gold-chart', [candlestickTrace, ma30Trace, dailyMa50Trace, dailyMa20Trace, dailyMa60Trace], layout, config); // 渲染 Plotly 主圖表
} // renderGoldChart 結束

function updateChartTradeAnnotations() { // 動態更新 XAUUSD 主圖表上勾選交易標記與進出場虛線之函數
    const goldChartEl = document.getElementById('gold-chart'); // 取得黃金圖表 DOM
    if (!goldChartEl || !globalData) return; // 檢查 DOM 與資料是否存在
    
    const selectedAnnotations = []; // 儲存勾選交易之 Plotly 標記
    const selectedShapes = []; // 儲存進出場連接線段 Shape

    const tradesMap = new Map(globalData.completed_trades.map(t => [t.trade_id, t])); // 建立 trade_id 快速查詢 Map
    
    selectedTradeIds.forEach(id => { // 遍歷所有已勾選之 trade_id
        const t = tradesMap.get(id); // 取得交易資料
        if (!t) return; // 若無資料則跳過
        
        const isLong = (t.type === 'Long'); // 判斷是否為多單
        const isWin = (t.pnl_points >= 0); // 判斷是否獲利
        const mainColor = isLong ? '#00e676' : '#ff1744'; // 進場色彩 (多綠空紅)
        const exitColor = isWin ? '#ffb74d' : '#ef5350'; // 出場色彩 (獲利橘黃虧損紅色)
        
        // 1. 進場點標記
        selectedAnnotations.push({
            x: t.entry_date, y: t.entry_price, // 進場時間與價格
            text: `${isLong ? '🟢 進場 Buy' : '🔴 進場 Sell'} #${t.trade_id}`, // 標籤文字
            showarrow: true, arrowhead: 2, arrowsize: 1, arrowwidth: 2, arrowcolor: mainColor, // 箭頭樣式
            ax: 0, ay: isLong ? 35 : -35, // 箭頭垂直偏移方向
            font: { color: '#ffffff', size: 11, family: 'JetBrains Mono' }, // 字型設定
            bgcolor: mainColor + 'cc', bordercolor: mainColor, borderpad: 4, borderwidth: 1 // 標籤外框
        });
        
        // 2. 出場點標記
        selectedAnnotations.push({
            x: t.exit_date, y: t.exit_price, // 出場時間與價格
            text: `平倉 #${t.trade_id} (${isWin ? '+' : ''}${t.pnl_points.toFixed(2)} pts)`, // 標籤文字與損益
            showarrow: true, arrowhead: 2, arrowsize: 1, arrowwidth: 2, arrowcolor: exitColor, // 箭頭樣式
            ax: 0, ay: isLong ? -35 : 35, // 箭頭垂直偏移方向
            font: { color: '#ffffff', size: 10, family: 'JetBrains Mono' }, // 字型設定
            bgcolor: exitColor + 'cc', bordercolor: exitColor, borderpad: 3, borderwidth: 1 // 標籤外框
        });

        // 3. 進出場連線 (虛線)
        selectedShapes.push({
            type: 'line', // 形狀種類為直線
            x0: t.entry_date, y0: t.entry_price, // 起點為進場時價
            x1: t.exit_date, y1: t.exit_price, // 終點為出場時價
            line: { color: isWin ? '#00e676' : '#ff1744', width: 2, dash: 'dot' } // 損益色彩對應虛線
        });
    });

    Plotly.relayout(goldChartEl, { // 重設圖表標記與連線
        annotations: selectedAnnotations, // 傳入動態生成標記陣列
        shapes: selectedShapes // 傳入動態生成進出場連線陣列
    }); // relayout 結束
} // updateChartTradeAnnotations 結束

function updateSelectionUI() { // 更新 UI 勾選計數與 Header 勾選框狀態之函數
    const countBadge = document.getElementById('selected-count-badge'); // 取得計數標籤 DOM
    if (countBadge) { // 若標籤存在
        countBadge.textContent = `已勾選：${selectedTradeIds.size} 筆`; // 更新顯示數量
    }
    
    const checkAllHeader = document.getElementById('check-all-header'); // 取得當頁全選 Checkbox DOM
    if (checkAllHeader && filteredTrades.length > 0) { // 若 Header Checkbox 存在
        const startIdx = (currentPage - 1) * pageSize; // 當頁起始索引
        const endIdx = Math.min(startIdx + pageSize, filteredTrades.length); // 當頁結束索引
        const pageItems = filteredTrades.slice(startIdx, endIdx); // 當頁資料
        
        const allPageChecked = pageItems.length > 0 && pageItems.every(t => selectedTradeIds.has(t.trade_id)); // 檢查當頁是否全選
        checkAllHeader.checked = allPageChecked; // 設定 Header Checkbox 狀態
    }
} // updateSelectionUI 結束

function renderEquityChart(completedTrades, goldChartData) { // 繪製策略累積權益曲線 (Equity Curve) 函數
    const equityChartEl = document.getElementById('equity-chart'); // 取得 Equity Chart DOM
    if (!equityChartEl || !completedTrades || completedTrades.length === 0) return; // 檢查 DOM 與資料是否存在
    
    // 依據平倉時間 exit_date 升冪排序 (舊到新)，確保 X 軸時間折線永不倒退
    const sortedTrades = [...completedTrades].sort((a, b) => new Date(a.exit_date) - new Date(b.exit_date));
    
    const timestamps = [goldChartData.timestamps[0]]; // 起始時間點
    const equityValues = [0]; // 起始權益為 0
    const hoverTexts = ['起始點: 0.00 pts']; // 起始點 Hover 文字
    
    let currentCumPnl = 0; // 累積損益計數器
    let maxCumPnl = 0; // 最高累積損益
    
    sortedTrades.forEach((t, idx) => { // 遍歷計算每一筆結算交易
        const pnl = (typeof t.pnl_points === 'number') ? t.pnl_points : parseFloat(t.pnl_points || 0); // 確保點數為數值
        currentCumPnl += pnl; // 累加點數損益
        if (currentCumPnl > maxCumPnl) maxCumPnl = currentCumPnl; // 更新歷史最高 PnL
        
        timestamps.push(t.exit_date); // 記錄平倉時間戳
        equityValues.push(parseFloat(currentCumPnl.toFixed(2))); // 記錄目前累積 PnL
        
        const isWin = (pnl >= 0); // 判斷個單是否獲利
        const pnlStr = (isWin ? '+' : '') + pnl.toFixed(2) + ' pts'; // 格式化當筆損益
        const cumStr = (currentCumPnl >= 0 ? '+' : '') + currentCumPnl.toFixed(2) + ' pts'; // 格式化累積權益
        const colorHex = isWin ? '#00e676' : '#ff1744'; // 獲利亮綠，虧損亮紅
        
        // 修正 Tooltip: 使用 Plotly 標準相容之 font 標籤，確保「當筆損益」清晰顯示
        hoverTexts.push(
            `<b>交易 #${t.trade_id || (idx + 1)} (${t.type})</b><br>` +
            `出場時間: ${t.exit_date}<br>` +
            `當筆損益: <font color="${colorHex}"><b>${pnlStr}</b></font><br>` +
            `<b>累積權益: ${cumStr}</b>`
        ); // 設定 Hover 文字
    });
    
    // 更新頂部標籤顯示最高與最新損益
    const maxPnlEl = document.getElementById('equity-max-pnl'); // 歷史最高標籤
    const currentPnlEl = document.getElementById('equity-current-pnl'); // 當前累積標籤
    if (maxPnlEl) maxPnlEl.textContent = `歷史最高 PnL: +${maxCumPnl.toFixed(2)} pts`;
    if (currentPnlEl) currentPnlEl.textContent = `當前累積 PnL: ${currentCumPnl >= 0 ? '+' : ''}${currentCumPnl.toFixed(2)} pts`;
    
    const traceEquity = { // 權益曲線 Trace 物件
        x: timestamps, // X 軸時間戳
        y: equityValues, // Y 軸累積 PnL
        mode: 'lines', // 線條模式
        name: '累積損益 (Pts)', // 名稱
        text: hoverTexts, // 自訂 Hover 文字
        hoverinfo: 'text', // 僅顯示自訂文字
        line: { color: '#00e676', width: 2 }, // 亮綠色線條
        fill: 'tozeroy', // 填充至 0 軸
        fillcolor: 'rgba(0, 230, 118, 0.08)' // 綠色半透明漸層
    };

    const layout = { // Equity Chart Layout 設定
        paper_bgcolor: '#131722', plot_bgcolor: '#131722', margin: { l: 50, r: 60, t: 20, b: 30 }, // 背景與內距
        xaxis: { type: 'date', gridcolor: 'rgba(255,255,255,0.05)', tickfont: { color: '#787b86', family: 'JetBrains Mono' }, fixedrange: false }, // X 軸解鎖自由拖曳
        yaxis: { gridcolor: 'rgba(255,255,255,0.05)', side: 'right', tickfont: { color: '#787b86', family: 'JetBrains Mono' }, fixedrange: false, autorange: true, zerolinecolor: 'rgba(255,255,255,0.2)' }, // Y 軸顯示 0 軸線
        showlegend: false, dragmode: 'pan' // 隱藏圖例與預設平移
    };

    Plotly.newPlot('equity-chart', [traceEquity], layout, { responsive: true, scrollZoom: true, displayModeBar: true }); // 繪製 Plotly Equity 圖表
} // renderEquityChart 結束

function renderDXYChart(dxyData) { // 繪製 DXY 美元指數圖表 (解鎖 Y 軸縮放)
    const dxyLineTrace = { x: dxyData.timestamps, y: dxyData.close, mode: 'lines', name: 'DXY 收盤價', line: { color: '#29b6f6', width: 2 } }; // 美元指數收盤價
    const dxyMa20Trace = { x: dxyData.timestamps, y: dxyData.ma20, mode: 'lines', name: 'DXY 20MA', line: { color: '#26a69a', width: 1.5 } }; // DXY 20MA
    const dxyMa60Trace = { x: dxyData.timestamps, y: dxyData.ma60, mode: 'lines', name: 'DXY 60MA', line: { color: '#ef5350', width: 1.5 } }; // DXY 60MA

    const layout = { // DXY 圖表版面
        paper_bgcolor: '#131722', plot_bgcolor: '#131722', margin: { l: 50, r: 60, t: 20, b: 30 }, // 背景與外距
        xaxis: { type: 'date', gridcolor: 'rgba(255,255,255,0.05)', tickfont: { color: '#787b86' }, fixedrange: false }, // X 軸可動
        yaxis: { gridcolor: 'rgba(255,255,255,0.05)', side: 'right', tickfont: { color: '#787b86' }, fixedrange: false, autorange: true }, // Y 軸可動可拉伸
        showlegend: false, dragmode: 'pan' // 隱藏圖例與平移模式
    }; // 版面結束

    Plotly.newPlot('dxy-chart', [dxyLineTrace, dxyMa20Trace, dxyMa60Trace], layout, { responsive: true, scrollZoom: true, displayModeBar: true }); // 渲染 DXY 圖表
} // renderDXYChart 結束

function formatMT5Time(dateStr) { // 將 UTC 時間轉為 MT5 伺服器時間 (GMT+3 夏令 / GMT+2 冬令) 顯示
    if (!dateStr) return '-'; // 空值回傳槓麻
    try {
        const d = new Date(dateStr.replace(/-/g, '/')); // 解析日期字串
        const month = d.getMonth() + 1; // 取得月份
        const isDST = (month >= 3 && month <= 10); // 簡化判定夏令時間 (3~10月 GMT+3)
        const offsetHours = isDST ? 3 : 2; // 時區偏移小時
        d.setHours(d.getHours() + offsetHours); // 加上時區偏移
        
        const m = String(d.getMonth() + 1).padStart(2, '0'); // 月
        const day = String(d.getDate()).padStart(2, '0'); // 日
        const hh = String(d.getHours()).padStart(2, '0'); // 時
        const mm = String(d.getMinutes()).padStart(2, '0'); // 分
        return `${m}/${day} ${hh}:${mm} <span style="font-size:0.75rem; color:#787b86;">(MT5)</span>`; // 回傳格式化字串
    } catch(e) {
        return dateStr;
    }
} // formatMT5Time 結束

function renderTradesTable() { // 渲染歷史交易紀錄數據表格函數
    const tbody = document.getElementById('trades-tbody'); // 取得表格 Body
    tbody.innerHTML = ''; // 清空內容
    
    const startIdx = (currentPage - 1) * pageSize; // 當頁起始索引
    const endIdx = Math.min(startIdx + pageSize, filteredTrades.length); // 當頁結束索引
    const pageItems = filteredTrades.slice(startIdx, endIdx); // 切割當頁交易紀錄
    
    if (pageItems.length === 0) { // 若無匹配項目
        tbody.innerHTML = '<tr><td colspan="12" style="text-align:center; padding: 24px; color: #787b86;">查無符合條件的交易紀錄</td></tr>'; // 顯示提示列
    } else { // 存在符合項目
        pageItems.forEach(t => { // 遍歷當頁紀錄
            const tr = document.createElement('tr'); // 建立列 DOM 元素
            const isProfit = t.pnl_points >= 0; // 判斷盈虧狀態
            const isChecked = selectedTradeIds.has(t.trade_id); // 檢查該筆交易是否已勾選
            
            if (isChecked) tr.classList.add('active-row'); // 若已勾選則套用高亮背景
            
            const entryMT5 = formatMT5Time(t.entry_date); // 轉為 MT5 時間
            const exitMT5 = formatMT5Time(t.exit_date); // 轉為 MT5 時間
            
            tr.innerHTML = `
                <td style="text-align: center;" onclick="event.stopPropagation();">
                    <input type="checkbox" class="trade-checkbox" data-id="${t.trade_id}" ${isChecked ? 'checked' : ''}>
                </td>
                <td>#${t.trade_id}</td>
                <td><span class="${t.type === 'Long' ? 'badge-long' : 'badge-short'}">${t.type}</span></td>
                <td><span class="${t.is_pyramid ? 'badge-pyr' : 'badge-main'}">${t.is_pyramid ? '加碼部位' : '主部位'}</span></td>
                <td>${entryMT5}<br><small style="color:#787b86;">${t.entry_date}</small></td>
                <td>$${t.entry_price.toFixed(2)}</td>
                <td>${exitMT5}<br><small style="color:#787b86;">${t.exit_date}</small></td>
                <td>$${t.exit_price.toFixed(2)}</td>
                <td>$${t.stop_price ? t.stop_price.toFixed(2) : '-'}</td>
                <td class="${isProfit ? 'positive-val' : 'negative-val'}">${isProfit ? '+' : ''}${t.pnl_points.toFixed(2)}</td>
                <td>${t.holding_hours} 小時</td>
                <td>${t.exit_reason}</td>
            `; // 充填 HTML 字串
            
            const checkbox = tr.querySelector('.trade-checkbox'); // 取得當列 Checkbox
            checkbox.addEventListener('change', (e) => { // 監聽勾選狀態變更
                if (e.target.checked) { // 勾選
                    selectedTradeIds.add(t.trade_id); // 加入集合
                    tr.classList.add('active-row'); // 加入高亮樣式
                    focusChartOnTrade(t); // 自動對焦該筆交易
                } else { // 取消勾選
                    selectedTradeIds.delete(t.trade_id); // 自集合刪除
                    tr.classList.remove('active-row'); // 移除高亮樣式
                }
                updateSelectionUI(); // 更新全選鈕與數量標籤
                updateChartTradeAnnotations(); // 更新圖表上的標記
            });
            
            tr.addEventListener('click', (e) => { // 註冊資料列點擊事件
                if (e.target.tagName.toLowerCase() === 'input') return; // 若點擊的是 Checkbox 本身則跳過
                
                if (selectedTradeIds.has(t.trade_id)) { // 若已勾選則取消
                    selectedTradeIds.delete(t.trade_id); // 移除
                    checkbox.checked = false; // 取消 Checkbox
                    tr.classList.remove('active-row'); // 清除高亮
                } else { // 若未勾選則勾選
                    selectedTradeIds.add(t.trade_id); // 新增
                    checkbox.checked = true; // 勾選 Checkbox
                    tr.classList.add('active-row'); // 高亮
                }
                updateSelectionUI(); // 更新 UI 狀態
                updateChartTradeAnnotations(); // 更新圖表標記
                focusChartOnTrade(t); // 觸發圖表焦距對焦
            }); // 點擊事件結束
            
            tbody.appendChild(tr); // 掛載資料列至 tbody
        }); // 遍歷結束
    } // 判斷結束
    
    document.getElementById('page-info').textContent = `顯示 ${filteredTrades.length === 0 ? 0 : startIdx + 1} 到 ${endIdx} 筆，共 ${filteredTrades.length} 筆交易`; // 分頁文字
    document.getElementById('btn-prev-page').disabled = (currentPage === 1); // 禁用上一頁
    document.getElementById('btn-next-page').disabled = (endIdx >= filteredTrades.length); // 禁用下一頁
    updateSelectionUI(); // 同步更新 Header Checkbox 與 count badge
} // renderTradesTable 結束

function focusChartOnTrade(trade) { // 點擊交易列對焦圖表範圍函數
    const goldChartEl = document.getElementById('gold-chart'); // 取得黃金圖表 DOM
    const dxyChartEl = document.getElementById('dxy-chart'); // 取得 DXY 圖表 DOM
    if (!goldChartEl) return; // 檢查 DOM 是否存在
    
    const entryTime = new Date(trade.entry_date).getTime(); // 進場時間戳
    const exitTime = new Date(trade.exit_date).getTime(); // 出場時間戳
    const timeSpan = Math.max(exitTime - entryTime, 48 * 3600 * 1000); // 最少顯示 48 小時範圍
    
    const startTimeStr = new Date(entryTime - timeSpan * 0.8).toISOString().replace('T', ' ').substring(0, 19); // 左側時間起點
    const endTimeStr = new Date(exitTime + timeSpan * 0.8).toISOString().replace('T', ' ').substring(0, 19); // 右側時間終點
    
    const goldData = globalData.gold_chart_data; // 黃金圖表數據
    let minPrice = Infinity; // 最低價
    let maxPrice = -Infinity; // 最高價
    
    const tStart = entryTime - timeSpan * 0.8; // 時間視窗起點
    const tEnd = exitTime + timeSpan * 0.8; // 時間視窗終點
    
    for (let i = 0; i < goldData.timestamps.length; i++) { // 遍歷黃金資料點
        const t = new Date(goldData.timestamps[i]).getTime(); // 轉毫秒數
        if (t >= tStart && t <= tEnd) { // 若落於時間視窗內
            minPrice = Math.min(minPrice, goldData.low[i]); // 更新視窗內最低價
            maxPrice = Math.max(maxPrice, goldData.high[i]); // 更新視窗內最高價
        } // 條件結束
    } // 遍歷結束
    
    if (minPrice !== Infinity && maxPrice !== -Infinity && maxPrice > minPrice) { // 有有效價格範圍
        const margin = (maxPrice - minPrice) * 0.15; // 計算 15% 上下裕度
        Plotly.relayout(goldChartEl, { // 重設黃金圖表範圍
            'xaxis.range': [startTimeStr, endTimeStr], // X 軸時間範圍
            'yaxis.range': [minPrice - margin, maxPrice + margin] // Y 軸價格範圍
        }); // relayout 結束
    } else { // 價格計算備用
        Plotly.relayout(goldChartEl, { 'xaxis.range': [startTimeStr, endTimeStr] }); // 僅設 X 軸
    } // 判斷結束

    const equityChartEl = document.getElementById('equity-chart'); // 取得 Equity 圖表 DOM
    if (equityChartEl) { // 若 Equity 圖表 DOM 存在
        Plotly.relayout(equityChartEl, { // 重設 Equity 圖表時間範圍
            'xaxis.range': [startTimeStr, endTimeStr], // 時間範圍與主圖同步
            'yaxis.autorange': true // 自動適應刻度
        }); // relayout 結束
    }

    if (dxyChartEl) { // 若 DXY 圖表 DOM 存在
        Plotly.relayout(dxyChartEl, { // 重設 DXY 圖表時間範圍
            'xaxis.range': [startTimeStr.substring(0, 10), endTimeStr.substring(0, 10)], // DXY 使用 YYYY-MM-DD
            'yaxis.autorange': true // 自動適應當前視窗 Y 軸刻度
        }); // relayout 結束
    } // DXY 判斷結束
} // focusChartOnTrade 結束

function setupEventListeners() { // 註冊事件函數
    const searchInput = document.getElementById('table-search'); // 搜尋框
    const typeFilter = document.getElementById('type-filter'); // 選單
    const prevBtn = document.getElementById('btn-prev-page'); // 上一頁
    const nextBtn = document.getElementById('btn-next-page'); // 下一頁
    const resetGoldBtn = document.getElementById('btn-reset-gold-chart'); // 取得重置黃金圖表按鈕 DOM
    const resetEquityBtn = document.getElementById('btn-reset-equity-chart'); // 取得重置 Equity 圖表按鈕 DOM
    const resetDxyBtn = document.getElementById('btn-reset-dxy-chart'); // 取得重置 DXY 圖表按鈕 DOM
    
    const selectFilteredBtn = document.getElementById('btn-select-filtered'); // 全選篩選項目按鈕
    const clearAllBtn = document.getElementById('btn-clear-all'); // 清除全選按鈕
    const checkAllHeader = document.getElementById('check-all-header'); // 表頭當頁全選 Checkbox

    if (selectFilteredBtn) { // 註冊全選篩選項目點擊事件
        selectFilteredBtn.addEventListener('click', () => { // 點擊事件
            filteredTrades.forEach(t => selectedTradeIds.add(t.trade_id)); // 將目前篩選之所有筆數加入集合
            renderTradesTable(); // 重新渲染表格
            updateSelectionUI(); // 更新介面狀態
            updateChartTradeAnnotations(); // 更新圖表標記
        });
    }

    if (clearAllBtn) { // 註冊全清除點擊事件
        clearAllBtn.addEventListener('click', () => { // 點擊事件
            selectedTradeIds.clear(); // 清空勾選集合
            renderTradesTable(); // 重新渲染表格
            updateSelectionUI(); // 更新介面狀態
            updateChartTradeAnnotations(); // 更新圖表標記
        });
    }

    if (checkAllHeader) { // 註冊當頁全選/全取消監聽
        checkAllHeader.addEventListener('change', (e) => { // 狀態變更事件
            const startIdx = (currentPage - 1) * pageSize; // 當頁起始
            const endIdx = Math.min(startIdx + pageSize, filteredTrades.length); // 當頁結束
            const pageItems = filteredTrades.slice(startIdx, endIdx); // 當頁筆數
            
            if (e.target.checked) { // 若勾選當頁
                pageItems.forEach(t => selectedTradeIds.add(t.trade_id)); // 批量加入
            } else { // 若取消勾選當頁
                pageItems.forEach(t => selectedTradeIds.delete(t.trade_id)); // 批量移除
            }
            renderTradesTable(); // 重新渲染表格
            updateSelectionUI(); // 更新介面狀態
            updateChartTradeAnnotations(); // 更新圖表標記
        });
    }

    if (resetGoldBtn) { // 註冊重置黃金圖表按鈕
        resetGoldBtn.addEventListener('click', () => { // 點擊觸發重置
            const goldChartEl = document.getElementById('gold-chart'); // 取得黃金圖表
            if (goldChartEl) { // 存在 DOM
                Plotly.relayout(goldChartEl, { // 呼叫 relayout 還原全圖視角
                    'xaxis.autorange': true, // X 軸自動全視角
                    'yaxis.autorange': true // Y 軸自動全視角
                }); // relayout 結束
            } // 判斷結束
        }); // 監聽結束
    } // 重置按鈕結束

    if (resetEquityBtn) { // 註冊重置 Equity 權益圖表按鈕
        resetEquityBtn.addEventListener('click', () => { // 點擊觸發重置
            const equityChartEl = document.getElementById('equity-chart'); // 取得 Equity 圖表
            if (equityChartEl) { // 存在 DOM
                Plotly.relayout(equityChartEl, { // 呼叫 relayout 還原全圖視角
                    'xaxis.autorange': true, // X 軸自動全視角
                    'yaxis.autorange': true // Y 軸自動全視角
                }); // relayout 結束
            } // 判斷結束
        }); // 監聽結束
    } // 重置 Equity 按鈕結束

    if (resetDxyBtn) { // 註冊重置 DXY 圖表按鈕
        resetDxyBtn.addEventListener('click', () => { // 點擊觸發重置
            const dxyChartEl = document.getElementById('dxy-chart'); // 取得 DXY 圖表
            if (dxyChartEl) { // 存在 DOM
                Plotly.relayout(dxyChartEl, { // 呼叫 relayout 還原
                    'xaxis.autorange': true, // X 軸自動
                    'yaxis.autorange': true // Y 軸自動
                }); // relayout 結束
            } // 判斷結束
        }); // 監聽結束
    } // 重置 DXY 按鈕結束

    function applyFilters() { // 執行過濾
        const keyword = searchInput.value.toLowerCase().trim(); // 關鍵字
        const selectedType = typeFilter.value; // 選取類型
        
        filteredTrades = globalData.completed_trades.filter(t => { // 篩選陣列
            const matchType = (selectedType === 'ALL') ||
                              (selectedType === 'Long' && t.type === 'Long') ||
                              (selectedType === 'Short' && t.type === 'Short') ||
                              (selectedType === 'Pyramid' && t.is_pyramid);
            
            const matchKeyword = !keyword ||
                                 t.trade_id.toString().includes(keyword) ||
                                 t.entry_date.toLowerCase().includes(keyword) ||
                                 t.exit_date.toLowerCase().includes(keyword) ||
                                 t.type.toLowerCase().includes(keyword) ||
                                 t.exit_reason.toLowerCase().includes(keyword);
            
            return matchType && matchKeyword; // 回傳判定
        }).sort((a, b) => b.trade_id - a.trade_id); // 確保篩選後始終依最新交易 (trade_id 倒序) 排序
        
        currentPage = 1; // 重置頁碼
        renderTradesTable(); // 重新渲染
    } // applyFilters 結束
    
    searchInput.addEventListener('input', applyFilters); // 搜尋輸入監聽
    typeFilter.addEventListener('change', applyFilters); // 選單切換監聽
    
    prevBtn.addEventListener('click', () => { // 上一頁點擊
        if (currentPage > 1) { // 頁碼 > 1
            currentPage--; // 遞減
            renderTradesTable(); // 重新繪製
        } // 判斷結束
    }); // 監聽結束
    
    nextBtn.addEventListener('click', () => { // 下一頁點擊
        if (currentPage * pageSize < filteredTrades.length) { // 未達末頁
            currentPage++; // 遞增
            renderTradesTable(); // 重新繪製
        } // 判斷結束
    }); // 監聽結束
} // setupEventListeners 結束

