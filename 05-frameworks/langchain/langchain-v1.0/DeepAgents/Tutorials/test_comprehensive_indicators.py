#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试增强版 get_technical_indicators 函数"""

from tools import get_technical_indicators
import json

def test_comprehensive_indicators(symbol, name):
    """测试全面的技术指标"""
    print(f"\n{'='*80}")
    print(f"测试股票: {name} ({symbol})")
    print('='*80)
    
    result = get_technical_indicators.invoke({"symbol": symbol, "period": "90"})
    data = json.loads(result)
    
    if "error" in data:
        print(f"❌ 错误: {data['error']}")
        return
    
    print(f"✅ 成功计算全面技术指标")
    print(f"\n📊 基本信息:")
    print(f"  股票代码: {data['symbol']}")
    print(f"  数据日期: {data['date']}")
    print(f"  数据来源: {data['data_source']}")
    
    # 价格信息
    price = data['price_info']
    print(f"\n💰 价格信息:")
    print(f"  当前价: {price['current']:.2f}")
    print(f"  开盘价: {price['open']:.2f}")
    print(f"  最高价: {price['high']:.2f}")
    print(f"  最低价: {price['low']:.2f}")
    print(f"  涨跌幅: {price['change_percent']:.2f}%")
    print(f"  成交量: {price['volume']:.0f}")
    print(f"  成交额: {price['amount']:.2f}")
    print(f"  换手率: {price['turnover_rate']:.2f}%")
    
    # 趋势指标
    trend = data['trend_indicators']
    print(f"\n📈 趋势指标 (均线系统):")
    print(f"  SMA5:  {trend['sma5']}")
    print(f"  SMA10: {trend['sma10']}")
    print(f"  SMA20: {trend['sma20']}")
    print(f"  SMA60: {trend['sma60']}")
    print(f"  EMA12: {trend['ema12']}")
    print(f"  EMA26: {trend['ema26']}")
    
    # MACD
    macd = data['macd']
    print(f"\n📉 MACD指标:")
    print(f"  DIF (快线): {macd['dif']}")
    print(f"  DEA (慢线): {macd['dea']}")
    print(f"  BAR (柱状): {macd['bar']}")
    print(f"  信号: {macd['signal']}")
    
    # 布林带
    boll = data['bollinger_bands']
    print(f"\n🎯 布林带:")
    print(f"  上轨: {boll['upper']}")
    print(f"  中轨: {boll['middle']}")
    print(f"  下轨: {boll['lower']}")
    
    # 动量指标
    momentum = data['momentum_indicators']
    print(f"\n⚡ 动量指标:")
    print(f"  RSI (相对强弱): {momentum['rsi']}")
    print(f"  CCI (顺势指标): {momentum['cci']}")
    print(f"  ROC (变动率):   {momentum['roc']:.2f}%")
    print(f"  WR (威廉指标):  {momentum['wr']}")
    
    # KDJ
    kdj = data['kdj']
    print(f"\n🔄 KDJ指标:")
    print(f"  K值: {kdj['k']}")
    print(f"  D值: {kdj['d']}")
    print(f"  J值: {kdj['j']}")
    print(f"  信号: {kdj['signal']}")
    
    # 成交量指标
    volume = data['volume_indicators']
    print(f"\n📊 成交量指标:")
    print(f"  OBV (能量潮):     {volume['obv']:.0f}")
    print(f"  VOL_MA5 (5日均): {volume['vol_ma5']:.0f}")
    print(f"  VOL_MA10 (10日均): {volume['vol_ma10']:.0f}")
    
    # 波动性指标
    volatility = data['volatility_indicators']
    print(f"\n📐 波动性指标:")
    print(f"  ATR (平均真实波幅): {volatility['atr']}")
    
    # 其他指标
    other = data['other_indicators']
    print(f"\n🔍 其他指标:")
    print(f"  BIAS (乖离率):  {other['bias']:.2f}%")
    print(f"  PSY (心理线):   {other['psy']:.2f}%")
    
    # 综合信号
    signals = data['signals']
    print(f"\n🚦 综合信号:")
    print(f"  趋势信号: {signals['trend']}")
    print(f"  MACD信号: {signals['macd']}")
    print(f"  KDJ信号:  {signals['kdj']}")
    
    # 技术面分析总结
    print(f"\n📋 技术面分析总结:")
    
    # 超买超卖判断
    rsi_val = momentum['rsi']
    if rsi_val:
        if rsi_val > 70:
            print(f"  • RSI={rsi_val:.2f} 处于超买区域，警惕回调风险")
        elif rsi_val < 30:
            print(f"  • RSI={rsi_val:.2f} 处于超卖区域，可能存在反弹机会")
        else:
            print(f"  • RSI={rsi_val:.2f} 处于正常区域")
    
    # 布林带位置
    current = price['current']
    if boll['upper'] and boll['lower']:
        boll_position = (current - boll['lower']) / (boll['upper'] - boll['lower']) * 100
        print(f"  • 价格位于布林带 {boll_position:.1f}% 位置", end="")
        if boll_position > 80:
            print(" (接近上轨，超买)")
        elif boll_position < 20:
            print(" (接近下轨，超卖)")
        else:
            print(" (中性)")
    
    # MACD金叉死叉
    if macd['dif'] and macd['dea']:
        if macd['dif'] > macd['dea']:
            print(f"  • MACD处于金叉状态，{macd['signal']}")
        else:
            print(f"  • MACD处于死叉状态，{macd['signal']}")

if __name__ == "__main__":
    # 测试三只不同类型的股票
    test_comprehensive_indicators("600000", "浦发银行")
    test_comprehensive_indicators("000001", "平安银行")
    test_comprehensive_indicators("300750", "宁德时代")
