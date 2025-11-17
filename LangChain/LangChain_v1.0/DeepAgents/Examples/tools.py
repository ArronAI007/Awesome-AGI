from langchain_core.tools import tool
import json
import akshare as ak
import baostock as bs
import pandas as pd
import logging
from tavily import TavilyClient
import requests
import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

# 禁用代理，避免连接问题
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
if 'HTTP_PROXY' in os.environ:
    del os.environ['HTTP_PROXY']
if 'HTTPS_PROXY' in os.environ:
    del os.environ['HTTPS_PROXY']
if 'http_proxy' in os.environ:
    del os.environ['http_proxy']
if 'https_proxy' in os.environ:
    del os.environ['https_proxy']

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
SEARXNG_URL = os.getenv("SEARXNG_URL", "").strip()

# 初始化 Tavily 客户端（如果有 API key）
tavily_client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None

def web_search(query: str, max_results: int = 5):
    """网络搜索：优先使用 Tavily，失败或不可用时降级到 SearXNG"""
    
    # 尝试使用 Tavily
    if tavily_client:
        try:
            result = tavily_client.search(query, max_results=max_results)
            logging.debug(f"使用 Tavily 搜索成功: {query}")
            return result
        except Exception as e:
            logging.warning(f"Tavily 搜索失败，降级到 SearXNG: {str(e)}")
    
    # 使用 SearXNG 后备或主搜索
    if not SEARXNG_URL:
        error_msg = "未配置搜索引擎（需要 TAVILY_API_KEY 或 SEARXNG_URL）"
        logging.error(error_msg)
        return {"error": error_msg}
    
    try:
        response = requests.get(
            f"{SEARXNG_URL}/search",
            params={
                "q": query,
                "format": "json"
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])[:max_results]
        
        logging.debug(f"使用 SearXNG 搜索成功: {query}")
        return {
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                    "score": r.get("score", 0)
                }
                for r in results
            ]
        }
    except Exception as e:
        error_msg = f"SearXNG 搜索失败: {str(e)}"
        logging.error(error_msg)
        return {"error": error_msg}

# 启动日志
if tavily_client and SEARXNG_URL:
    logging.info("✅ 搜索引擎已配置：Tavily（主）+ SearXNG（后备）")
elif tavily_client:
    logging.info("✅ 搜索引擎已配置：Tavily（仅）")
elif SEARXNG_URL:
    logging.info("✅ 搜索引擎已配置：SearXNG（仅）")
else:
    logging.warning("⚠️ 未配置任何搜索引擎")

