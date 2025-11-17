#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试简化版 get_stock_price 函数"""

from tools import get_stock_price
import json

def test_stock(symbol, name):
    """测试单个股票"""
    print(f"\n{'='*60}")
    print(f"测试股票: {name} ({symbol})")
    print('='*60)
    
    result = get_stock_price.invoke({"symbol": symbol})
    data = json.loads(result)
    
    if "error" in data:
        print(f"❌ 错误: {data['error']}")
        return
    
    print(f"✅ 成功获取数据")
    print(f"\n股票代码: {data['symbol']}")
    print(f"Baostock代码: {data['bs_code']}")
    print(f"数据条数: {data['data_count']}")
    print(f"日期范围: {data['date_range']['start']} 至 {data['date_range']['end']}")
    
    print(f"\n最新数据 ({data['latest']['date']}):")
    print(f"  收盘价: {data['latest']['close']}")
    print(f"  开盘价: {data['latest']['open']}")
    print(f"  最高价: {data['latest']['high']}")
    print(f"  最低价: {data['latest']['low']}")
    print(f"  成交量: {data['latest']['volume']}")
    print(f"  成交额: {data['latest']['amount']}")
    print(f"  换手率: {data['latest']['turn']}%")
    print(f"  涨跌幅: {data['latest']['pctChg']}%")
    
    print(f"\n历史数据样例（最近3天）:")
    for i, record in enumerate(data['history'][-3:]):
        print(f"  {record['date']}: 收盘={record['close']}, 涨跌幅={record['pctChg']}%")

if __name__ == "__main__":
    # 测试上海A股
    test_stock("600000", "浦发银行")
    
    # 测试深圳A股
    test_stock("000001", "平安银行")
    
    # 测试创业板
    test_stock("300750", "宁德时代")
