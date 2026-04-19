from pathlib import Path
from typing import Dict, Any, Callable, Awaitable, Optional, List
import os
import time
import shutil
import zipfile
import re
from urllib.parse import urlparse

from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import StarTools
import astrbot.core.message.components as Comp
from astrbot.core.utils.io import download_file

from .json_operate import get_all_servers


DATA_DIR = Path(StarTools.get_data_dir("astrbot_mcgetter"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
REQUEST_TIMEOUT_SECONDS = 120


class McBindService:
    """处理 /mcbind 绑定请求与文件上传解压逻辑。"""

    def __init__(self) -> None:
        self.bind_requests: Dict[str, Dict[str, Any]] = {}

    async def begin_bind(
        self,
        event: AstrMessageEvent,
        server_id: str,
        get_json_path: Callable[[str], Awaitable[Path]],
    ) -> str:
        group_id = event.get_group_id()
        if not group_id:
            return "请在群聊中使用 /mcbind 指令"

        if not re.fullmatch(r"\d+", str(server_id)):
            return "服务器ID必须为数字"

        json_path = await get_json_path(group_id)
        servers = await get_all_servers(json_path)
        if str(server_id) not in servers:
            return f"未找到服务器ID {server_id}"

        request_key = f"{group_id}-{event.get_sender_id()}"
        self.bind_requests[request_key] = {
            "timestamp": time.time(),
            "group_id": str(group_id),
            "server_id": str(server_id),
            "last_non_file_message_id": "",
        }

        return (
            f"已开始绑定服务器 {server_id}。请在{REQUEST_TIMEOUT_SECONDS}秒内上传 .zip 文件"
            "（必须包含 mods 或 kubejs 文件夹）。"
        )

    async def handle_file_message(
        self,
        event: AstrMessageEvent,
        get_json_path: Callable[[str], Awaitable[Path]],
    ) -> Optional[str]:
        group_id = event.get_group_id()
        if not group_id:
            return None

        user_id = event.get_sender_id()
        request_key = f"{group_id}-{user_id}"
        if request_key not in self.bind_requests:
            return None

        request = self.bind_requests[request_key]
        if time.time() - request.get("timestamp", 0) > REQUEST_TIMEOUT_SECONDS:
            del self.bind_requests[request_key]
            return "/mcbind 已超时，请重新发送指令后再上传文件"

        messages = event.get_messages() or []
        if not messages and getattr(event, "message_obj", None):
            messages = getattr(event.message_obj, "message", []) or []

        file_component = None
        for message in messages:
            if self._is_file_component(message):
                file_component = message
                break

        if not file_component:
            if not self._is_new_user_message(event, request):
                return None
            return "未检测到可处理的文件消息，请直接上传 .zip 文件"

        server_id = str(request.get("server_id"))

        # 上传时再次检查服务器ID是否仍存在
        json_path = await get_json_path(group_id)
        servers = await get_all_servers(json_path)
        if server_id not in servers:
            del self.bind_requests[request_key]
            return f"服务器ID {server_id} 已不存在，请重新选择后执行 /mcbind"

        bind_dir = DATA_DIR / f"{group_id}_{server_id}"
        temp_dir = DATA_DIR / "_uploads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_zip_path = temp_dir / f"{group_id}_{server_id}_{int(time.time())}.zip"

        try:
            file_name = str(getattr(file_component, "name", "") or "")
            file_location = await file_component.get_file(allow_return_url=True)

            if not file_name and isinstance(file_location, str) and file_location:
                parsed = urlparse(file_location)
                file_name = os.path.basename(parsed.path)

            if not file_name.lower().endswith(".zip"):
                del self.bind_requests[request_key]
                return "仅支持上传 .zip 文件，例如 a.zip"

            if not isinstance(file_location, str) or not file_location:
                del self.bind_requests[request_key]
                return "无法获取上传文件，请重新上传"

            if file_location.startswith("http"):
                await download_file(file_location, str(temp_zip_path))
            else:
                source_path = Path(file_location)
                if not source_path.exists():
                    del self.bind_requests[request_key]
                    return "文件不存在或已失效，请重新上传"
                shutil.copyfile(source_path, temp_zip_path)

            if not temp_zip_path.exists():
                del self.bind_requests[request_key]
                return "文件下载失败，请重新上传"

            with zipfile.ZipFile(temp_zip_path, "r") as zf:
                infos = zf.infolist()
                has_mods, has_kubejs = self._contains_required_dirs(infos)
                if not has_mods and not has_kubejs:
                    del self.bind_requests[request_key]
                    return "zip 内必须至少包含 mods 或 kubejs 文件夹之一"

                if (bind_dir / "mods").exists():
                    shutil.rmtree(bind_dir / "mods", ignore_errors=True)
                if (bind_dir / "kubejs").exists():
                    shutil.rmtree(bind_dir / "kubejs", ignore_errors=True)

                extracted_any = self._extract_allowed_paths(zf, infos, bind_dir)
                if not extracted_any:
                    del self.bind_requests[request_key]
                    return "zip 中未找到可解压的 mods/kubejs 内容"

            del self.bind_requests[request_key]
            return f"绑定成功：已写入 {bind_dir}"
        except zipfile.BadZipFile:
            if request_key in self.bind_requests:
                del self.bind_requests[request_key]
            return "上传文件不是有效的 zip 压缩包"
        except Exception as e:
            if request_key in self.bind_requests:
                del self.bind_requests[request_key]
            return "处理上传文件时发生错误:" + str(e)
        finally:
            if temp_zip_path.exists():
                try:
                    temp_zip_path.unlink()
                except Exception:
                    pass

    def _contains_required_dirs(self, infos: List[zipfile.ZipInfo]) -> tuple[bool, bool]:
        has_mods = False
        has_kubejs = False
        for info in infos:
            parts = [p for p in info.filename.replace("\\", "/").split("/") if p and p != "."]
            lowered = [p.lower() for p in parts]
            if "mods" in lowered:
                has_mods = True
            if "kubejs" in lowered:
                has_kubejs = True
        return has_mods, has_kubejs

    def _extract_allowed_paths(
        self,
        zf: zipfile.ZipFile,
        infos: List[zipfile.ZipInfo],
        bind_dir: Path,
    ) -> bool:
        extracted_any = False
        target_root = bind_dir.resolve()

        for info in infos:
            raw_parts = [p for p in info.filename.replace("\\", "/").split("/") if p and p != "."]
            if not raw_parts:
                continue

            lowered_parts = [p.lower() for p in raw_parts]
            folder_index = -1
            folder_name = ""
            for idx, part in enumerate(lowered_parts):
                if part in ("mods", "kubejs"):
                    folder_index = idx
                    folder_name = part
                    break

            if folder_index < 0:
                continue

            relative_parts = [folder_name] + raw_parts[folder_index + 1:]
            destination = target_root.joinpath(*relative_parts)
            resolved_destination = destination.resolve()

            if os.path.commonpath([str(target_root), str(resolved_destination)]) != str(target_root):
                continue

            if info.is_dir():
                resolved_destination.mkdir(parents=True, exist_ok=True)
                extracted_any = True
                continue

            resolved_destination.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(resolved_destination, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted_any = True

        return extracted_any

    def _is_file_component(self, message: Any) -> bool:
        if isinstance(message, Comp.File):
            return True

        msg_type = getattr(message, "type", None)
        if msg_type is None:
            return False

        msg_type_text = str(msg_type).strip().lower()
        if msg_type_text in {"file", "componenttype.file"}:
            return True

        msg_type_name = str(getattr(msg_type, "name", "")).strip().lower()
        msg_type_value = str(getattr(msg_type, "value", "")).strip().lower()
        if msg_type_name == "file" or msg_type_value == "file":
            return True

        return hasattr(message, "get_file") and hasattr(message, "name")

    def _is_new_user_message(self, event: AstrMessageEvent, request: Dict[str, Any]) -> bool:
        """仅在监听用户发来新的消息时触发非文件提示。"""
        current_message_id = str(getattr(event.message_obj, "message_id", "") or "")
        if not current_message_id:
            return False

        last_message_id = str(request.get("last_non_file_message_id", "") or "")
        if current_message_id == last_message_id:
            return False

        request["last_non_file_message_id"] = current_message_id
        return True
