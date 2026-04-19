# astrbot_mcgetter

<div align="center">

![:name](https://count.getloli.com/@astrbot_mcgetter?name=astrbot_mcgetter&theme=minecraft&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

</div>

## 简介

AstrBot Minecraft服务器信息查询插件，用于查询Minecraft服务器状态信息并使用图片展示。支持多服务器管理、实时状态查询、玩家列表显示、自动清理等功能。

## 功能特性

- 🎮 **多服务器管理** - 支持添加、删除、查询多个Minecraft服务器
- 📊 **实时状态查询** - 获取服务器在线状态、玩家数量、延迟等信息
- 👥 **玩家列表显示** - 显示当前在线玩家列表
- 🖼️ **图片化展示** - 将服务器信息渲染为美观的图片
- 🔒 **地址验证** - 自动验证服务器地址格式和连接性
- 📝 **群组独立** - 每个群组独立管理服务器列表
- 🧹 **自动清理** - 自动删除长时间未查询成功的服务器
- 🆔 **ID管理** - 基于ID的服务器管理系统，支持名称和ID双重操作
- 🕹️ **自定义模板** - 用户可自定义图片渲染效果,支持动态加载

## 安装说明

1. 确保已安装 AstrBot
2. 将插件文件放入 AstrBot 插件目录
3. 重启 AstrBot 或重新加载插件
4. 在群聊中使用 `/mchelp` 查看帮助

## 上传端一键打包（Windows）

为了给 `/mcbind` 提供更干净的上传包，仓库提供了 `pack_output_zip.bat` + `pack_output_zip.ps1`（仅用户侧打包，不影响插件逻辑）。

### 使用前准备

1. 安装并配置好 Java（确保 `java` 命令可用）。
2. 下载 Vineflower 反编译器，并将其重命名为 `vineflower.jar`。
3. 将 `pack_output_zip.bat`、`pack_output_zip.ps1` 与 `vineflower.jar` 放到游戏目录中，且与 `mods`、`kubejs` 同级。

目录示例：

```
MinecraftRoot/
    mods/
    kubejs/
    vineflower.jar
    pack_output_zip.bat
    pack_output_zip.ps1
```

### 执行方式

双击运行 `pack_output_zip.bat`（或在 CMD 中执行）。脚本会：

1. 在独立临时目录中工作，不污染原始 `mods`、`kubejs`。
2. 复制 `kubejs`，并排除 `assets` 目录。
3. 批量反编译 `mods` 下全部 `.jar` 到临时目录。
4. 删除反编译结果中的 `assets`。
5. 打包生成同级目录下的 `output.zip`（包含 `mods`、`kubejs` 两个子目录）。

然后将 `output.zip` 上传给插件的 `/mcbind` 流程即可。

### 并发反编译（加速）

- 默认并发数：自动使用 CPU 核心数的一半（向下取整，最低 1，上限 8），避免默认占满导致卡顿。
- 手动指定并发：

```cmd
pack_output_zip.bat 6
```

说明：`6` 表示最多同时反编译 6 个 jar。

## 使用方法

### 基础命令

| 命令           | 参数                   | 说明           |
|--------------|----------------------|--------------|
| `/mchelp`    | 无                    | 查看帮助信息       |
| `/mc`        | 无                    | 查询所有保存的服务器状态 |
| `/mcadd`     | 服务器名称 服务器地址 [force]  | 添加要查询的服务器    |
| `/mcget`     | 服务器名称/ID             | 获取指定服务器的地址信息 |
| `/mcdel`     | 服务器名称/ID             | 删除指定的服务器     |
| `/mcup`      | 服务器名称/ID [新名称] [新地址] | 更新服务器信息      |
| `/mclist`    | 无                    | 列出所有服务器及其ID  |
| `/mccleanup` | 无                    | 手动触发自动清理     |
| `/mctem`     | 模板名称                 | 切换图片渲染模板     |

### 详细说明

#### 添加服务器
```
/mcadd 服务器名称 服务器地址 [force]
```
- **服务器名称**: 自定义的服务器名称
- **服务器地址**: 服务器IP地址或域名（支持端口号）
- **force**: 可选参数，设为True时跳过预查询检查强制添加

**示例**:
```
/mcadd Hypixel mc.hypixel.net
/mcadd 本地服务器 127.0.0.1:25565 True
```

#### 查询服务器
```
/mc
```
查询所有已保存的服务器状态，返回包含以下信息的图片：
- 服务器名称和ID
- 在线状态
- 玩家数量（当前/最大）
- 服务器版本
- 延迟
- 在线玩家列表

**自动清理**: 每次执行 `/mc` 命令时会自动清理10天未查询成功的服务器

#### 获取服务器地址
```
/mcget 服务器名称/ID
```
获取指定服务器的地址信息。支持通过名称或ID查找。

#### 删除服务器
```
/mcdel 服务器名称/ID
```
从列表中删除指定的服务器。支持通过名称或ID删除。

#### 更新服务器信息
```
/mcup 服务器名称/ID [新名称] [新地址]
```
更新指定服务器的名称或地址信息。

#### 列出所有服务器
```
/mclist
```
显示所有保存的服务器及其ID和地址。

#### 手动清理
```
/mccleanup
```
手动触发自动清理，删除10天未查询成功的服务器。

## 自动清理功能

### 功能特性
- **自动状态记录**: 记录服务器创建时间、最后成功/失败时间、失败次数
- **自动清理规则**: 服务器连续10天未查询成功时自动删除
- **清理时机**: 每次使用 `/mc` 命令时自动触发，或使用 `/mccleanup` 手动触发
- **清理提示**: 删除服务器时显示详细信息（名称、ID、地址、最后成功时间）

### 清理消息示例
```
自动清理完成，以下服务器因10天未查询成功已被删除:
• 过期服务器1 (ID: 2) - 地址: example.com:25565 - 最后成功: 2024-01-01 12:00:00
• 过期服务器2 (ID: 3) - 地址: test.server.com - 最后成功: 2024-01-02 15:30:00
```

## 自定义模板

### 使用说明

1. 编写或下载自定义处理脚本
    脚本需满足以下条件:
    - 调用函数必须命名为draw_image
    - 需包含以下参数:
        - players_list: list(玩家名称列表)
        - latency: int(延迟)
        - server_name: str(服务器名称)
        - plays_max: int(最大玩家数)
        - plays_online: int(在线玩家数)
        - server_version: str(服务器版本)
        - icon_base64: Optional[str] = None(服务器图标,可为空)
    - 返回值需为图片的base64 string值

示例:
```python

async def draw_image(
    players_list: list,
    latency: int,
    server_name: str,
    plays_max: int,
    plays_online: int,
    server_version: str,
    icon_base64: Optional[str] = None
) -> str:
    """生成服务器信息图片并返回base64编码"""
    
    # 异步获取图标
    server_icon = await fetch_icon(icon_base64)
    
    # 配置参数
    BG_COLOR = (34, 34, 34)
    TEXT_COLOR = (255, 255, 255)
    ACCENT_COLOR = (85, 255, 85)
    WARNING_COLOR = (255, 170, 0)
    ERROR_COLOR = (255, 85, 85)
    
    # 字体配置
    try:
        title_font = await load_font(30)
        text_font = await load_font(20)
        small_font = await load_font(18)
    except IOError:
        title_font = ImageFont.load_default(30)
        text_font = ImageFont.load_default(20)
        small_font = ImageFont.load_default(18)
    
    # 计算布局参数
    icon_size = 64 if server_icon else 0
    base_y = 20
    text_x = 20 + icon_size + 20
    
    # 自动计算图片高度
    line_height = 30
    player_lines = (len(players_list) // 4) + 1
    img_height = 180 + (player_lines * line_height) + (20 if server_icon else 0)
    
    # 创建画布
    img = Image.new("RGB", (600, img_height), color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # 绘制服务器图标
    if server_icon:
        icon_mask = Image.new("L", (64, 64), 0)
        mask_draw = ImageDraw.Draw(icon_mask)
        mask_draw.rounded_rectangle((0, 0, 64, 64), radius=10, fill=255)
        server_icon.thumbnail((64, 64))
        img.paste(server_icon, (20, base_y), icon_mask)
    
    # 服务器信息绘制（保持原有绘制逻辑不变）
    draw.text((text_x, base_y), server_name, font=title_font, fill=ACCENT_COLOR)
    base_y += 40
    
    version_text = f"版本: {server_version}"
    latency_color = ACCENT_COLOR if latency < 100 else WARNING_COLOR if latency < 200 else ERROR_COLOR
    latency_text = f"延迟: {latency}ms"
    
    draw.text((text_x, base_y), version_text, font=text_font, fill=TEXT_COLOR)
    draw.text((400, base_y), latency_text, font=text_font, fill=latency_color)
    base_y += 40
    
    online_text = f"在线玩家 ({plays_online}/{plays_max})"
    draw.text((text_x, base_y), online_text, font=text_font, fill=ACCENT_COLOR)
    base_y += 40
    
    if players_list:
        chunks = [players_list[i:i+4] for i in range(0, len(players_list), 4)]
        for chunk in chunks:
            players_line = " • ".join(chunk)
            draw.text((text_x + 20, base_y), players_line, font=small_font, fill=TEXT_COLOR)
            base_y += line_height
    else:
        draw.text((text_x + 20, base_y), "暂无玩家在线", font=small_font, fill=TEXT_COLOR)
        base_y += line_height
    
    draw.rounded_rectangle([10, 10, img.width-10, img.height-10], radius=10, outline=ACCENT_COLOR, width=2)
    
    # 转换为base64
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    # 返回base64 bytes
    return img_base64

```

2. 将脚本存放到Astrbot的插件数据目录,例如Windows中的路径为
```路径
...\AstrBot\data\plugin_data
```

具体而言,存放在plugin_data\astrbot_mcgetter\template下

命名为{name}.py,其中name就是模板名称

你也可以手动修改template.txt来决定使用的模板

## JSON配置系统

### 数据格式
插件使用基于ID的JSON配置系统，支持自动版本迁移：

```json
{
    "version": "2.1",
    "next_id": 5,
    "last_cleanup": 1752028440,
    "servers": {
        "1": {
            "id": 1,
            "name": "主服务器",
            "host": "main.example.com:25565",
            "created_time": 1752028440,
            "last_success_time": 1752028440,
            "last_failed_time": null,
            "failed_count": 0
        }
    }
}
```

### 主要特性
- **自动版本迁移**: 旧版配置会自动迁移到新版格式
- **ID管理**: 使用递增的数字ID，删除后不重用
- **向后兼容**: 支持通过名称或ID进行操作
- **状态跟踪**: 记录服务器查询状态和时间戳

## 支持的功能

- ✅ 多服务器管理
- ✅ 实时状态查询
- ✅ 玩家列表显示
- ✅ 图片化信息展示
- ✅ 地址格式验证
- ✅ 群组独立配置
- ✅ 强制添加模式
- ✅ 自动清理功能
- ✅ ID管理系统
- ✅ 服务器信息更新
- ✅ 状态跟踪记录

## 技术特性

- **地址验证**: 只允许字母、数字和符号 `.:-` 在服务器地址中
- **预查询检查**: 添加服务器前自动验证连接性
- **错误处理**: 完善的异常处理和用户友好的错误提示
- **日志记录**: 详细的操作日志便于调试
- **异步操作**: 所有操作都是异步的，性能优异
- **数据安全**: 删除操作前会显示详细信息

## 使用场景

### 场景1: 定期维护
```
1. 定期使用 /mc 命令查询服务器
2. 系统自动清理过期服务器
3. 查看清理结果，了解服务器状态
```

### 场景2: 服务器管理
```
1. 使用 /mclist 查看所有服务器
2. 通过 /mcget 获取特定服务器信息
3. 使用 /mcup 更新服务器信息
4. 用 /mcdel 删除不需要的服务器
```

### 场景3: 监控服务器状态
```
1. 使用 /mc 查看所有服务器状态
2. 观察服务器的查询状态
3. 及时发现并处理问题服务器
```

## 配置参数

### 自动清理配置
- **清理天数**: 10天（可在代码中修改 `AUTO_CLEANUP_DAYS` 常量）
- **清理时机**: 每次 `/mc` 命令执行时
- **清理提示**: 显示被删除服务器的详细信息

## 版本信息

- **插件版本**: 1.4.0
- **JSON格式版本**: 2.1
- **兼容性**: 完全向后兼容

## 注意事项

### 1. 数据安全
- 删除操作不可逆，请谨慎使用
- 建议定期备份重要的服务器配置
- 清理前会显示详细的删除信息

### 2. 时间计算
- 基于Unix时间戳计算
- 精确到秒级别
- 自动处理时区问题

### 3. 性能考虑
- 清理操作是异步的，不会阻塞其他功能
- 只在必要时执行清理（有服务器需要清理时）
- 清理结果会缓存，避免重复计算

## 故障排除

### 常见问题

**Q: 为什么服务器没有被自动清理？**
A: 检查服务器的 `last_success_time` 是否真的超过10天，或者使用 `/mccleanup` 手动触发

**Q: 如何查看服务器的查询状态？**
A: 使用 `/mclist` 查看所有服务器，或直接查看JSON配置文件

**Q: 可以修改清理天数吗？**
A: 可以，修改 `script/json_operate.py` 中的 `AUTO_CLEANUP_DAYS` 常量

**Q: 清理操作会影响正常使用吗？**
A: 不会，清理操作是异步的，不会阻塞其他功能

**Q: 如何恢复被删除的服务器？**
A: 被删除的服务器无法自动恢复，需要重新使用 `/mcadd` 添加

**Q: 支持通过ID操作吗？**
A: 是的，所有命令都支持通过名称或ID进行操作

## 最佳实践

### 1. 定期维护
- 每周使用 `/mc` 命令查询一次所有服务器
- 定期使用 `/mccleanup` 手动清理
- 关注清理结果，及时处理问题

### 2. 服务器管理
- 及时删除不再使用的服务器
- 定期检查服务器状态
- 保持服务器列表的整洁

### 3. 监控建议
- 关注失败次数较多的服务器
- 定期检查最后成功时间
- 根据清理结果调整服务器配置

## 支持

- [AstrBot 帮助文档](https://astrbot.app)
- [GitHub Issues](https://github.com/your-repo/astrbot_mcgetter/issues)

## 开发计划

### TODO

- [ ] 玩家名称颜色随在线天数改变
- [ ] 服务器状态历史记录
- [x] 自定义图片主题
- [ ] 定时自动查询功能
- [ ] 服务器分组管理

## 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 贡献

欢迎提交 Issue 和 Pull Request 来改进这个插件！

---

<div align="center">

**Made with ❤️ for Minecraft Community**

</div>
