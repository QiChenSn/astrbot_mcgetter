from typing import List, Optional, Dict, Any
from pathlib import Path
import astrbot.core.message.components as Comp
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from .script.get_server_info import get_server_status
from .script.template_selector import write_config, get_img
from .script.mcbind_service import McBindService
from .script.mcq_service import McqService
from .script.json_operate import (
    read_json, add_data, del_data, update_data, 
    get_all_servers, get_server_info, get_server_by_name,
    update_server_status, auto_cleanup_servers
)
import asyncio
import re
from datetime import datetime
from time import localtime, strftime

# 常量定义
HELP_INFO = """
/mchelp 
--查看帮助

/mc   
--查询保存的服务器

/mcadd 服务器名称 服务器地址 [force] [群聊个数] [群号列表]
--添加要查询的服务器
--force: 可选参数，设为True时跳过预查询检查强制添加
--群聊个数: 可选参数，指定从群号列表中取前几个群
--群号列表: 可选参数，群号之间使用英文逗号分隔，如 123,456,789
--默认会添加到当前群；若填写群号列表，会在此基础上额外添加到指定群

/mcget 服务器名称/ID
--获取指定服务器的地址信息

/mcdel 服务器名称/ID 
--删除服务器

/mcup 服务器名称/ID [新名称] [新地址]
--更新服务器信息

/mclist
--列出所有服务器及其ID

/mccleanup
--手动触发自动清理（删除10天未查询成功的服务器）

/mcbind 服务器ID
--为指定服务器绑定数据压缩包（zip）
--发送命令后请在120秒内上传 .zip 文件
--压缩包内至少包含 mods 或 kubejs 文件夹之一

/mcq 服务器ID [提示词]
--使用 Agent 分析该服务器已绑定的 mods/kubejs 内容
--支持调用网络搜索工具补充信息

/mcop @用户 或 /mcop 用户ID
--将用户加入 /mcq 权限白名单
--仅系统管理员、群主、群管理员或群等级达到阈值的用户可操作

/mctem
--切换图片渲染模板
"""

