# v14：动态工具/技能插件化

## 本版目标

到 v13 为止，`tool_registry` 是一次性在 `build_default_tool_registry()` 里构建好、之后只会被"删除"（循环检测禁用工具）不会被"新增"的静态集合。这一版让工具可以在运行时动态注册——更接近真实世界里"Agent 发现并加载一个新技能/插件"的场景，同时证明 v6 的输出校验和 v11 的权限检查完全不需要因为"多了一个新工具"而改动一行代码。

## 新增/修改文件（对照 v13）

- 新增 `harness/tool_registry.py`：`ToolRegistry(dict)`，新增 `register(tool)`/`unregister(name)` 两个方法，其余行为完全是普通 `dict`。
- 修改 `tools.py`：`build_default_tool_registry()` 返回 `ToolRegistry` 实例而不是普通 `dict`；新增 `load_plugin(plugin_name)` 工具（调用后把 `weather_lookup` 动态注册进 registry）和 `weather_lookup(city)` 工具本身（默认不在注册表里，只有加载插件后才存在）。
- 修改 `scenarios.py`：新增 `plugin_then_use`（先加载插件、再调用新工具）。
- 修改 `main.py`：`--scenario` 增加 `plugin_then_use`。
- 其余文件（`mock_llm.py`、`harness/loop.py` 及其余 `harness/` 子模块、`evals.py`）与 v13 完全一致——本版本不修改核心循环。

## 核心设计

**为什么 `ToolRegistry` 直接继承 `dict`，而不是包一层自己实现 `__getitem__`/`__delitem__`/`__contains__`**：v1~v13 所有代码（`harness/loop.py`、`harness/validator.py`、`harness/permissions.py`）都是用最朴素的 dict 语法操作 `tool_registry` 的——下标取值、`del`、`in`、`.keys()`。直接继承 `dict` 能免费获得这些行为的完整实现，不需要手写、也不需要担心漏实现某个魔术方法导致行为不一致；`register`/`unregister` 只是在这基础上加两个语义更清晰的方法名。

**为什么 `load_plugin` 能拿到 `registry` 自身的引用**：`load_plugin` 和 `read_file`/`write_file` 一样是 `build_default_tool_registry()` 内部定义的闭包，天然能访问同一个函数作用域里的 `registry` 变量——不需要额外的依赖注入机制，这是 Python 闭包最自然的用法。

**为什么 `weather_lookup` 不在初始注册表里、必须先 `load_plugin` 才能用**：如果 `weather_lookup` 一开始就在注册表里，"动态注册"这件事就无从谈起——本版本要证明的核心命题是"运行时新增的工具，校验和权限层不需要预先知道它的存在"，`weather_lookup` 必须真的在运行时才出现，这个证明才有意义。

## 如何运行 demo

```bash
python3 main.py --scenario plugin_then_use   # 先加载 weather 插件，再调用 weather_lookup
```

## 局限性

`load_plugin` 里"可加载的插件有哪些"是硬编码在函数内部的一个小字典（目前只有 `weather`），不是真正的"从外部文件系统/网络发现插件"这种动态发现机制——本版本只演示"注册表本身支持运行时增删"这个核心能力，真实的插件发现/加载机制（比如按约定扫描一个目录、或者对接 MCP 协议）超出本版本范围。另外，`unregister` 目前没有任何调用点使用（没有场景演示"运行时卸载一个工具"），只是为了让 `ToolRegistry` 的接口在语义上完整（有 register 就该有对应的 unregister）。
