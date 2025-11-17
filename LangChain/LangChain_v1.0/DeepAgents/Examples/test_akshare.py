"""测试 AKShare 股票与搜索工具

包含：
- A股/港股测试（保留现有示例）
- 新增两个搜索工具的简单测试：`web_search` 和 `search_financial_news`
"""

from tools import (
    get_stock_price,
    get_financial_statements,
    get_technical_indicators,
    web_search,
    search_financial_news,
)
import json

# 测试股票代码（示例）
test_symbols = [
    "600700",  # 示例：申万宏源（请根据需要替换为有效A股/港股代码）
]

print("=" * 80)
print("测试 AKShare 股票与搜索工具")
print("=" * 80)

for symbol in test_symbols:
    print(f"\n{'=' * 80}")
    print(f"测试股票代码: {symbol}")
    print("=" * 80)
    
    # 测试获取股票价格
    print("\n1. 获取股票价格和基本信息")
    print("-" * 80)
    try:
        result = get_stock_price.invoke({"symbol": symbol})
        print(json.dumps(json.loads(result), indent=2, ensure_ascii=False))
    except Exception as e:
        print({"error": f"get_stock_price 调用失败: {str(e)}"})
    
    # 测试获取财务报表
    print("\n2. 获取财务报表数据")
    print("-" * 80)
    try:
        result = get_financial_statements.invoke({"symbol": symbol})
        print(json.dumps(json.loads(result), indent=2, ensure_ascii=False))
    except Exception as e:
        print({"error": f"get_financial_statements 调用失败: {str(e)}"})
    
    # 测试获取技术指标
    print("\n3. 获取技术指标")
    print("-" * 80)
    try:
        result = get_technical_indicators.invoke({"symbol": symbol})
        print(json.dumps(json.loads(result), indent=2, ensure_ascii=False))
    except Exception as e:
        print({"error": f"get_technical_indicators 调用失败: {str(e)}"})
    
    print("\n")

# 新增：测试搜索工具
print("\n" + "#" * 40)
print("测试搜索工具: web_search 和 search_financial_news")
print("#" * 40)

query = "浦发银行 财报 2024"
print("\nA. 测试 web_search")
print("-" * 40)
try:
    res = web_search(query, max_results=3)
    print(json.dumps(res, indent=2, ensure_ascii=False))
except Exception as e:
    print({"error": f"web_search 调用失败: {str(e)}"})

print("\nB. 测试 search_financial_news（作为 tool.invoke 调用）")
print("-" * 40)
try:
    # 使用示例公司名和代码
    res = search_financial_news.invoke({"company_name": "浦发银行", "symbol": "600000"})
    print(json.dumps(json.loads(res), indent=2, ensure_ascii=False))
except Exception as e:
    print({"error": f"search_financial_news 调用失败: {str(e)}"})

print("\n测试完成")
print("=" * 80)
