"""调用格式/协议正确性评测（文章五）——用 pydantic 把工具参数 schema 写死。

参数"填了"不等于"填对了、能被解析"。

坑 4：把"协议正确"当成"语义正确"。schema 校验通过，只代表"参数能被解析"，
不代表"参数值对"——`group_id="ops_team"` 能通过 schema 校验，但它可能是错的。
别用 pydantic 校验替代语义断言（那是 test_tool_selection.py 的活儿），两者是两层。
"""

import pytest
from pydantic import BaseModel, Field, ValidationError

from trace import run_agent_with_calls


class QueryOrdersArgs(BaseModel):
    start: str = Field(..., min_length=8)   # 日期字符串，至少 8 位
    end: str = Field(..., min_length=8)


class SendMessageArgs(BaseModel):
    group_id: str
    content: str = Field(..., min_length=1)


# 工具名 → 参数 schema 的映射
SCHEMAS = {
    "query_orders": QueryOrdersArgs,
    "send_message": SendMessageArgs,
}


def test_calls_are_parseable():
    calls = run_agent_with_calls("生成本周销售周报，发送到销售团队群")["calls"]
    for c in calls:
        schema = SCHEMAS.get(c["tool"])
        if not schema:
            continue
        try:
            schema(**c["args"])
        except ValidationError as e:
            pytest.fail(f"工具 {c['tool']} 的参数不符合 schema: {e}")