@tool
def get_stock_price(symbol: str) -> str:
    """获取A股最近一个月的历史行情数据
    
    参数:
        symbol: A股股票代码，如 '000001'（平安银行）、'600000'（浦发银行）
    
    返回值:
        JSON字符串，包含以下字段：
        - symbol: 股票代码
        - bs_code: 带市场前缀的完整代码（如 sh.600000）
        - data_count: 历史数据条数
        - date_range: 数据日期范围（start/end）
        - latest: 最新一个交易日的详细数据
            - date: 日期
            - close: 收盘价
            - open: 开盘价
            - high: 最高价
            - low: 最低价
            - volume: 成交量（股）
            - amount: 成交额（元）
            - turn: 换手率（%）
            - pctChg: 涨跌幅（%）
        - history: 完整历史数据列表，每条包含date/open/high/low/close/volume等字段
        - data_source: 数据来源（Baostock）
    """
    logging.info(f"[工具] 正在获取A股历史行情: {symbol}")
    
    try:
        # 添加市场前缀：6开头是上海sh，0/3开头是深圳sz
        if symbol.startswith('6'):
            bs_code = f"sh.{symbol}"
        elif symbol.startswith('0') or symbol.startswith('3'):
            bs_code = f"sz.{symbol}"
        else:
            return json.dumps({"error": f"无法识别的股票代码格式: {symbol}"}, ensure_ascii=False)
        
        # 登录Baostock系统
        lg = bs.login()
        if lg.error_code != '0':
            logging.error(f"Baostock登录失败: {lg.error_msg}")
            return json.dumps({"error": f"Baostock登录失败: {lg.error_msg}"}, ensure_ascii=False)
        
        # 获取最近一个月的日线数据
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - pd.Timedelta(days=30)).strftime('%Y-%m-%d')
        
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3"  # 不复权
        )
        
        # 转换为DataFrame
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        
        bs.logout()
        
        if not data_list:
            return json.dumps({"error": f"未找到股票 {symbol} 的历史数据"}, ensure_ascii=False)
        
        # 转换为DataFrame并格式化
        result_df = pd.DataFrame(data_list, columns=rs.fields)
        
        # 将数据转换为字典列表，便于JSON序列化
        history_data = []
        for _, row in result_df.iterrows():
            history_data.append({
                "date": row['date'],
                "open": float(row['open']) if row['open'] else 0,
                "high": float(row['high']) if row['high'] else 0,
                "low": float(row['low']) if row['low'] else 0,
                "close": float(row['close']) if row['close'] else 0,
                "preclose": float(row['preclose']) if row['preclose'] else 0,
                "volume": float(row['volume']) if row['volume'] else 0,
                "amount": float(row['amount']) if row['amount'] else 0,
                "turn": float(row['turn']) if row['turn'] else 0,
                "pctChg": float(row['pctChg']) if row['pctChg'] else 0
            })
        
        # 获取最新一天的数据作为摘要
        latest = result_df.iloc[-1]
        
        result = {
            "symbol": symbol,
            "bs_code": bs_code,
            "data_count": len(history_data),
            "date_range": {
                "start": result_df.iloc[0]['date'],
                "end": latest['date']
            },
            "latest": {
                "date": latest['date'],
                "close": float(latest['close']) if latest['close'] else 0,
                "open": float(latest['open']) if latest['open'] else 0,
                "high": float(latest['high']) if latest['high'] else 0,
                "low": float(latest['low']) if latest['low'] else 0,
                "volume": float(latest['volume']) if latest['volume'] else 0,
                "amount": float(latest['amount']) if latest['amount'] else 0,
                "turn": float(latest['turn']) if latest['turn'] else 0,
                "pctChg": float(latest['pctChg']) if latest['pctChg'] else 0
            },
            "history": history_data,
            "data_source": "Baostock"
        }
        
        return json.dumps(result, indent=2, ensure_ascii=False)
        
    except Exception as e:
        # 确保logout
        try:
            bs.logout()
        except:
            pass
        logging.exception("get_stock_price 异常")
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@tool
def get_technical_indicators(symbol: str, period: str = "90") -> str:

    """计算A股的全面技术指标
    
    参数:
        symbol: A股股票代码，如 '000001'（平安银行）、'600000'（浦发银行）
        period: 历史数据天数，默认90天
    
    返回指标包括：
    - 趋势指标：SMA5/10/20/60, EMA12/26, MACD, 布林带
    - 动量指标：RSI, CCI, ROC, Williams %R
    - 摆动指标：KDJ
    - 成交量指标：OBV, 成交量均线
    - 波动性指标：ATR
    - 其他指标：乖离率, 心理线
    """
    logging.info(f"[工具] 正在计算A股技术指标: {symbol}")
    
    try:
        # 添加市场前缀：6开头是上海sh，0/3开头是深圳sz
        if symbol.startswith('6'):
            bs_code = f"sh.{symbol}"
        elif symbol.startswith('0') or symbol.startswith('3'):
            bs_code = f"sz.{symbol}"
        else:
            return json.dumps({"error": f"无法识别的股票代码格式: {symbol}"}, ensure_ascii=False)
        
        # 登录Baostock系统
        lg = bs.login()
        if lg.error_code != '0':
            logging.error(f"Baostock登录失败: {lg.error_msg}")
            return json.dumps({"error": f"Baostock登录失败: {lg.error_msg}"}, ensure_ascii=False)
        
        # 获取足够的历史数据用于计算技术指标（需要额外80天计算60日均线等）
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - pd.Timedelta(days=int(period) + 80)).strftime('%Y-%m-%d')
        
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3"  # 不复权
        )
        
        # 转换为DataFrame
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        
        bs.logout()
        
        if not data_list:
            return json.dumps({"error": f"未找到股票 {symbol} 的历史数据"}, ensure_ascii=False)
        
        # 转换为DataFrame
        df = pd.DataFrame(data_list, columns=rs.fields)
        
        # 转换数据类型
        for col in ['open', 'high', 'low', 'close', 'preclose', 'volume', 'amount', 'turn', 'pctChg']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # ==================== 1. 趋势指标 ====================
        # 简单移动平均线
        df['SMA5'] = df['close'].rolling(window=5).mean()
        df['SMA10'] = df['close'].rolling(window=10).mean()
        df['SMA20'] = df['close'].rolling(window=20).mean()
        df['SMA60'] = df['close'].rolling(window=60).mean()
        
        # 指数移动平均线
        df['EMA12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['close'].ewm(span=26, adjust=False).mean()
        
        # MACD指标
        df['MACD_DIF'] = df['EMA12'] - df['EMA26']
        df['MACD_DEA'] = df['MACD_DIF'].ewm(span=9, adjust=False).mean()
        df['MACD_BAR'] = (df['MACD_DIF'] - df['MACD_DEA']) * 2
        
        # 布林带
        df['BOLL_MID'] = df['close'].rolling(window=20).mean()
        std = df['close'].rolling(window=20).std()
        df['BOLL_UPPER'] = df['BOLL_MID'] + 2 * std
        df['BOLL_LOWER'] = df['BOLL_MID'] - 2 * std
        
        # ==================== 2. 动量指标 ====================
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # CCI (顺势指标)
        tp = (df['high'] + df['low'] + df['close']) / 3
        df['CCI'] = (tp - tp.rolling(window=20).mean()) / (0.015 * tp.rolling(window=20).std())
        
        # ROC (变动率)
        df['ROC'] = ((df['close'] - df['close'].shift(12)) / df['close'].shift(12)) * 100
        
        # Williams %R
        high_14 = df['high'].rolling(window=14).max()
        low_14 = df['low'].rolling(window=14).min()
        df['WR'] = ((high_14 - df['close']) / (high_14 - low_14)) * -100
        
        # ==================== 3. KDJ指标 ====================
        low_9 = df['low'].rolling(window=9).min()
        high_9 = df['high'].rolling(window=9).max()
        rsv = (df['close'] - low_9) / (high_9 - low_9) * 100
        df['K'] = rsv.ewm(com=2, adjust=False).mean()
        df['D'] = df['K'].ewm(com=2, adjust=False).mean()
        df['J'] = 3 * df['K'] - 2 * df['D']
        
        # ==================== 4. 成交量指标 ====================
        # OBV (能量潮)
        df['OBV'] = (df['volume'] * ((df['close'] > df['close'].shift(1)).astype(int) * 2 - 1)).cumsum()
        
        # 成交量均线
        df['VOL_MA5'] = df['volume'].rolling(window=5).mean()
        df['VOL_MA10'] = df['volume'].rolling(window=10).mean()
        
        # ==================== 5. 波动性指标 ====================
        # ATR (平均真实波幅)
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['ATR'] = true_range.rolling(window=14).mean()
        
        # ==================== 6. 其他指标 ====================
        # 乖离率
        df['BIAS'] = ((df['close'] - df['SMA20']) / df['SMA20']) * 100
        
        # 心理线 PSY
        df['PSY'] = (df['close'] > df['close'].shift(1)).rolling(window=12).sum() / 12 * 100
        
        # 获取最新数据
        latest = df.iloc[-1]
        
        # 判断趋势
        if not pd.isna(latest['SMA20']) and not pd.isna(latest['SMA60']):
            if latest['close'] > latest['SMA20'] and latest['SMA20'] > latest['SMA60']:
                trend_signal = "看涨"
            elif latest['close'] < latest['SMA20'] and latest['SMA20'] < latest['SMA60']:
                trend_signal = "看跌"
            else:
                trend_signal = "震荡"
        else:
            trend_signal = "数据不足"
        
        # MACD信号
        if not pd.isna(latest['MACD_DIF']) and not pd.isna(latest['MACD_DEA']):
            if latest['MACD_DIF'] > latest['MACD_DEA'] and latest['MACD_DIF'] > 0:
                macd_signal = "强势看涨"
            elif latest['MACD_DIF'] > latest['MACD_DEA'] and latest['MACD_DIF'] < 0:
                macd_signal = "弱势反弹"
            elif latest['MACD_DIF'] < latest['MACD_DEA'] and latest['MACD_DIF'] < 0:
                macd_signal = "强势看跌"
            else:
                macd_signal = "弱势回调"
        else:
            macd_signal = "数据不足"
        
        # KDJ信号
        if not pd.isna(latest['K']) and not pd.isna(latest['D']):
            if latest['K'] > 80 and latest['D'] > 80:
                kdj_signal = "超买"
            elif latest['K'] < 20 and latest['D'] < 20:
                kdj_signal = "超卖"
            elif latest['K'] > latest['D']:
                kdj_signal = "金叉看涨"
            else:
                kdj_signal = "死叉看跌"
        else:
            kdj_signal = "数据不足"
        
        # 构建返回结果
        result = {
            "symbol": symbol,
            "bs_code": bs_code,
            "date": latest['date'],
            "data_source": "Baostock",
            
            # 基本价格信息
            "price_info": {
                "current": float(latest['close']) if not pd.isna(latest['close']) else 0,
                "open": float(latest['open']) if not pd.isna(latest['open']) else 0,
                "high": float(latest['high']) if not pd.isna(latest['high']) else 0,
                "low": float(latest['low']) if not pd.isna(latest['low']) else 0,
                "change_percent": float(latest['pctChg']) if not pd.isna(latest['pctChg']) else 0,
                "volume": float(latest['volume']) if not pd.isna(latest['volume']) else 0,
                "amount": float(latest['amount']) if not pd.isna(latest['amount']) else 0,
                "turnover_rate": float(latest['turn']) if not pd.isna(latest['turn']) else 0
            },
            
            # 趋势指标
            "trend_indicators": {
                "sma5": round(float(latest['SMA5']), 2) if not pd.isna(latest['SMA5']) else None,
                "sma10": round(float(latest['SMA10']), 2) if not pd.isna(latest['SMA10']) else None,
                "sma20": round(float(latest['SMA20']), 2) if not pd.isna(latest['SMA20']) else None,
                "sma60": round(float(latest['SMA60']), 2) if not pd.isna(latest['SMA60']) else None,
                "ema12": round(float(latest['EMA12']), 2) if not pd.isna(latest['EMA12']) else None,
                "ema26": round(float(latest['EMA26']), 2) if not pd.isna(latest['EMA26']) else None
            },
            
            # MACD指标
            "macd": {
                "dif": round(float(latest['MACD_DIF']), 4) if not pd.isna(latest['MACD_DIF']) else None,
                "dea": round(float(latest['MACD_DEA']), 4) if not pd.isna(latest['MACD_DEA']) else None,
                "bar": round(float(latest['MACD_BAR']), 4) if not pd.isna(latest['MACD_BAR']) else None,
                "signal": macd_signal
            },
            
            # 布林带
            "bollinger_bands": {
                "upper": round(float(latest['BOLL_UPPER']), 2) if not pd.isna(latest['BOLL_UPPER']) else None,
                "middle": round(float(latest['BOLL_MID']), 2) if not pd.isna(latest['BOLL_MID']) else None,
                "lower": round(float(latest['BOLL_LOWER']), 2) if not pd.isna(latest['BOLL_LOWER']) else None
            },
            
            # 动量指标
            "momentum_indicators": {
                "rsi": round(float(latest['RSI']), 2) if not pd.isna(latest['RSI']) else None,
                "cci": round(float(latest['CCI']), 2) if not pd.isna(latest['CCI']) else None,
                "roc": round(float(latest['ROC']), 2) if not pd.isna(latest['ROC']) else None,
                "wr": round(float(latest['WR']), 2) if not pd.isna(latest['WR']) else None
            },
            
            # KDJ指标
            "kdj": {
                "k": round(float(latest['K']), 2) if not pd.isna(latest['K']) else None,
                "d": round(float(latest['D']), 2) if not pd.isna(latest['D']) else None,
                "j": round(float(latest['J']), 2) if not pd.isna(latest['J']) else None,
                "signal": kdj_signal
            },
            
            # 成交量指标
            "volume_indicators": {
                "obv": float(latest['OBV']) if not pd.isna(latest['OBV']) else None,
                "vol_ma5": float(latest['VOL_MA5']) if not pd.isna(latest['VOL_MA5']) else None,
                "vol_ma10": float(latest['VOL_MA10']) if not pd.isna(latest['VOL_MA10']) else None
            },
            
            # 波动性指标
            "volatility_indicators": {
                "atr": round(float(latest['ATR']), 4) if not pd.isna(latest['ATR']) else None
            },
            
            # 其他指标
            "other_indicators": {
                "bias": round(float(latest['BIAS']), 2) if not pd.isna(latest['BIAS']) else None,
                "psy": round(float(latest['PSY']), 2) if not pd.isna(latest['PSY']) else None
            },
            
            # 综合信号
            "signals": {
                "trend": trend_signal,
                "macd": macd_signal,
                "kdj": kdj_signal
            }
        }
        
        return json.dumps(result, indent=2, ensure_ascii=False)
        
    except Exception as e:
        # 确保logout
        try:
            bs.logout()
        except:
            pass
        logging.exception("get_technical_indicators 异常")
        return json.dumps({"error": f"计算技术指标失败: {str(e)}"}, ensure_ascii=False)
    
@tool
def get_financial_statements(symbol: str, report_type: str = "资产负债表") -> str:
    """获取A股关键财务报表数据
    
    参数:
        symbol: A股股票代码，如 '000001'（平安银行）、'600000'（浦发银行）
        report_type: 报表类型，支持 "资产负债表"、"利润表"、"现金流量表"
    """
    logging.info(f"[工具] 正在获取A股财务报表: {symbol}")
    
    try:
        # 添加市场前缀
        if symbol.startswith('6'):
            sina_symbol = f"sh{symbol}"
        elif symbol.startswith('0') or symbol.startswith('3'):
            sina_symbol = f"sz{symbol}"
        else:
            return json.dumps({
                "error": f"无法识别的A股代码格式: {symbol}",
                "hint": "仅支持A股代码，如 000001（深圳）或 600000（上海）"
            }, ensure_ascii=False)
        
        # 调用新浪财务报表接口
        df = ak.stock_financial_report_sina(stock=sina_symbol, symbol=report_type)
        
        if df.empty:
            return json.dumps({"error": f"未找到A股 {symbol} 的财务数据"}, ensure_ascii=False)
        
        # 取最新一期（第一行）所有字段
        latest = df.iloc[0].to_dict()
        latest["symbol"] = symbol
        latest["sina_symbol"] = sina_symbol
        latest["data_source"] = "新浪A股财务报表"
        
        return json.dumps(latest, indent=2, ensure_ascii=False)
        
    except Exception as e:
        logging.exception("get_financial_statements 异常")
        return json.dumps({"error": f"获取财务报表失败: {str(e)}"}, ensure_ascii=False)

@tool
def search_market_trends(topic: str) -> str:
    """搜索特定主题的市场趋势和分析（优先使用Tavily，失败时降级到SearXNG）
    
    参数:
        topic: 要搜索的主题，如 "人工智能"、"新能源汽车"、"半导体行业"
    
    返回值:
        JSON字符串，包含以下字段：
        - topic: 搜索主题
        - search_query: 实际使用的搜索查询语句
        - trend_results: 搜索结果列表
            - title: 文章标题
            - url: 文章链接
            - content: 内容摘要
            - score: 相关性评分（SearXNG）
    """
    try:
        search_query = f"{topic} 市场分析 趋势 2024 2025 投资前景 预测"
        results = web_search(search_query)

        return json.dumps({
            "topic": topic,
            "search_query": search_query,
            "trend_results": results
        }, indent=2, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"搜索趋势失败: {str(e)}"}, ensure_ascii=False)

