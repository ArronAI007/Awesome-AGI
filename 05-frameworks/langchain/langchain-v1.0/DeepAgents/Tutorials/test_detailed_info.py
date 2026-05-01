#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试 get_stock_detailed_info 函数"""

from tools import get_stock_detailed_info
import json

def test_detailed_info(symbol, name, info_type="全部"):
    """测试个股详细信息"""
    print(f"\n{'='*80}")
    print(f"测试股票: {name} ({symbol}) - 信息类型: {info_type}")
    print('='*80)
    
    result = get_stock_detailed_info.invoke({
        "symbol": symbol,
        "info_type": info_type
    })
    data = json.loads(result)
    
    if "error" in data:
        print(f"❌ 错误: {data['error']}")
        return
    
    print(f"✅ 成功获取数据")
    print(f"\n股票代码: {data['symbol']}")
    print(f"查询类型: {data['info_type']}")
    
    # 显示各类信息
    for key, value in data['data'].items():
        print(f"\n{'─'*80}")
        print(f"【{key}】")
        print('─'*80)
        
        if isinstance(value, str):
            print(f"  {value}")
        elif isinstance(value, dict):
            for k, v in value.items():
                if v:  # 只显示非空值
                    print(f"  {k}: {v}")
        elif isinstance(value, list):
            if len(value) > 0:
                print(f"  共 {len(value)} 条记录")
                # 显示前3条
                for i, item in enumerate(value[:3], 1):
                    print(f"\n  记录 {i}:")
                    if isinstance(item, dict):
                        for k, v in item.items():
                            print(f"    {k}: {v}")
                if len(value) > 3:
                    print(f"\n  ... 还有 {len(value) - 3} 条记录")
            else:
                print("  暂无数据")

def test_specific_info_type(symbol, name):
    """测试单独的信息类型"""
    info_types = ["主营介绍", "公司概况", "资金流向", "筹码分布", "增减持", "分红情况"]
    
    for info_type in info_types:
        print(f"\n{'='*80}")
        print(f"测试: {name} ({symbol}) - {info_type}")
        print('='*80)
        
        result = get_stock_detailed_info.invoke({
            "symbol": symbol,
            "info_type": info_type
        })
        data = json.loads(result)
        
        if "error" in data:
            print(f"❌ 错误: {data['error']}")
            continue
        
        info_data = data['data'].get(info_type)
        if isinstance(info_data, str):
            print(f"  状态: {info_data}")
        elif isinstance(info_data, list):
            print(f"  ✅ 获取到 {len(info_data)} 条记录")
        elif isinstance(info_data, dict):
            print(f"  ✅ 获取到详细信息（{len(info_data)} 个字段）")
        else:
            print(f"  状态: 数据类型 {type(info_data)}")

if __name__ == "__main__":
    # 测试1: 获取全部信息（可能较慢）
    print("\n" + "="*80)
    print("测试模式1: 获取全部信息")
    print("="*80)
    test_detailed_info("000001", "平安银行", "全部")
    
    # 测试2: 分别测试各个信息类型
    print("\n\n" + "="*80)
    print("测试模式2: 分别测试各个信息类型")
    print("="*80)
    test_specific_info_type("600000", "浦发银行")
