# 第 6 篇：生产级的工程问题——线上监控 + 成本估算
# 开发的时候你觉得 Agent 主要是用来查天气和发邮件的。上线后发现 60% 的用户在用你的
# Agent 写情书。你的天气 Prompt 优化对这个场景完全没用——这就是评估体系第 4 层
# （线上监控）要解决的问题：持续记录每一次交互，知道用户到底在用 Agent 干什么、
# 稳不稳、贵不贵。
import collections
from datetime import datetime, timedelta


# ============================================================
# 层次 4：线上监控——记录每一次交互，分析使用模式
# ============================================================
class AgentMonitor:
    """Agent 线上监控：记录每一次交互，分析使用模式"""

    def __init__(self):
        self.records = []  # 生产环境应该写入数据库

    def log_interaction(self, user_input: str, response: str,
                        steps: int, tool_calls: list, duration: float,
                        errors: list = None):
        """记录一次完整交互"""
        self.records.append({
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input[:500],
            "response_preview": response[:200],
            "steps_used": steps,
            "tool_calls": tool_calls,
            "duration_seconds": duration,
            "errors": errors or [],
        })

    def get_stats(self, hours: int = 24) -> dict:
        """获取过去 N 小时的统计"""
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = [r for r in self.records
                  if datetime.fromisoformat(r["timestamp"]) > cutoff]

        if not recent:
            return {"message": "暂无数据"}

        # 成功率
        success_count = sum(1 for r in recent if not r["errors"])
        success_rate = success_count / len(recent) * 100

        # 平均步数
        avg_steps = sum(r["steps_used"] for r in recent) / len(recent)

        # 平均耗时
        avg_duration = sum(r["duration_seconds"] for r in recent) / len(recent)

        # 最常调用的工具
        tool_counter = collections.Counter()
        for r in recent:
            for tc in r["tool_calls"]:
                tool_counter[tc] += 1

        # 最常见的错误
        error_counter = collections.Counter()
        for r in recent:
            for e in r["errors"]:
                error_counter[e] += 1

        return {
            "time_range": f"过去 {hours} 小时",
            "total_interactions": len(recent),
            "success_rate": f"{success_rate:.1f}%",
            "avg_steps": f"{avg_steps:.1f}",
            "avg_duration": f"{avg_duration:.1f}s",
            "top_tools": tool_counter.most_common(5),
            "top_errors": error_counter.most_common(5),
        }

    def alert_if_needed(self, thresholds: dict = None) -> list[str]:
        """检查是否需要告警"""
        if thresholds is None:
            thresholds = {
                "success_rate_min": 80,   # 成功率低于 80% 告警
                "avg_duration_max": 30,    # 平均耗时超过 30s 告警
                "avg_steps_max": 8,        # 平均步数超过 8 步告警
                "error_rate_max": 10,      # 错误率超过 10% 告警
            }

        stats = self.get_stats(hours=1)  # 最近 1 小时
        if "message" in stats:
            return []

        alerts = []

        success_rate = float(stats["success_rate"].rstrip("%"))
        if success_rate < thresholds["success_rate_min"]:
            alerts.append(f"🚨 成功率过低: {stats['success_rate']}（阈值 {thresholds['success_rate_min']}%）")

        avg_duration = float(stats["avg_duration"].rstrip("s"))
        if avg_duration > thresholds["avg_duration_max"]:
            alerts.append(f"⏱️ 平均耗时过长: {stats['avg_duration']}（阈值 {thresholds['avg_duration_max']}s）")

        avg_steps = float(stats["avg_steps"])
        if avg_steps > thresholds["avg_steps_max"]:
            alerts.append(f"🔄 平均步数过多: {stats['avg_steps']}（阈值 {thresholds['avg_steps_max']}）")

        return alerts


# ============================================================
# 成本控制：Agent 到底花多少钱？
# ============================================================
class CostEstimator:
    """Agent 成本估算器"""

    # 大约的定价（2025 年参考，实际以官方为准）
    PRICING = {
        "gpt-4o": {"input": 2.50, "output": 10.00},    # 每百万 token 美元
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
        "deepseek-v3": {"input": 0.27, "output": 1.10},
    }

    def estimate(self, model: str, avg_input_tokens: int,
                 avg_output_tokens: int, avg_steps: int,
                 daily_queries: int) -> dict:
        """估算每天/每月的成本"""
        pricing = self.PRICING.get(model, self.PRICING["gpt-4o-mini"])

        # 每次查询的 token 消耗
        input_cost_per_query = (avg_input_tokens / 1_000_000) * pricing["input"]
        output_cost_per_query = (avg_output_tokens * avg_steps / 1_000_000) * pricing["output"]
        cost_per_query = input_cost_per_query + output_cost_per_query

        # 每日/每月
        daily_cost = cost_per_query * daily_queries
        monthly_cost = daily_cost * 30

        return {
            "model": model,
            "cost_per_query": f"${cost_per_query:.4f}",
            "daily_cost": f"${daily_cost:.2f}",
            "monthly_cost": f"${monthly_cost:.2f}",
            "monthly_queries": daily_queries * 30,
        }


if __name__ == "__main__":
    # 示例：中等规模的 Agent
    estimator = CostEstimator()
    result = estimator.estimate(
        model="gpt-4o",
        avg_input_tokens=2000,   # system prompt + 记忆 + 用户输入
        avg_output_tokens=500,   # 每步输出
        avg_steps=5,             # 平均 5 步推理
        daily_queries=10000,     # 每天 1 万次查询
    )

    for k, v in result.items():
        print(f"  {k}: {v}")

    # 输出:
    #   model: gpt-4o
    #   cost_per_query: $0.0300       ← 一次查询 3 美分
    #   daily_cost: $300.00           ← 每天 300 美元
    #   monthly_cost: $9000.00        ← 每月 9000 美元
    #   monthly_queries: 300000
