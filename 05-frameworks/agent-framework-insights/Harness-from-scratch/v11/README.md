# v11：安全权限沙箱

## 本版目标

到 v10 为止，Harness 会执行模型要求的任何工具调用，不管这个操作有多危险。这一版加入一个简单的权限规则引擎：每个工具可以配置成 `allow`（放行）、`ask`（需要审批）、`deny`（禁止）三种状态之一，在真正执行之前拦截。

## 新增/修改文件（对照 v10）

- 新增 `harness/permissions.py`：`check_permission(call, policy)`，未配置的工具默认 `"allow"`。
- 修改 `tools.py`：新增一个危险工具 `delete_all_files`（清空内存态文件系统），用来演示 `deny` 规则。
- 修改 `harness/loop.py`：`run_agent()` 新增 `permission_policy`（字典，默认空）和 `approve_fn`（回调，默认是一个基于 `input()` 的真实终端询问函数）两个参数。校验通过之后、熔断检查之前，先做一次权限过滤：`deny` 直接拦截；`ask` 调用 `approve_fn(call)`，返回假就同样拦截。
- 修改 `scenarios.py`：新增 `ask_then_approved`、`ask_then_denied`、`deny_dangerous_tool` 三个场景。
- 修改 `main.py`：新增 `DEFAULT_PERMISSION_POLICY`（`write_file` 设为 `ask`，`delete_all_files` 设为 `deny`）。
- 其余文件（`mock_llm.py`、`harness/budget.py`、`harness/loop_detector.py`、`harness/context_manager.py`、`harness/validator.py`、`harness/errors.py`、`harness/retry.py`、`harness/session_store.py`）与 v10 完全一致。

## 核心设计

**为什么 `approve_fn` 是普通同步函数，不是 `async def`**：审批本质上是一个"询问外部世界一个是/否问题"的动作，在 CLI 场景里就是阻塞地等待用户输入；把它做成同步函数反而更贴近真实语义（人不会"并发"地回答审批问题），也让测试更容易写（传一个确定性的 lambda，不需要处理协程）。

**为什么权限检查放在校验通过之后、熔断检查之前**：一个调用如果连基本格式都不对（未知工具/缺参数），根本不需要问"要不要批准"；而权限判断是"这个操作本身是否被允许"，这个问题应该先于"这个工具最近是不是老出问题"（熔断）被回答——即使一个工具从没失败过，只要策略上不允许，也不该被执行。

**为什么 `deny` 不经过 `approve_fn`**：`deny` 表示"这类操作在任何情况下都不该被执行"，是比"需要人工确认"更强的约束，不应该给模型或审批者任何绕过的机会。

## 如何运行 demo

```bash
python3 main.py --scenario ask_then_approved     # 需要在终端手动输入 y 批准
python3 main.py --scenario ask_then_denied       # 手动输入 n（或直接回车）拒绝，模型换策略完成任务
python3 main.py --scenario deny_dangerous_tool   # 危险操作被直接拦截，不会有任何询问
```

## 局限性

权限策略是一个扁平的 `{工具名: 规则}` 字典，无法根据参数内容做更细粒度的判断（比如"写入 `/tmp` 下的文件允许，写入其它路径需要审批"），也没有路径白名单/黑名单这类更精细的规则表达能力。`approve_fn` 的默认实现是阻塞式的 `input()`，如果同一轮里有多个都需要审批的调用，会一个接一个地依次询问，不会并发弹出多个审批请求——这是因为审批过滤发生在进入 `asyncio.gather` 之前的顺序阶段，和"真正执行的并发"是两个不同的关注点。

至此，v8~v11 这一批工业级扩展全部完成。v12~v15（可观测性与成本核算、自动化评估框架、动态工具/技能插件化、多智能体协作）将在下一批计划中规划。
