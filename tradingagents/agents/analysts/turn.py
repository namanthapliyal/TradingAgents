"""One turn of a tool-using analyst, and its last turn once its tool rounds are spent."""

import json
import re

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

WRAP_UP = (
    "You have used every tool round this report allows. Write your final report "
    "now from the tool results above, and say which data you could not retrieve."
)


def _extract_text_tool_calls(content: str, tools) -> list[dict]:
    """Parse JSON tool calls that smaller/local models emit in message content.

    Local models (e.g. Ollama with Qwen or Llama) frequently output tool calls
    as raw JSON or inside markdown code blocks instead of native API tool_calls.
    Extracting them here allows LangGraph's ToolNode to execute them seamlessly.
    """
    if not isinstance(content, str) or not content.strip():
        return []

    valid_names = {t.name if hasattr(t, "name") else getattr(t, "__name__", str(t)) for t in tools}
    text = content.strip()
    calls = []

    # 1. Direct JSON parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get("name") in valid_names:
            args = obj.get("arguments") or obj.get("args") or obj.get("parameters") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            return [{"name": obj["name"], "args": args, "id": "call_0", "type": "tool_call"}]
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, dict) and item.get("name") in valid_names:
                    args = item.get("arguments") or item.get("args") or item.get("parameters") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    calls.append(
                        {"name": item["name"], "args": args, "id": f"call_{i}", "type": "tool_call"}
                    )
            if calls:
                return calls
    except Exception:
        pass

    # 2. Markdown fence search: ```json ... ``` or ``` ... ```
    matches = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    for i, m in enumerate(matches):
        try:
            obj = json.loads(m)
            if isinstance(obj, dict) and obj.get("name") in valid_names:
                args = obj.get("arguments") or obj.get("args") or obj.get("parameters") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                calls.append(
                    {"name": obj["name"], "args": args, "id": f"call_{i}", "type": "tool_call"}
                )
        except Exception:
            pass

    return calls


def take_turn(prompt, llm, tools, messages):
    """The analyst's reply and its report, which stays empty while it calls tools.

    Told to wrap up, it answers without tools: a model offered tools may call one
    whatever it is told. Its earlier calls and their results reach it as text,
    since a provider may refuse a history holding tool calls when none are bound.
    """
    if messages and isinstance(messages[-1], HumanMessage) and messages[-1].content == WRAP_UP:
        # The prompt lists the tools it offers; a model told of tools it cannot
        # call may still try, and some providers then answer with nothing.
        prompt = prompt.partial(tool_names="none; your tool rounds are spent")
        result = (prompt | llm).invoke(_as_text(messages))
        return result, result.content
    result = (prompt | llm.bind_tools(tools)).invoke(messages)
    if not getattr(result, "tool_calls", None) and hasattr(result, "content") and result.content:
        parsed_calls = _extract_text_tool_calls(result.content, tools)
        if parsed_calls:
            result.tool_calls = parsed_calls
    # If the analyst has tools, but produced NO tool calls and has not yet received
    # any tool results in messages (Turn 1), do not allow it to terminate with a hallucinated
    # free-text report. Force an initial tool call to the primary tool.
    if tools and not getattr(result, "tool_calls", None):
        has_tool_results = any(isinstance(m, ToolMessage) for m in messages)
        if not has_tool_results:
            primary_tool = tools[0]
            tool_name = (
                primary_tool.name
                if hasattr(primary_tool, "name")
                else getattr(primary_tool, "__name__", str(primary_tool))
            )
            result.tool_calls = [
                {"name": tool_name, "args": {}, "id": "call_turn1_0", "type": "tool_call"}
            ]
    return result, "" if result.tool_calls else result.content


def _as_text(messages):
    """The history with its tool calls and tool results written out as plain messages."""
    written = []
    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            said = message.content if isinstance(message.content, str) else ""
            calls = "; ".join(
                f"{c['name']}({json.dumps(c['args'], default=str)})" for c in message.tool_calls
            )
            written.append(AIMessage(content=f"{said}\n[Called {calls}]".strip()))
        elif isinstance(message, ToolMessage):
            written.append(
                HumanMessage(content=f"[{message.name or 'Tool'} returned]\n{message.content}")
            )
        else:
            written.append(message)
    return written