@tool
def search(query: str, max_results: int = 5) -> str:
    """通用网络搜索工具（优先使用Tavily，失败时降级到SearXNG）
    
    参数:
        query: 搜索查询语句，支持中英文
        max_results: 返回的最大结果数量，默认5条
    
    返回值:
        JSON字符串，包含搜索结果列表：
        - title: 标题
        - url: 链接
        - content: 内容摘要
        - score: 相关性评分（仅SearXNG）
    
    使用场景:
        适用于任何需要网络搜索的场景，如查找资料、获取最新信息等
    """
    try:
        results = web_search(query, max_results=max_results)
        return json.dumps({
            "query": query,
            "max_results": max_results,
            "results": results
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"搜索失败: {str(e)}"}, ensure_ascii=False)
    
@tool
def search_financial_news(company_name: str, symbol: str) -> str:
    """搜索公司的最新财经新闻（优先使用Tavily，失败时降级到SearXNG）
    
    参数:
        company_name: 公司名称，如 "平安银行"、"贵州茅台"
        symbol: 股票代码，如 "000001"、"600519"
    
    返回值:
        JSON字符串，包含以下字段：
        - symbol: 股票代码
        - company: 公司名称
        - results: 新闻搜索结果列表
            - title: 新闻标题
            - url: 新闻链接
            - content: 新闻内容摘要
            - score: 相关性评分（SearXNG）
    
    注意:
        每次查询只调用一次此工具，除非明确要求更多新闻。
        如果已有新闻结果，请勿再次调用。
    """
    try:
        query = f"{company_name} {symbol} 财经新闻 股票 财报 最新"
        results = web_search(query)
        return json.dumps({
            "symbol": symbol,
            "company": company_name,
            "results": results
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@tool
def get_stock_detailed_info(symbol: str, info_type: str = "全部") -> str:
    """获取A股个股的详细信息
    
    参数:
        symbol: A股股票代码，如 '000001'（平安银行）、'600000'（浦发银行）
        info_type: 信息类型，支持 "全部"、"主营介绍"、"公司概况"、"筹码分布"、"分红情况"
    
    返回信息包括：
    - 主营介绍：主营业务、产品类型、产品名称、经营范围
    - 公司概况：公司基本信息、联系方式、行业信息等
    - 筹码分布：获利比例、平均成本、集中度等
    - 分红情况：历史分红记录
    """
    logging.info(f"[工具] 正在获取个股详细信息: {symbol}, 类型: {info_type}")
    
    result = {
        "symbol": symbol,
        "info_type": info_type,
        "data": {}
    }
    
    try:
        # 1. 主营介绍
        if info_type in ["全部", "主营介绍"]:
            try:
                logging.info(f"正在获取主营介绍...")
                zyjs_df = ak.stock_zyjs_ths(symbol=symbol)
                if not zyjs_df.empty:
                    # 转换为字典格式
                    zyjs_data = []
                    for _, row in zyjs_df.iterrows():
                        zyjs_data.append({
                            "股票代码": str(row.get("股票代码", "")),
                            "主营业务": str(row.get("主营业务", "")),
                            "产品类型": str(row.get("产品类型", "")),
                            "产品名称": str(row.get("产品名称", "")),
                            "经营范围": str(row.get("经营范围", ""))
                        })
                    result["data"]["主营介绍"] = zyjs_data
                else:
                    result["data"]["主营介绍"] = "暂无数据"
            except Exception as e:
                logging.warning(f"获取主营介绍失败: {str(e)}")
                result["data"]["主营介绍"] = f"获取失败: {str(e)}"
        
        # 2. 公司概况
        if info_type in ["全部", "公司概况"]:
            try:
                logging.info(f"正在获取公司概况...")
                profile_df = ak.stock_profile_cninfo(symbol=symbol)
                if not profile_df.empty:
                    # 转换为字典格式，只取第一行
                    profile_data = {}
                    for col in profile_df.columns:
                        value = profile_df[col].iloc[0] if len(profile_df) > 0 else ""
                        # 处理可能的 NaN 值
                        if pd.isna(value):
                            value = ""
                        profile_data[col] = str(value)
                    result["data"]["公司概况"] = profile_data
                else:
                    result["data"]["公司概况"] = "暂无数据"
            except Exception as e:
                logging.warning(f"获取公司概况失败: {str(e)}")
                result["data"]["公司概况"] = f"获取失败: {str(e)}"
        
        # 3. 筹码分布
        if info_type in ["全部", "筹码分布"]:
            try:
                logging.info(f"正在获取筹码分布...")
                cyq_df = ak.stock_cyq_em(symbol=symbol, adjust="")
                if not cyq_df.empty:
                    # 只返回最近10个交易日的数据
                    cyq_recent = cyq_df.tail(10)
                    cyq_data = []
                    for _, row in cyq_recent.iterrows():
                        cyq_data.append({
                            "日期": str(row.get("日期", "")),
                            "获利比例": float(row.get("获利比例", 0)) if not pd.isna(row.get("获利比例")) else 0,
                            "平均成本": float(row.get("平均成本", 0)) if not pd.isna(row.get("平均成本")) else 0,
                            "90成本_低": float(row.get("90成本-低", 0)) if not pd.isna(row.get("90成本-低")) else 0,
                            "90成本_高": float(row.get("90成本-高", 0)) if not pd.isna(row.get("90成本-高")) else 0,
                            "90集中度": float(row.get("90集中度", 0)) if not pd.isna(row.get("90集中度")) else 0,
                            "70成本_低": float(row.get("70成本-低", 0)) if not pd.isna(row.get("70成本-低")) else 0,
                            "70成本_高": float(row.get("70成本-高", 0)) if not pd.isna(row.get("70成本-高")) else 0,
                            "70集中度": float(row.get("70集中度", 0)) if not pd.isna(row.get("70集中度")) else 0
                        })
                    result["data"]["筹码分布"] = cyq_data
                else:
                    result["data"]["筹码分布"] = "暂无数据"
            except Exception as e:
                logging.warning(f"获取筹码分布失败: {str(e)}")
                result["data"]["筹码分布"] = f"获取失败: {str(e)}"
        
        # 4. 分红情况
        if info_type in ["全部", "分红情况"]:
            try:
                logging.info(f"正在获取分红情况...")
                fhps_df = ak.stock_fhps_detail_ths(symbol=symbol)
                if not fhps_df.empty:
                    fhps_data = []
                    for _, row in fhps_df.iterrows():
                        fhps_data.append({
                            "报告期": str(row.get("报告期", "")),
                            "分红方案说明": str(row.get("分红方案说明", "")),
                            "股权登记日": str(row.get("A股股权登记日", "") or row.get("B股股权登记日", "")),
                            "除权除息日": str(row.get("A股除权除息日", "") or row.get("B股除权除息日", "")),
                            "分红总额": str(row.get("分红总额", "")),
                            "方案进度": str(row.get("方案进度", "")),
                            "股利支付率": str(row.get("股利支付率", "")),
                            "税前分红率": str(row.get("税前分红率", ""))
                        })
                    result["data"]["分红情况"] = fhps_data
                else:
                    result["data"]["分红情况"] = "暂无分红数据"
            except Exception as e:
                logging.warning(f"获取分红情况失败: {str(e)}")
                result["data"]["分红情况"] = f"获取失败: {str(e)}"
        
        return json.dumps(result, indent=2, ensure_ascii=False)
        
    except Exception as e:
        logging.exception("get_stock_detailed_info 异常")
        return json.dumps({"error": f"获取个股详细信息失败: {str(e)}"}, ensure_ascii=False)

@tool
def get_stock_news(symbol: str, max_count: int = 5) -> str:
    """获取A股个股的最新新闻资讯
    
    参数:
        symbol: A股股票代码，如 '000001'（平安银行）、'600000'（浦发银行）
        max_count: 返回的新闻数量，默认20条，最多100条
    
    返回信息包括：
    - 新闻标题
    - 新闻内容摘要
    - 发布时间
    - 文章来源
    - 新闻链接
    """
    logging.info(f"[工具] 正在获取个股新闻: {symbol}, 数量: {max_count}")
    
    try:
        # 调用东方财富个股新闻接口
        news_df = ak.stock_news_em(symbol=symbol)
        
        if news_df.empty:
            return json.dumps({
                "symbol": symbol,
                "count": 0,
                "news": [],
                "message": "暂无新闻数据"
            }, indent=2, ensure_ascii=False)
        
        # 限制返回数量
        news_df = news_df.head(min(max_count, 100))
        
        # 转换为字典列表
        news_list = []
        for _, row in news_df.iterrows():
            news_item = {
                "标题": str(row.get("新闻标题", "")),
                "内容": str(row.get("新闻内容", "")),
                "发布时间": str(row.get("发布时间", "")),
                "来源": str(row.get("文章来源", "")),
                "链接": str(row.get("新闻链接", ""))
            }
            news_list.append(news_item)
        
        result = {
            "symbol": symbol,
            "count": len(news_list),
            "news": news_list,
            "data_source": "东方财富"
        }
        
        return json.dumps(result, indent=2, ensure_ascii=False)
        
    except Exception as e:
        logging.exception("get_stock_news 异常")
        return json.dumps({"error": f"获取个股新闻失败: {str(e)}"}, ensure_ascii=False)

@tool
def get_stock_research_report(symbol: str, max_count: int = 5) -> str:
    """获取A股个股的研究报告
    
    参数:
        symbol: A股股票代码，如 '000001'（平安银行）、'600000'（浦发银行）
        max_count: 返回的研报数量，默认10条
    
    返回信息包括：
    - 报告名称
    - 东财评级（买入、增持、中性等）
    - 研究机构
    - 近一月个股研报数
    - 盈利预测（2024-2026年收益和市盈率）
    - 所属行业
    - 发布日期
    - 报告PDF链接
    """
    logging.info(f"[工具] 正在获取个股研究报告: {symbol}, 数量: {max_count}")
    
    try:
        # 调用东方财富个股研报接口
        report_df = ak.stock_research_report_em(symbol=symbol)
        
        if report_df.empty:
            return json.dumps({
                "symbol": symbol,
                "count": 0,
                "reports": [],
                "message": "暂无研究报告数据"
            }, indent=2, ensure_ascii=False)
        
        # 限制返回数量
        report_df = report_df.head(max_count)
        
        # 转换为字典列表
        reports_list = []
        for _, row in report_df.iterrows():
            report_item = {
                "股票代码": str(row.get("股票代码", "")),
                "股票简称": str(row.get("股票简称", "")),
                "报告名称": str(row.get("报告名称", "")),
                "东财评级": str(row.get("东财评级", "-")) if pd.notna(row.get("东财评级")) else "-",
                "机构": str(row.get("机构", "")),
                "近一月研报数": int(row.get("近一月个股研报数", 0)) if pd.notna(row.get("近一月个股研报数")) else 0,
                "盈利预测": {
                    "2024年": {
                        "收益": float(row.get("2024-盈利预测-收益", 0)) if pd.notna(row.get("2024-盈利预测-收益")) else None,
                        "市盈率": float(row.get("2024-盈利预测-市盈率", 0)) if pd.notna(row.get("2024-盈利预测-市盈率")) else None
                    },
                    "2025年": {
                        "收益": float(row.get("2025-盈利预测-收益", 0)) if pd.notna(row.get("2025-盈利预测-收益")) else None,
                        "市盈率": float(row.get("2025-盈利预测-市盈率", 0)) if pd.notna(row.get("2025-盈利预测-市盈率")) else None
                    },
                    "2026年": {
                        "收益": float(row.get("2026-盈利预测-收益", 0)) if pd.notna(row.get("2026-盈利预测-收益")) else None,
                        "市盈率": float(row.get("2026-盈利预测-市盈率", 0)) if pd.notna(row.get("2026-盈利预测-市盈率")) else None
                    }
                },
                "行业": str(row.get("行业", "")),
                "发布日期": str(row.get("日期", "")),
                "报告PDF链接": str(row.get("报告PDF链接", ""))
            }
            reports_list.append(report_item)
        
        result = {
            "symbol": symbol,
            "stock_name": reports_list[0]["股票简称"] if reports_list else "",
            "count": len(reports_list),
            "total_reports_last_month": reports_list[0]["近一月研报数"] if reports_list else 0,
            "reports": reports_list,
            "data_source": "东方财富-数据中心-研究报告"
        }
        
        return json.dumps(result, indent=2, ensure_ascii=False)
        
    except Exception as e:
        logging.exception("get_stock_research_report 异常")
        return json.dumps({"error": f"获取个股研究报告失败: {str(e)}"}, ensure_ascii=False)
