from pathlib import Path
from typing import Any
import os

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


MAX_LIST_ITEMS = 500
MAX_SEARCH_RESULTS = 80


@dataclass
class ListServerDataFilesTool(FunctionTool[AstrAgentContext]):
    """列出绑定目录下 mods/kubejs 内的文件。"""

    name: str = "list_server_data_files"
    description: str = (
        "List files under mods/kubejs in the bound server data directory. "
        "Use this first before reading files."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "subdir": {
                    "type": "string",
                    "description": "Which subdir to list: all/mods/kubejs. Default all.",
                },
                "keyword": {
                    "type": "string",
                    "description": "Optional filename keyword filter.",
                },
            },
            "required": [],
        }
    )
    bind_dir: str = ""

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        base = Path(self.bind_dir)
        if not base.exists():
            return "绑定目录不存在。"

        subdir = str(kwargs.get("subdir", "all")).strip().lower() or "all"
        keyword = str(kwargs.get("keyword", "")).strip().lower()
        if subdir not in {"all", "mods", "kubejs"}:
            subdir = "all"

        targets = []
        if subdir in {"all", "mods"}:
            targets.append(base / "mods")
        if subdir in {"all", "kubejs"}:
            targets.append(base / "kubejs")

        files: list[str] = []
        for target in targets:
            if not target.exists():
                continue
            for root, _, filenames in os.walk(target):
                for filename in filenames:
                    full = Path(root) / filename
                    rel = full.relative_to(base).as_posix()
                    if keyword and keyword not in rel.lower():
                        continue
                    files.append(rel)
                    if len(files) >= MAX_LIST_ITEMS:
                        break
                if len(files) >= MAX_LIST_ITEMS:
                    break
            if len(files) >= MAX_LIST_ITEMS:
                break

        if not files:
            return "未找到匹配文件。"

        files.sort()
        body = "\n".join(files)
        return f"共找到 {len(files)} 个文件（最多展示 {MAX_LIST_ITEMS}）：\n{body}"


@dataclass
class ReadServerDataFileTool(FunctionTool[AstrAgentContext]):
    """将相对路径解析为绑定目录下可参考的绝对路径。"""

    name: str = "read_server_data_file"
    description: str = (
        "Resolve a relative file path under mods/kubejs into an absolute path. "
        "Only returns path reference, does not read file content."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "relative_path": {
                    "type": "string",
                    "description": "Required. Relative path under bind dir, such as kubejs/server_scripts/example.js",
                },
            },
            "required": ["relative_path"],
        }
    )
    bind_dir: str = ""

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        rel = str(kwargs.get("relative_path", "")).strip().replace("\\", "/")
        if not rel:
            return "relative_path 不能为空。"

        base = Path(self.bind_dir).resolve()
        target = (base / rel).resolve()

        try:
            if os.path.commonpath([str(base), str(target)]) != str(base):
                return "非法路径：越界访问被拒绝。"
        except Exception:
            return "非法路径。"

        if not target.exists() or not target.is_file():
            return "文件不存在。"

        parts = [p.lower() for p in target.relative_to(base).parts]
        if not parts or parts[0] not in {"mods", "kubejs"}:
            return "只允许读取 mods 或 kubejs 下的文件。"

        return (
            f"可参考文件路径:\n"
            f"relative: {target.relative_to(base).as_posix()}\n"
            f"absolute: {str(target)}"
        )


@dataclass
class SearchServerDataTool(FunctionTool[AstrAgentContext]):
    """按文件名/路径关键词检索参考文件路径（不读取内容）。"""

    name: str = "search_server_data"
    description: str = "Search candidate file paths by filename/path keyword under mods/kubejs."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Required. Keyword to match file path, e.g. script, recipe, event, quest.",
                },
                "subdir": {
                    "type": "string",
                    "description": "Optional: all/mods/kubejs. Default all.",
                },
            },
            "required": ["query"],
        }
    )
    bind_dir: str = ""

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        query = str(kwargs.get("query", "")).strip()
        if not query:
            return "query 不能为空。"

        subdir = str(kwargs.get("subdir", "all")).strip().lower() or "all"
        if subdir not in {"all", "mods", "kubejs"}:
            subdir = "all"

        base = Path(self.bind_dir)
        if not base.exists():
            return "绑定目录不存在。"

        targets = []
        if subdir in {"all", "mods"}:
            targets.append(base / "mods")
        if subdir in {"all", "kubejs"}:
            targets.append(base / "kubejs")

        results: list[str] = []
        q_lower = query.lower()
        for target in targets:
            if not target.exists():
                continue
            for root, _, filenames in os.walk(target):
                for filename in filenames:
                    fp = Path(root) / filename
                    rel = fp.relative_to(base).as_posix()
                    if q_lower in rel.lower():
                        rel = fp.relative_to(base).as_posix()
                        results.append(rel)
                        if len(results) >= MAX_SEARCH_RESULTS:
                            break
                if len(results) >= MAX_SEARCH_RESULTS:
                    break
            if len(results) >= MAX_SEARCH_RESULTS:
                break

        if not results:
            return "未检索到匹配内容。"

        body = "\n".join(results)
        return f"共命中 {len(results)} 个文件（最多展示 {MAX_SEARCH_RESULTS}）：\n{body}"