@register("astrbot_mcgetter", "QiChen", "查询mc服务器信息和玩家列表,渲染为图片", "1.5.3")
class MyPlugin(Star):
    """Minecraft服务器信息查询插件"""
    
    def __init__(self, context: Context, config: Optional[Dict[str, Any]] = None):
        """
        初始化插件

        Args:
            context: 插件上下文
        """
        super().__init__(context)
        self.plugin_config = config or {}
        self.mcbind_service = McBindService()
        self.mcq_service = McqService()

    @filter.command("mchelp")
    async def get_help(self, event: AstrMessageEvent) -> MessageEventResult:
        """
        显示帮助信息

        Args:
            event: 消息事件

        Returns:
            包含帮助信息的消息结果
        """
        yield event.plain_result(HELP_INFO)

    @filter.command("mctem")
    async def change_mctem(self,event: AstrMessageEvent,name: str)-> MessageEventResult:
        if name is None:
            yield event.plain_result("请指定模板名称")

        if write_config(name):
            yield event.plain_result("模板切换成功")
        else:
            yield event.plain_result("模板配置文件写入失败")

    @filter.command("mc")
    async def mcgetter(self, event: AstrMessageEvent) -> Optional[MessageEventResult]:
        """
        查询所有保存的服务器信息

        Args:
            event: 消息事件

        Returns:
            包含服务器信息图片的消息结果，如果出错则返回None
        """
        try:
            group_id = event.get_group_id()
            
            json_path = await self.get_json_path(group_id)

            json_data = await read_json(json_path)

            if not json_data or not json_data.get("servers"):
                yield event.plain_result("请先使用 /mcadd 添加服务器")
                return
            
            # 执行自动清理
            deleted_servers = await auto_cleanup_servers(json_path)
            if deleted_servers:
                cleanup_message = "自动清理完成，以下服务器因10天未查询成功已被删除:\n"
                for server in deleted_servers:
                    last_success_date = datetime.fromtimestamp(server['last_success_time']).strftime('%Y-%m-%d %H:%M:%S')
                    cleanup_message += f"• {server['name']} (ID: {server['id']}) - 地址: {server['host']} - 最后成功: {last_success_date}\n"
                yield event.plain_result(cleanup_message.strip())
                
                # 重新读取数据（清理后）
                json_data = await read_json(json_path)
                if not json_data.get("servers"):
                    yield event.plain_result("所有服务器已被清理，请重新添加服务器")
                    return
            
            message_chain: List[Comp.Image] = []
            failed_servers: List[Dict[str, Any]] = []
            servers = json_data.get("servers", {})
            
            for server_id, server_info in servers.items():
                try:
                    mcinfo_img = await self.get_img(server_info['name'], server_info['host'], server_id, str(json_path))
                    if mcinfo_img:
                        message_chain.append(Comp.Image.fromBase64(mcinfo_img))
                    else:
                        failed_servers.append({
                            "id": server_id,
                            "name": server_info.get("name", "未知服务器"),
                            "host": server_info.get("host", "未知地址"),
                            "last_success_time": server_info.get("last_success_time")
                        })

                except Exception as e:
                    failed_servers.append({
                        "id": server_id,
                        "name": server_info.get("name", "未知服务器"),
                        "host": server_info.get("host", "未知地址"),
                        "last_success_time": server_info.get("last_success_time")
                    })
                    continue

            if message_chain:
                yield event.chain_result(message_chain)

            if failed_servers:
                failed_server_forward_chain = self.build_failed_servers_forward_chain(failed_servers)
                yield event.chain_result(failed_server_forward_chain)

            if not message_chain and not failed_servers:
                yield event.plain_result("没有可用的服务器信息，请检查服务器是否在线")
                
        except Exception as e:
            yield event.plain_result("查询服务器信息时发生错误:"+str(e))

    def build_failed_servers_forward_chain(self, failed_servers: List[Dict[str, Any]]) -> List[Comp.Nodes]:
        """
        构建查询失败服务器的合并转发消息链

        Args:
            failed_servers: 查询失败的服务器信息列表

        Returns:
            List[Comp.Nodes]: 单条合并转发消息链
        """
        nodes: List[Comp.Node] = [
            Comp.Node(
                uin="0",
                name="MCGetter",
                content=[
                    Comp.Plain(f"本次查询共有 {len(failed_servers)} 个服务器失败，详情如下：")
                ]
            )
        ]

        for server in failed_servers:
            last_success_time = server.get("last_success_time")
            if isinstance(last_success_time, (int, float)) and last_success_time > 0:
                last_success_text = strftime('%Y-%m-%d %H:%M:%S', localtime(last_success_time))
            else:
                last_success_text = "从未查询成功"

            nodes.append(
                Comp.Node(
                    uin="0",
                    name="MCGetter",
                    content=[
                        Comp.Plain(
                            f"ID: {server.get('id', '未知')}\n"
                            f"名称: {server.get('name', '未知服务器')}\n"
                            f"地址: {server.get('host', '未知地址')}\n"
                            f"最后查询成功时间: {last_success_text}"
                        )
                    ]
                )
            )

        return [Comp.Nodes(nodes=nodes)]

    @filter.command("mcadd")
    async def mcadd(
        self,
        event: AstrMessageEvent,
        name: str,
        host: str,
        force: str = "false",
        group_count: int = 0,
        group_ids: str = ""
    ) -> MessageEventResult:
        """
        添加新的服务器

        Args:
            event: 消息事件
            name: 服务器名称
            host: 服务器地址
            force: 可选，True/False，是否跳过预查询
            group_count: 可选，指定从群号列表中取前几个群
            group_ids: 可选，群号列表，逗号分隔

        Returns:
            操作结果消息
        """

        try:
            # 解析 force，兼容 true/false/1/0/yes/no
            force_str = str(force).strip().lower()
            true_tokens = {"true", "1", "yes", "y", "on"}
            false_tokens = {"false", "0", "no", "n", "off", ""}

            force_enabled = False
            legacy_group_id = ""
            if force_str in true_tokens:
                force_enabled = True
            elif force_str in false_tokens:
                force_enabled = False
            elif re.fullmatch(r"\d+", force_str):
                # 兼容旧输入：/mcadd name host <群号>
                legacy_group_id = force_str
            else:
                yield event.plain_result("force 参数无效，请使用 True/False")
                return

            if group_count < 0:
                yield event.plain_result("群聊个数不能小于0")
                return

            parsed_group_ids: List[str] = []
            if group_ids:
                normalized_group_ids = str(group_ids).replace("，", ",")
                parsed_group_ids = [gid.strip() for gid in normalized_group_ids.split(",") if gid.strip()]
                invalid_group_ids = [gid for gid in parsed_group_ids if not re.fullmatch(r"\d+", gid)]
                if invalid_group_ids:
                    yield event.plain_result(f"以下群号不合法: {'、'.join(invalid_group_ids)}")
                    return

            target_group_ids: List[str] = []

            if legacy_group_id and not parsed_group_ids and group_count == 0:
                target_group_ids.append(legacy_group_id)

            if parsed_group_ids:
                if group_count > 0:
                    if len(parsed_group_ids) < group_count:
                        yield event.plain_result("群号列表数量少于指定的群聊个数")
                        return
                    target_group_ids.extend(parsed_group_ids[:group_count])
                else:
                    target_group_ids.extend(parsed_group_ids)

            # 检查host合法性
            if not re.match(r'^[a-zA-Z0-9.:-]+$', host):
                yield event.plain_result("服务器地址格式不正确，只能包含字母、数字和符号.:-")
                return
            elif await get_server_status(host) is None and not force_enabled:
                yield event.plain_result("预查询失败，请检查服务器是否在线或地址是否正确，或在完整的/mcadd命令后加上True 强制添加")
                return

            # 始终默认包含当前群
            current_group_id = event.get_group_id()
            if current_group_id:
                target_group_ids.insert(0, current_group_id)

            if not target_group_ids:
                yield event.plain_result("当前会话没有群号，请填写群号列表参数")
                return

            # 去重并保留顺序
            target_group_ids = list(dict.fromkeys(target_group_ids))

            result_lines: List[str] = []

            for group_id in target_group_ids:
                json_path = await self.get_json_path(group_id)

                # 检查当前群是否已存在相同地址
                try:
                    json_data = await read_json(json_path)
                    servers = json_data.get("servers", {})
                    duplicated_server = None
                    for server_id, server_info in servers.items():
                        if server_info.get('host') == host:
                            duplicated_server = (server_id, server_info)
                            break

                    if duplicated_server:
                        dup_id, dup_info = duplicated_server
                        result_lines.append(
                            f"群 {group_id}: 已存在相同地址服务器 {dup_info.get('name', '未知')} (ID: {dup_id})"
                        )
                        continue
                except Exception as e:
                    result_lines.append(f"群 {group_id}: 检查地址失败 - {str(e)}")
                    continue

                # 执行添加并获取新增ID
                if await add_data(json_path, name, host):
                    try:
                        json_data = await read_json(json_path)
                        servers = json_data.get("servers", {})
                        created_id = None
                        for server_id, server_info in servers.items():
                            if server_info.get('name') == name and server_info.get('host') == host:
                                created_id = server_id
                                break

                        if created_id:
                            result_lines.append(f"群 {group_id}: 添加成功 {name} (ID: {created_id})")
                        else:
                            result_lines.append(f"群 {group_id}: 添加成功 {name}")
                    except Exception as e:
                        result_lines.append(f"群 {group_id}: 添加成功，但读取新ID失败 - {str(e)}")
                else:
                    result_lines.append(f"群 {group_id}: 无法添加 {name}，请检查是否已存在")

            if result_lines:
                yield event.plain_result("\n".join(result_lines))
            else:
                yield event.plain_result("未执行任何添加操作")
                
        except Exception as e:
            yield event.plain_result("添加服务器时发生错误:"+str(e))

    @filter.command("mcdel")
    async def mcdel(self, event: AstrMessageEvent, identifier: str) -> MessageEventResult:
        """
        删除指定的服务器（支持通过名称或ID删除）

        Args:
            event: 消息事件
            identifier: 要删除的服务器名称或ID

        Returns:
            操作结果消息
        """
        try:
            group_id = event.get_group_id()
            json_path = await self.get_json_path(group_id)
            
            if await del_data(json_path, identifier):
                yield event.plain_result(f"成功删除服务器 {identifier}")
            else:
                yield event.plain_result(f"无法删除 {identifier}，请检查是否存在")
                
        except Exception as e:
            yield event.plain_result("删除服务器时发生错误:"+str(e))

    @filter.command("mcbind")
    async def mcbind(self, event: AstrMessageEvent, server_id: str) -> MessageEventResult:
        """
        为指定服务器绑定数据文件（上传zip后解压mods/kubejs）
        """
        message = await self.mcbind_service.begin_bind(event, server_id, self.get_json_path)
        if message:
            yield event.plain_result(message)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def handle_mcbind_file(self, event: AstrMessageEvent) -> MessageEventResult:
        """
        处理 /mcbind 后的文件上传消息
        """
        message = await self.mcbind_service.handle_file_message(event, self.get_json_path)
        if message:
            yield event.plain_result(message)

    @filter.command("mcget")
    async def mcget(self, event: AstrMessageEvent, identifier: str) -> MessageEventResult:
        """
        获取指定服务器的信息（支持通过名称或ID查找）
        """
        try:
            group_id = event.get_group_id()
            json_path = await self.get_json_path(group_id)
            
            server_info = await get_server_info(json_path, identifier)
            if not server_info:
                yield event.plain_result(f"没有找到服务器 {identifier}")
                return
                
            yield event.plain_result(f"{server_info['name']} (ID: {server_info['id']}) 的地址是:")
            yield event.plain_result(f"{server_info['host']}")
            
        except Exception as e:
            yield event.plain_result("获取服务器信息时发生错误:"+str(e))

    @filter.command("mcq")
    async def mcq(self, event: AstrMessageEvent) -> MessageEventResult:
        """对指定服务器已绑定内容进行 Agent 分析。"""
        try:
            if not self._can_use_mcq(event):
                yield event.plain_result(
                    "你没有权限使用 /mcq。默认仅系统管理员、群主/群管理员、群等级达到阈值用户可用；"
                    "管理员可用 /mcop @用户 或 /mcop 用户ID 添加白名单。"
                )
                return

            result = await self.mcq_service.ask(event, self.context, self.get_json_path)
            yield event.plain_result(result)
        except Exception as e:
            yield event.plain_result("执行 mcq 分析时发生错误:" + str(e))

    @filter.command("mcop")
    async def mcop(self, event: AstrMessageEvent, user_id: str = "") -> MessageEventResult:
        """添加 /mcq 白名单用户。"""
        try:
            if not self._can_manage_mcq_whitelist(event):
                yield event.plain_result("你没有权限执行 /mcop")
                return

            target_user_id = self._extract_target_user_id(event, user_id)
            if not target_user_id:
                yield event.plain_result("用法：/mcop @用户 或 /mcop 用户ID")
                return

            whitelist = self._get_mcq_whitelist()
            if target_user_id in whitelist:
                yield event.plain_result(f"用户 {target_user_id} 已在 /mcq 白名单中")
                return

            whitelist.append(target_user_id)
            self._set_plugin_config_value("mcq_whitelist_user_ids", whitelist)
            self._save_plugin_config()

            yield event.plain_result(f"已将用户 {target_user_id} 加入 /mcq 白名单")
        except Exception as e:
            yield event.plain_result("执行 mcop 时发生错误:" + str(e))

    @filter.command("mcup")
    async def mcup(self, event: AstrMessageEvent, identifier: str, new_name: Optional[str] = None, new_host: Optional[str] = None) -> MessageEventResult:
        """
        更新服务器信息（支持通过名称或ID更新）

        Args:
            event: 消息事件
            identifier: 要更新的服务器名称或ID
            new_name: 新的服务器名称（可选）
            new_host: 新的服务器地址（可选）

        Returns:
            操作结果消息
        """

        try:
            if not new_name and not new_host:
                yield event.plain_result("请提供要更新的信息（新名称或新地址）")
                return
                
            # 如果提供了新地址，检查格式
            if new_host and not re.match(r'^[a-zA-Z0-9.:-]+$', new_host):
                yield event.plain_result("服务器地址格式不正确，只能包含字母、数字和符号.:-")
                return
                
            group_id = event.get_group_id()
            json_path = await self.get_json_path(group_id)
            
            if await update_data(json_path, identifier, new_name, new_host):
                # 获取更新后的服务器信息
                updated_info = await get_server_info(json_path, identifier)
                if updated_info:
                    yield event.plain_result(f"成功更新服务器信息: {updated_info['name']} (ID: {updated_info['id']})")
                else:
                    yield event.plain_result(f"成功更新服务器 {identifier}")
            else:
                yield event.plain_result(f"无法更新 {identifier}，请检查是否存在或名称是否冲突")
                
        except Exception as e:
            yield event.plain_result("更新服务器信息时发生错误:"+str(e))

    @filter.command("mclist")
    async def mclist(self, event: AstrMessageEvent) -> MessageEventResult:
        """
        列出所有服务器及其ID
        """
        try:
            group_id = event.get_group_id()
            json_path = await self.get_json_path(group_id)
            
            servers = await get_all_servers(json_path)
            if not servers:
                yield event.plain_result("没有保存的服务器")
                return

            nodes: List[Comp.Node] = [
                Comp.Node(
                    uin="0",
                    name="MCGetter",
                    content=[
                        Comp.Plain(f"当前保存的服务器共 {len(servers)} 个，列表如下：")
                    ]
                )
            ]

            for server_id, server_info in servers.items():
                nodes.append(
                    Comp.Node(
                        uin="0",
                        name="MCGetter",
                        content=[
                            Comp.Plain(
                                f"ID: {server_id}\n"
                                f"名称: {server_info.get('name', '未知服务器')}\n"
                                f"地址: {server_info.get('host', '未知地址')}"
                            )
                        ]
                    )
                )

            yield event.chain_result([Comp.Nodes(nodes=nodes)])
            
        except Exception as e:
            yield event.plain_result("获取服务器列表时发生错误:"+str(e))

    @filter.command("mccleanup")
    async def mccleanup(self, event: AstrMessageEvent) -> MessageEventResult:
        """
        手动触发自动清理（删除10天未查询成功的服务器）
        """
        try:
            group_id = event.get_group_id()
            json_path = await self.get_json_path(group_id)
            
            deleted_servers = await auto_cleanup_servers(json_path)
            if deleted_servers:
                cleanup_message = "自动清理完成，以下服务器因10天未查询成功已被删除:\n"
                for server in deleted_servers:
                    last_success_date = datetime.fromtimestamp(server['last_success_time']).strftime('%Y-%m-%d %H:%M:%S')
                    cleanup_message += f"• {server['name']} (ID: {server['id']}) - 地址: {server['host']} - 最后成功: {last_success_date}\n"
                yield event.plain_result(cleanup_message.strip())
            else:
                yield event.plain_result("没有需要清理的服务器")
                
        except Exception as e:
            yield event.plain_result("自动清理时发生错误:"+str(e))

    async def get_img(self, server_name: str, host: str, server_id: Optional[str] = None, json_path: Optional[str] = None) -> Optional[str]:
        """
        获取服务器信息图片

        Args:
            server_name: 服务器名称
            host: 服务器地址
            server_id: 服务器ID（可选）
            json_path: JSON文件路径（用于更新状态）

        Returns:
            图片的base64编码字符串，如果获取失败则返回None
        """
        try:
            info = await get_server_status(host)
            if not info:
                # 更新查询失败状态
                if json_path and server_id:
                    await update_server_status(json_path, server_id, False)
                return None

            # 更新查询成功状态
            if json_path and server_id:
                await update_server_status(json_path, server_id, True)

            info['server_name'] = server_name
            # 如果有服务器ID，则在名称前添加ID
            display_name = f"[{server_id}]{server_name}" if server_id else server_name
            
            mcinfo_img = await get_img(
                players_list=info['players_list'],
                latency=info['latency'],
                server_name=display_name,
                plays_max=info['plays_max'],
                plays_online=info['plays_online'],
                server_version=info['server_version'],
                icon_base64=info['icon_base64']
            )
            return mcinfo_img
            
        except Exception as e:
            # 更新查询失败状态
            if json_path and server_id:
                await update_server_status(json_path, server_id, False)
            return None

    async def get_json_path(self, group_id: str) -> Path:
        """
        获取群组的JSON配置文件路径

        Args:
            group_id: 群组ID

        Returns:
            JSON文件的Path对象
        """
        data_path = StarTools.get_data_dir("astrbot_mcgetter")
        json_path = data_path / f'{group_id}.json'
        json_path.parent.mkdir(parents=True, exist_ok=True)
        return json_path

    def _get_plugin_config_value(self, key: str, default: Any) -> Any:
        try:
            if hasattr(self.plugin_config, "get"):
                value = self.plugin_config.get(key, default)
                return default if value is None else value
        except Exception:
            pass
        return default

    def _set_plugin_config_value(self, key: str, value: Any) -> None:
        try:
            if isinstance(self.plugin_config, dict) or hasattr(self.plugin_config, "__setitem__"):
                self.plugin_config[key] = value
        except Exception as e:
            logger.warning("设置插件配置失败 key=%s: %s", key, e)

    def _save_plugin_config(self) -> None:
        save_fn = getattr(self.plugin_config, "save_config", None)
        if callable(save_fn):
            save_fn()

    def _get_mcq_whitelist(self) -> List[str]:
        raw = self._get_plugin_config_value("mcq_whitelist_user_ids", [])
        if not isinstance(raw, list):
            return []
        ret: List[str] = []
        for item in raw:
            s = str(item).strip()
            if s:
                ret.append(s)
        return list(dict.fromkeys(ret))

    def _extract_target_user_id(self, event: AstrMessageEvent, user_id_text: str) -> str:
        for comp in event.get_messages():
            if isinstance(comp, Comp.At):
                qq = str(getattr(comp, "qq", "") or "").strip()
                if qq and qq != "all":
                    return qq

        text = str(user_id_text or "").strip()
        if re.fullmatch(r"\d+", text):
            return text
        return ""

    def _extract_sender_level(self, event: AstrMessageEvent) -> int:
        sender = getattr(event.message_obj, "sender", None)
        level_candidates = []
        if sender is not None:
            level_candidates.append(getattr(sender, "level", None))
            level_candidates.append(getattr(sender, "group_level", None))

        raw_message = getattr(event.message_obj, "raw_message", None)
        if isinstance(raw_message, dict):
            sender_obj = raw_message.get("sender")
            if isinstance(sender_obj, dict):
                level_candidates.append(sender_obj.get("level"))

        for raw_level in level_candidates:
            if raw_level is None:
                continue
            if isinstance(raw_level, (int, float)):
                return int(raw_level)
            s = str(raw_level)
            m = re.search(r"\d+", s)
            if m:
                try:
                    return int(m.group(0))
                except Exception:
                    continue
        return 0

    def _check_group_owner_or_admin(self, event: AstrMessageEvent) -> Dict[str, bool]:
        sender_id = event.get_sender_id()
        group = getattr(event.message_obj, "group", None)
        is_owner = False
        is_group_admin = False

        if group is not None:
            owner_id = str(getattr(group, "group_owner", "") or "").strip()
            if owner_id and sender_id and owner_id == sender_id:
                is_owner = True

            admins = getattr(group, "group_admins", None) or []
            admin_set = {str(a).strip() for a in admins if str(a).strip()}
            if sender_id and sender_id in admin_set:
                is_group_admin = True

        sender = getattr(event.message_obj, "sender", None)
        sender_role = str(getattr(sender, "role", "") or "").lower()
        event_role = str(getattr(event, "role", "") or "").lower()

        if sender_role in {"owner", "group_owner"}:
            is_owner = True
        if sender_role in {"admin", "administrator", "group_admin"}:
            is_group_admin = True
        if event_role in {"owner", "group_owner"}:
            is_owner = True
        if event_role in {"admin", "administrator", "group_admin"}:
            is_group_admin = True

        return {"owner": is_owner, "admin": is_group_admin}

    def _can_manage_mcq_whitelist(self, event: AstrMessageEvent) -> bool:
        allow_astrbot_admin = bool(self._get_plugin_config_value("mcq_allow_astrbot_admin", True))

        if allow_astrbot_admin and event.is_admin():
            return True

        role_check = self._check_group_owner_or_admin(event)
        if role_check["owner"] or role_check["admin"]:
            return True

        return False

    def _can_use_mcq(self, event: AstrMessageEvent) -> bool:
        permission_enabled = bool(self._get_plugin_config_value("mcq_permission_enabled", True))
        if not permission_enabled:
            return True

        sender_id = event.get_sender_id()
        if sender_id and sender_id in self._get_mcq_whitelist():
            return True

        allow_astrbot_admin = bool(self._get_plugin_config_value("mcq_allow_astrbot_admin", True))
        allow_group_owner = bool(self._get_plugin_config_value("mcq_allow_group_owner", True))
        allow_group_admin = bool(self._get_plugin_config_value("mcq_allow_group_admin", True))
        min_group_level = int(self._get_plugin_config_value("mcq_min_group_level", 90) or 0)

        if allow_astrbot_admin and event.is_admin():
            return True

        role_check = self._check_group_owner_or_admin(event)
        if allow_group_owner and role_check["owner"]:
            return True
        if allow_group_admin and role_check["admin"]:
            return True

        if min_group_level > 0 and self._extract_sender_level(event) >= min_group_level:
            return True

        return False
