#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试简化版 get_financial_statements 函数"""

from tools import get_financial_statements
import json

def test_financial_statement(symbol, name, report_type):
    """测试单个股票的财务报表"""
    print(f"\n{'='*60}")
    print(f"测试股票: {name} ({symbol}) - {report_type}")
    print('='*60)
    
    result = get_financial_statements.invoke({
        "symbol": symbol,
        "report_type": report_type
    })
    data = json.loads(result)
    
    if "error" in data:
        print(f"❌ 错误: {data['error']}")
        return
    
    print(f"✅ 成功获取数据")
    print(f"\n股票代码: {data.get('symbol')}")
    print(f"新浪代码: {data.get('sina_symbol')}")
    print(f"数据来源: {data.get('data_source')}")
    
    # 显示主要财务指标（排除元数据字段）
    print(f"\n主要财务指标:")
    exclude_keys = ['symbol', 'sina_symbol', 'data_source']
    count = 0
    for key, value in data.items():
        if key not in exclude_keys:
            print(f"  {key}: {value}")
            count += 1
            if count >= 100:  # 只显示前10个指标
                print(f"  ... 共 {len(data) - len(exclude_keys)} 个指标")
                break

if __name__ == "__main__":
    # 测试资产负债表
    test_financial_statement("600000", "浦发银行", "资产负债表")
    
    # 测试利润表
    test_financial_statement("000001", "平安银行", "利润表")
    
    # 测试现金流量表
    test_financial_statement("300750", "宁德时代", "现金流量表")
