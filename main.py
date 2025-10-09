from typing import List, Optional, Dict, Any
from pathlib import Path
import astrbot.core.message.components as Comp
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from .script.get_server_info import get_server_status
from .script.get_img import generate_server_info_image
from .script.json_operate import (
    read_json, add_data, del_data, update_data, 
    get_all_servers, get_server_info, get_server_by_name,
    update_server_status, auto_cleanup_servers
)
import asyncio
import re
from datetime import datetime

# 常量定义
HELP_INFO = """
/mchelp 
--查看帮助

/mc   
--查询保存的服务器

/mcadd 服务器名称 服务器地址 [force]
--添加要查询的服务器
--force: 可选参数，设为True时跳过预查询检查强制添加

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
"""

@register("astrbot_mcgetter", "QiChen", "查询mc服务器信息和玩家列表,渲染为图片", "1.4.0")
class MyPlugin(Star):
    """Minecraft服务器信息查询插件"""
    
    def __init__(self, context: Context):
        """
        初始化插件

        Args:
            context: 插件上下文
        """
        super().__init__(context)

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
            servers = json_data.get("servers", {})
            
            for server_id, server_info in servers.items():
                try:
                    mcinfo_img = await self.get_img(server_info['name'], server_info['host'], server_id, str(json_path))
                    if mcinfo_img:
                        message_chain.append(Comp.Image.fromBase64(mcinfo_img))
                    else:
                except Exception as e:
                    continue

            if message_chain:
                yield event.chain_result(message_chain)
            else:
                yield event.plain_result("没有可用的服务器信息，请检查服务器是否在线")
                
        except Exception as e:
            yield event.plain_result("查询服务器信息时发生错误")

    @filter.command("mcadd")
    async def mcadd(self, event: AstrMessageEvent, name: str, host: str, force: bool = False) -> MessageEventResult:
        """
        添加新的服务器

        Args:
            event: 消息事件
            name: 服务器名称
            host: 服务器地址
            force: 是否强制添加（跳过预查询检查）

        Returns:
            操作结果消息
        """

        try:
            # 检查host合法性
            if not re.match(r'^[a-zA-Z0-9.:-]+$', host):
                yield event.plain_result("服务器地址格式不正确，只能包含字母、数字和符号.:-")
                return
            elif await get_server_status(host) is None and not force:
                yield event.plain_result("预查询失败，请检查服务器是否在线或地址是否正确，或在完整的/mcadd命令后加上True 强制添加")
                return
                
            group_id = event.get_group_id()
            json_path = await self.get_json_path(group_id)
            
            # 检查当前地址是否已存在
            try:
                json_data = await read_json(json_path)
                servers = json_data.get("servers", {})
                if servers:
                    for server_id, server_info in servers.items():
                        if server_info['host'] == host:
                            yield event.plain_result(f"已存在相同地址的服务器 {server_info['name']} (ID: {server_id})")
                            return
            except Exception as e:
                yield event.plain_result("检查服务器地址时发生错误")
                return
                
            if await add_data(json_path, name, host):
                # 获取新添加的服务器ID
                json_data = await read_json(json_path)
                servers = json_data.get("servers", {})
                for server_id, server_info in servers.items():
                    if server_info['name'] == name and server_info['host'] == host:
                        yield event.plain_result(f"成功添加服务器 {name} (ID: {server_id})")
                        return
                yield event.plain_result(f"成功添加服务器 {name}")
            else:
                yield event.plain_result(f"无法添加 {name}，请检查是否已存在")
                
        except Exception as e:
            yield event.plain_result("添加服务器时发生错误")

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
            yield event.plain_result("删除服务器时发生错误")

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
            yield event.plain_result("获取服务器信息时发生错误")

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
            yield event.plain_result("更新服务器信息时发生错误")

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
                
            server_list = "当前保存的服务器列表:\n"
            for server_id, server_info in servers.items():
                server_list += f"ID: {server_id}, 名称: {server_info['name']}, 地址: {server_info['host']}\n"
                
            yield event.plain_result(server_list.strip())
            
        except Exception as e:
            yield event.plain_result("获取服务器列表时发生错误")

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
            yield event.plain_result("自动清理时发生错误")

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
            
            mcinfo_img = await generate_server_info_image(
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
