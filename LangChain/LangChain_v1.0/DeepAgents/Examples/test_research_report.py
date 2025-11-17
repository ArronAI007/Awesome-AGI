#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试个股研究报告工具"""

import json
from tools import get_stock_research_report


def test_research_report():
    """测试获取个股研究报告 - 详细显示前3条"""
    print("=" * 80)
    print("测试：获取平安银行(000001)的研究报告")
    print("=" * 80)
    
    result_str = get_stock_research_report.invoke({"symbol": "000001", "max_count": 10})
    result = json.loads(result_str)
    
    print(f"\n股票: {result.get('stock_name', '')} ({result.get('symbol', '')})")
    print(f"近一月研报数: {result.get('total_reports_last_month', 0)}")
    print(f"返回研报数: {result.get('count', 0)}")
    print(f"数据来源: {result.get('data_source', '')}")
    
    if result.get('reports'):
        print("\n" + "=" * 80)
        print("前3条研究报告详情:")
        print("=" * 80)
        
        for i, report in enumerate(result['reports'][:3], 1):
            print(f"\n【报告 {i}】")
            print(f"报告名称: {report.get('报告名称', '')}")
            print(f"研究机构: {report.get('机构', '')}")
            print(f"东财评级: {report.get('东财评级', '-')}")
            print(f"发布日期: {report.get('发布日期', '')}")
            print(f"所属行业: {report.get('行业', '')}")
            
            # 显示盈利预测
            forecast = report.get('盈利预测', {})
            print("\n盈利预测:")
            for year in ['2024年', '2025年', '2026年']:
                year_data = forecast.get(year, {})
                earnings = year_data.get('收益')
                pe = year_data.get('市盈率')
                if earnings or pe:
                    print(f"  {year}: 收益={earnings if earnings else 'N/A'}, 市盈率={pe if pe else 'N/A'}")
            
            print(f"\nPDF链接: {report.get('报告PDF链接', '')}")
            print("-" * 80)


def test_multiple_stocks():
    """测试多只股票的研报概况"""
    print("\n" + "=" * 80)
    print("测试：多只股票研报概况")
    print("=" * 80)
    
    stocks = [
        ("600000", "浦发银行"),
        ("300750", "宁德时代"),
        ("600519", "贵州茅台")
    ]
    
    for symbol, name in stocks:
        result_str = get_stock_research_report.invoke({"symbol": symbol, "max_count": 3})
        result = json.loads(result_str)
        
        print(f"\n{name} ({symbol}):")
        print(f"  近一月研报数: {result.get('total_reports_last_month', 0)}")
        print(f"  返回研报数: {result.get('count', 0)}")
        
        if result.get('reports'):
            latest = result['reports'][0]
            print(f"  最新研报: {latest.get('报告名称', '')}")
            print(f"  机构: {latest.get('机构', '')}")
            print(f"  评级: {latest.get('东财评级', '-')}")
            print(f"  日期: {latest.get('发布日期', '')}")


def test_report_summary():
    """测试研报评级统计"""
    print("\n" + "=" * 80)
    print("测试：研报评级统计 - 平安银行")
    print("=" * 80)
    
    result_str = get_stock_research_report.invoke({"symbol": "000001", "max_count": 50})
    result = json.loads(result_str)
    
    if result.get('reports'):
        # 统计评级分布
        ratings = {}
        institutions = set()
        
        for report in result['reports']:
            rating = report.get('东财评级', '-')
            ratings[rating] = ratings.get(rating, 0) + 1
            institutions.add(report.get('机构', ''))
        
        print(f"\n统计了 {result.get('count', 0)} 条研报")
        print(f"涉及 {len(institutions)} 家研究机构")
        
        print("\n评级分布:")
        for rating, count in sorted(ratings.items(), key=lambda x: x[1], reverse=True):
            print(f"  {rating}: {count} 条")
        
        # 显示最近5条研报标题
        print("\n最近5条研报:")
        for i, report in enumerate(result['reports'][:5], 1):
            print(f"  {i}. [{report.get('发布日期', '')}] {report.get('报告名称', '')[:50]}...")


if __name__ == "__main__":
    # 测试1: 详细研报信息
    test_research_report()
    
    # 测试2: 多股票对比
    test_multiple_stocks()
    
    # 测试3: 评级统计
    test_report_summary()
    
    print("\n" + "=" * 80)
    print("所有测试完成！")
    print("=" * 80)
