# 配置路径迁移完成

## 变更摘要

已将实时监控、日志分析和双目分析中的端口和SSH密钥配置统一迁移到项目相对路径 `data/conf/` 下。

## 文件变更

### 新增文件

1. **data/conf/ssh_config.json** - SSH 连接配置文件
   - SSH 密钥路径（相对路径）
   - SSH 主机地址
   - SSH 用户名
   - 各功能模块的默认端口

2. **robot_monitor/config_loader.py** - 配置加载器
   - 提供统一的配置加载接口
   - 自动处理相对路径转绝对路径
   - 提供默认配置回退

3. **data/conf/README.md** - 配置文档
   - 详细的配置说明
   - 使用示例
   - 注意事项

### 修改文件

1. **robot_monitor/ssh_bridge.py**
   - 导入 config_loader 模块
   - 使用 `get_ssh_key_path()`, `get_ssh_host()`, `get_ssh_user()` 替代硬编码
   - `_upload_monitor_images()` 中使用 `get_default_port("stereo_analysis")`

2. **robot_monitor/offline_server.py**
   - 导入 config_loader 模块
   - 使用配置加载器替代硬编码的 SSH 配置
   - 新增 `/offline/config` API 端点，供前端获取配置

3. **src/components/ConnectionPanel.vue**
   - 添加 `onMounted` 钩子
   - 从服务器加载 `realtime_monitor` 默认端口

4. **src/components/LogFetchPanel.vue**
   - 添加 `onMounted` 钩子
   - 从服务器加载 `log_fetch` 默认端口

5. **src/components/StereoAnalysis2Panel.vue**
   - 添加 `onMounted` 钩子
   - 从服务器加载 `stereo_analysis` 默认端口

## 配置结构

```
data/conf/
├── ssh_config.json          # SSH 连接配置
├── bestmow_rsa_202604       # SSH 私钥（已存在）
└── README.md                # 配置文档
```

## 配置示例

```json
{
  "ssh_key_path": "bestmow_rsa_202604",
  "ssh_host": "120.25.121.3",
  "ssh_user": "root",
  "default_ports": {
    "realtime_monitor": 10015,
    "log_fetch": 10123,
    "stereo_analysis": 10123
  }
}
```

## 使用方式

### 后端

```python
from config_loader import get_ssh_key_path, get_default_port

ssh_key = get_ssh_key_path()  # 返回绝对路径
port = get_default_port("log_fetch")  # 返回 10123
```

### 前端

前端组件会在挂载时自动从 `/offline/config` API 加载配置并更新默认端口。

## 优势

1. **集中管理**：所有配置统一在 `data/conf/` 目录
2. **相对路径**：SSH 密钥使用项目相对路径，便于迁移
3. **灵活配置**：可以轻松修改端口和连接参数
4. **向后兼容**：如果配置文件不存在，使用默认值
5. **前后端同步**：前端自动从后端获取最新配置

## 测试验证

```bash
# 测试配置加载
python3 robot_monitor/config_loader.py

# 输出：
# SSH Key Path: /home/youfeng/.../data/conf/bestmow_rsa_202604
# SSH Host: 120.25.121.3
# SSH User: root
# Default Ports:
#   - Realtime Monitor: 10015
#   - Log Fetch: 10123
#   - Stereo Analysis: 10123
```

## 注意事项

1. SSH 私钥文件权限已正确设置为 600
2. 修改配置后需要重启后端服务
3. 前端会在页面加载时自动获取最新配置
