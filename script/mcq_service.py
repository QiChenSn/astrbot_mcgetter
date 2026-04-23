from pathlib import Path
from typing import Callable, Awaitable
import re
import time

from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context, StarTools
from astrbot.core.agent.tool import ToolSet
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.api import logger

from .json_operate import get_all_servers
from .mcq_tools import (
    ListServerDataFilesTool,
    ReadServerDataFileTool,
    SearchServerDataTool,
)


DATA_DIR = Path(StarTools.get_data_dir("astrbot_mcgetter"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_USER_QUESTION = "分析kubejs主要进行了哪些修改"
DEFAULT_SYSTEM_PROMPT = (
    "你是 Minecraft 模组整合包分析专家，擅长 Forge/NeoForge 生态、KubeJS 脚本与模组源码阅读。"
    "分析时必须遵循工具优先原则：先用工具读取本地绑定数据（mods、kubejs、配置文件）再下结论。"
    "你必须先调用路径工具定位相关文件，再使用读取/检索工具提取证据。"
    "对于 mod 级分析（机制实现、事件注入、Mixin/Hooks、关键配置含义），在本地证据基础上优先调用 GitHub 查询源码工具进行交叉验证。"
    "如仍不足，再使用其他网络搜索工具补充版本兼容性、已知问题与社区文档。"
    "严禁无依据猜测；不要编造未在工具结果中出现的内容。"
    "回答请结构化输出：结论摘要、证据（文件路径/源码线索）、分析过程、风险与不确定性。"
)


class McqService:
    async def ask(
        self,
        event: AstrMessageEvent,
        context: Context,
        get_json_path: Callable[[str], Awaitable[Path]],
    ) -> str:
        group_id = event.get_group_id()
        if not group_id:
            return "请在群聊中使用 /mcq 指令"

        server_id, question = self._parse_args(event.message_str)
        if not server_id:
            return "用法：/mcq 服务器ID [提示词]"

        if not re.fullmatch(r"\d+", server_id):
            return "服务器ID必须为数字"

        json_path = await get_json_path(group_id)
        servers = await get_all_servers(json_path)
        if server_id not in servers:
            return f"未找到服务器ID {server_id}"

        bind_dir = DATA_DIR / f"{group_id}_{server_id}"
        mods_dir = bind_dir / "mods"
        kubejs_dir = bind_dir / "kubejs"
        if not mods_dir.exists() and not kubejs_dir.exists():
            return f"服务器 {server_id} 尚未绑定数据文件，请先使用 /mcbind {server_id}"

        question = question or DEFAULT_USER_QUESTION
        provider_id = await context.get_current_chat_provider_id(event.unified_msg_origin)

        tools = self._build_tools(bind_dir, context)
        trace_hooks = _McqToolTraceHooks()
        start_ts = time.perf_counter()

        prompt = (
            f"群号: {group_id}\n"
            f"服务器ID: {server_id}\n"
            f"绑定目录: {bind_dir}\n"
            f"用户问题: {question}\n"
            "请先调用工具检查相关文件后再回答。"
        )

        llm_resp = await context.tool_loop_agent(
            event=event,
            chat_provider_id=provider_id,
            prompt=prompt,
            tools=tools,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            max_steps=25,
            tool_call_timeout=120,
            agent_hooks=trace_hooks,
        )
        elapsed = time.perf_counter() - start_ts
        answer = llm_resp.completion_text or "分析完成，但未返回有效内容。"
        used_tools = ", ".join(trace_hooks.tool_names) if trace_hooks.tool_names else "无"
        return (
            f"{answer}\n\n"
            f"---\n"
            f"耗时: {elapsed:.2f}s\n"
            f"工具调用: {used_tools}"
        )

    def _parse_args(self, message_str: str) -> tuple[str, str]:
        text = str(message_str or "").strip()
        if not text:
            return "", ""

        parts = text.split()
        if not parts:
            return "", ""

        if parts[0].lstrip("/").lower() == "mcq":
            parts = parts[1:]

        if not parts:
            return "", ""

        server_id = parts[0]
        question = " ".join(parts[1:]).strip()
        return server_id, question

    def _build_tools(self, bind_dir: Path, context: Context) -> ToolSet:
        # get_full_tool_set 仅包含插件/MCP工具，不含 AstrBot 内置工具。
        # 这里显式合并 builtin，确保拿到系统自带能力（如搜索/文件等）。
        tmgr = context.get_llm_tool_manager()
        toolset = ToolSet()

        full_toolset = tmgr.get_full_tool_set()
        for tool in full_toolset:
            if getattr(tool, "active", True):
                toolset.add_tool(tool)

        builtin_tools = tmgr.iter_builtin_tools()
        for builtin_tool in builtin_tools:
            if getattr(builtin_tool, "active", True):
                toolset.add_tool(builtin_tool)

        logger.debug(
            "mcq 可用工具统计: full=%s, builtin=%s, merged=%s",
            len(full_toolset.tools),
            len(tmgr.iter_builtin_tools()),
            len(toolset.tools),
        )

        # 永远提供路径索引工具，帮助 Agent 锁定分析范围。
        toolset.add_tool(ListServerDataFilesTool(bind_dir=str(bind_dir)))

        # 优先依赖 AstrBot 内置读取工具；若内置读取能力缺失，再启用插件读取兜底。
        has_builtin_file_read = toolset.get_tool("astrbot_file_read_tool") is not None
        if not has_builtin_file_read:
            toolset.add_tool(ReadServerDataFileTool(bind_dir=str(bind_dir)))
            toolset.add_tool(SearchServerDataTool(bind_dir=str(bind_dir)))
            logger.warning("mcq 未检测到 astrbot_file_read_tool，已启用插件读取兜底工具")

        return toolset


class _McqToolTraceHooks(BaseAgentRunHooks):
    def __init__(self) -> None:
        self.tool_names: list[str] = []

    async def on_tool_start(self, run_context, tool, tool_args) -> None:
        name = getattr(tool, "name", "")
        if name and name not in self.tool_names:
            self.tool_names.append(name)
