#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试 get_stock_news 函数"""

from tools import get_stock_news
import json

def test_stock_news(symbol, name, max_count=10):
    """测试个股新闻"""
    print(f"\n{'='*80}")
    print(f"测试股票新闻: {name} ({symbol}) - 获取 {max_count} 条")
    print('='*80)
    
    result = get_stock_news.invoke({
        "symbol": symbol,
        "max_count": max_count
    })
    data = json.loads(result)
    
    if "error" in data:
        print(f"❌ 错误: {data['error']}")
        return
    
    print(f"✅ 成功获取新闻")
    print(f"\n数据来源: {data.get('data_source')}")
    print(f"新闻总数: {data['count']} 条")
    
    if data['count'] == 0:
        print(f"消息: {data.get('message', '暂无数据')}")
        return
    
    # 显示前5条新闻的详细信息
    print(f"\n{'─'*80}")
    print("最新新闻（前5条）:")
    print('─'*80)
    
    for i, news in enumerate(data['news'][:5], 1):
        print(f"\n【新闻 {i}】")
        print(f"  标题: {news['标题']}")
        print(f"  发布时间: {news['发布时间']}")
        print(f"  来源: {news['来源']}")
        print(f"  内容: {news['内容'][:100]}..." if len(news['内容']) > 100 else f"  内容: {news['内容']}")
        print(f"  链接: {news['链接']}")
    
    if data['count'] > 5:
        print(f"\n... 还有 {data['count'] - 5} 条新闻")

def test_multiple_stocks():
    """测试多个股票的新闻"""
    stocks = [
        ("000001", "平安银行", 10),
        ("600000", "浦发银行", 10),
        ("300750", "宁德时代", 15)
    ]
    
    for symbol, name, count in stocks:
        test_stock_news(symbol, name, count)

def test_news_summary(symbol, name):
    """测试新闻摘要（只获取3条）"""
    print(f"\n{'='*80}")
    print(f"快速新闻摘要: {name} ({symbol})")
    print('='*80)
    
    result = get_stock_news.invoke({
        "symbol": symbol,
        "max_count": 3
    })
    data = json.loads(result)
    
    if "error" in data or data['count'] == 0:
        print(f"  无新闻数据")
        return
    
    print(f"  共 {data['count']} 条最新新闻:")
    for i, news in enumerate(data['news'], 1):
        print(f"    {i}. [{news['发布时间']}] {news['标题']}")

if __name__ == "__main__":
    # 测试1: 详细测试单个股票
    print("\n" + "="*80)
    print("测试模式1: 详细新闻信息")
    print("="*80)
    test_stock_news("000001", "平安银行", 10)
    
    # 测试2: 快速新闻摘要
    print("\n\n" + "="*80)
    print("测试模式2: 快速新闻摘要")
    print("="*80)
    test_news_summary("600000", "浦发银行")
    test_news_summary("300750", "宁德时代")
