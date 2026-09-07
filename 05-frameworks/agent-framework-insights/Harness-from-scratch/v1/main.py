import argparse

from harness.loop import run_agent
from mock_llm import MockLLM, ScriptExhausted
from scenarios import get_scenario
from tools import build_default_tool_registry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, choices=["happy_path", "runaway"])
    args = parser.parse_args()

    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry()

    try:
        result = run_agent(goal, tool_registry, llm)
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")


if __name__ == "__main__":
    main()
