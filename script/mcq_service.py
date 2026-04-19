from pathlib import Path
from typing import Callable, Awaitable
import re

from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context, StarTools
from astrbot.core.agent.tool import ToolSet

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
    "你是 Minecraft 模组与整合包分析助手。"
    "你必须先通过路径工具获取需要参照的文件路径。"
    "拿到路径后，优先使用默认 Agent 执行器已有工具进行后续读取/检索/分析。"
    "如本地信息不足，可调用默认网络搜索工具补充版本兼容性、模组信息与已知问题。"
    "回答请结构化输出：简短说明，证据，解释说明。"
    "不要编造未在工具结果中出现的文件内容。"
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
        )
        return llm_resp.completion_text or "分析完成，但未返回有效内容。"

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
        # 以默认工具集为基础，保留系统已有执行能力，再补充路径提示工具。
        toolset = context.get_llm_tool_manager().get_full_tool_set()

        toolset.add_tool(ListServerDataFilesTool(bind_dir=str(bind_dir)))
        toolset.add_tool(ReadServerDataFileTool(bind_dir=str(bind_dir)))
        toolset.add_tool(SearchServerDataTool(bind_dir=str(bind_dir)))

        return toolset
