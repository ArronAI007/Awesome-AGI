# 第 6 篇：生产级的工程问题——评估体系
# 改了一版 Prompt，Agent 的回复"感觉"变好了——但怎么证明？没有评估体系，
# 你的每一次改动都是蒙的。评估分四个层次：
#   层次 1：能跑就行         → 功能正确性（有没有报错？有没有回复？）
#   层次 2：回答对了吗       → 准确性评估（查天气的结果对吗？发邮件的收件人对吗？）
#   层次 3：用着舒服吗       → 体验评估（回复自然吗？步骤合理吗？符合预期吗？）
#   层次 4：长期稳定吗       → 回归测试 + 监控（改了 Prompt 有没有搞坏别的东西？）
# 本模块覆盖前三层（冒烟测试 / 行为验证 / 回归测试），第 4 层见 monitoring.py。
import json


# ============================================================
# 层次 1：冒烟测试——能跑就行
# ============================================================
class SmokeTest:
    """烟雾测试：能跑就行"""

    TEST_CASES = [
        {
            "name": "简单问候",
            "input": "你好",
            "check": lambda r: len(r) > 0  # 有回复就行
        },
        {
            "name": "天气查询",
            "input": "北京今天天气怎么样？",
            "check": lambda r: "温度" in r or "天气" in r or "°" in r
        },
        {
            "name": "无需工具的简单问题",
            "input": "1+1等于几？",
            "check": lambda r: "2" in r
        },
        {
            "name": "多步任务",
            "input": "帮我查北京和上海今天天气，对比一下哪个更热",
            "check": lambda r: len(r) > 30
        },
    ]

    def run(self, agent) -> dict:
        results = {"passed": 0, "failed": 0, "details": []}

        for case in self.TEST_CASES:
            try:
                response = agent.chat(case["input"])
                passed = case["check"](response)
                status = "✅" if passed else "❌"

                results["details"].append({
                    "name": case["name"],
                    "status": status,
                    "response_preview": response[:100]
                })

                if passed:
                    results["passed"] += 1
                else:
                    results["failed"] += 1
            except Exception as e:
                results["details"].append({
                    "name": case["name"],
                    "status": "💥",
                    "error": str(e)
                })
                results["failed"] += 1

        return results


# ============================================================
# 层次 2：行为验证——回答对了吗（用 LLM 做裁判）
# ============================================================
class BehaviorTest:
    """行为验证：回答对了吗"""

    def __init__(self, llm_client):
        self.judge = llm_client  # 用 LLM 做裁判

    def run_test_case(self, agent, test_case: dict) -> dict:
        """
        test_case 格式:
        {
            "name": "天气查询准确性",
            "input": "北京今天多少度？",
            "expected_behaviors": [
                "回复中应该包含具体温度数字",
                "应该明确提到了北京",
                "不应该说'我不知道'"
            ],
            "forbidden_behaviors": [
                "不应该查询其他城市",
                "不应该输出原始 API 数据"
            ]
        }
        """
        # 1. 让 Agent 回答
        response = agent.chat(test_case["input"])

        # 2. 让裁判 LLM 评估
        judge_prompt = f"""你是一个 Agent 评估裁判。请根据以下标准评估 Agent 的回复。

用户问题: {test_case['input']}

Agent 回复:
```

{response}

```
期望行为（每条都要满足）:
{chr(10).join(f"- {b}" for b in test_case['expected_behaviors'])}

禁止行为（出现任何一条就算失败）:
{chr(10).join(f"- {b}" for b in test_case.get('forbidden_behaviors', []))}

请输出 JSON 格式的评估结果:
{{
    "pass": true/false,
    "score": 0-100,
    "reason": "一句话说明通过或失败的原因",
    "issues": ["问题1", "问题2"]
}}
"""
        judge_response = self.judge.chat.completions.create(
            model="gpt-4o-mini",  # 评估用便宜的模型就行
            messages=[{"role": "user", "content": judge_prompt}],
            response_format={"type": "json_object"}
        )

        result = json.loads(judge_response.choices[0].message.content)

        return {
            "name": test_case["name"],
            "pass": result["pass"],
            "score": result["score"],
            "reason": result["reason"],
            "response_preview": response[:200]
        }

    def run_suite(self, agent, test_cases: list[dict]) -> dict:
        total_pass = 0
        total_score = 0
        details = []

        for case in test_cases:
            result = self.run_test_case(agent, case)
            details.append(result)
            if result["pass"]:
                total_pass += 1
            total_score += result["score"]

        return {
            "total": len(test_cases),
            "passed": total_pass,
            "pass_rate": f"{total_pass / len(test_cases) * 100:.1f}%",
            "avg_score": total_score / len(test_cases),
            "details": details
        }


# ============================================================
# 层次 3：回归测试——改了 Prompt 有没有搞坏旧的？
# ============================================================
class RegressionTestSuite:
    """回归测试套件：确保新改动不会破坏已有功能"""

    def __init__(self):
        self.suites = {}  # 按功能模块组织的测试

    def add_suite(self, module_name: str, test_cases: list[dict]):
        self.suites[module_name] = test_cases

    def run_all(self, agent) -> dict:
        """跑全量回归"""
        all_results = {}

        for module, cases in self.suites.items():
            bt = BehaviorTest(agent.llm.client)
            results = bt.run_suite(agent, cases)
            all_results[module] = results

        # 计算总体指标
        total = sum(r["total"] for r in all_results.values())
        passed = sum(r["passed"] for r in all_results.values())

        return {
            "total": total,
            "passed": passed,
            "pass_rate": f"{passed / total * 100:.1f}%" if total > 0 else "N/A",
            "by_module": all_results
        }


if __name__ == "__main__":
    # 构建回归测试套件
    suite = RegressionTestSuite()

    # 天气模块的回归测试
    suite.add_suite("weather", [
        {
            "name": "单城市天气查询",
            "input": "北京今天天气怎么样？",
            "expected_behaviors": ["应该包含温度", "应该提到北京"],
            "forbidden_behaviors": ["不应该说不知道"]
        },
        {
            "name": "多城市对比",
            "input": "北京和上海哪个更热？",
            "expected_behaviors": ["应该包含两个城市的温度", "应该给出对比结论"],
            "forbidden_behaviors": ["不应该只查一个城市"]
        },
        {
            "name": "带提醒的天气查询",
            "input": "明天上海下雨吗？如果需要带伞提醒我",
            "expected_behaviors": ["应该查询明天天气", "应该判断是否需要带伞"],
            "forbidden_behaviors": ["不应该查询今天天气"]
        },
    ])

    # 邮件模块的回归测试
    suite.add_suite("email", [
        {
            "name": "发送简单邮件",
            "input": "给xiaowang@company.com发邮件，标题'测试'，内容'这是一封测试邮件'",
            "expected_behaviors": ["应该确认邮件已发送"],
            "forbidden_behaviors": ["不应该说没有邮箱权限就放弃"]
        },
    ])

    # 每次改完 Prompt 跑一次：
    # results = suite.run_all(agent)
    # print(f"回归测试通过率: {results['pass_rate']}")
