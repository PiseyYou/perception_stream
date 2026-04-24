# 配置文件说明

本项目的配置文件统一存放在 `data/conf/` 目录下。

## 目录结构

```
data/
├── conf/                    # 配置文件目录
│   ├── ssh_config.json      # SSH 连接配置
│   ├── bestmow_rsa_202604   # SSH 私钥
│   └── README.md            # 本文档
├── visualization/           # 可视化数据（符号链接）
│   └── 0327/
│       ├── cam_images/
│       ├── cam_pointclouds/
│       ├── nav_images/
│       └── nav_pointclouds/
├── bag_debug/               # Bag 调试数据
└── stereo_debug/            # 双目调试数据
```

## SSH 配置 (ssh_config.json)

配置 SSH 连接参数，用于实时监控、日志拉取和双目分析功能。

### 配置项说明

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

- **ssh_key_path**: SSH 私钥文件路径
  - 可以是相对路径（相对于 `data/conf/` 目录）
  - 也可以是绝对路径
  - 示例：`"bestmow_rsa_202604"` 或 `"/home/user/.ssh/id_rsa"`

- **ssh_host**: SSH 服务器地址
  - 示例：`"120.25.121.3"`

- **ssh_user**: SSH 登录用户名
  - 示例：`"root"`

- **default_ports**: 各功能模块的默认端口配置
  - **realtime_monitor**: 实时监控连接端口（用于 ConnectionPanel）
  - **log_fetch**: 日志拉取端口（用于 LogFetchPanel）
  - **stereo_analysis**: 双目分析图片上传端口（用于 StereoAnalysis2Panel）

### 使用方式

#### 后端 Python

```python
from config_loader import get_ssh_key_path, get_ssh_host, get_ssh_user, get_default_port

# 获取 SSH 配置
ssh_key = get_ssh_key_path()
ssh_host = get_ssh_host()
ssh_user = get_ssh_user()

# 获取默认端口
port = get_default_port("realtime_monitor")  # 或 "log_fetch", "stereo_analysis"
```

#### 前端 Vue

前端组件会在 `onMounted` 时自动从 `/offline/config` API 加载配置：

```typescript
onMounted(async () => {
  try {
    const res = await fetch('/offline/config')
    const data = await res.json()
    if (data.ok && data.default_ports?.realtime_monitor) {
      port.value = data.default_ports.realtime_monitor
    }
  } catch (e) {
    console.warn('Failed to load config:', e)
  }
})
```

### 配置文件位置

- 配置文件：`data/conf/ssh_config.json`
- SSH 密钥：`data/conf/bestmow_rsa_202604`（或配置中指定的路径）

### 注意事项

1. SSH 私钥文件权限应设置为 600：
   ```bash
   chmod 600 data/conf/bestmow_rsa_202604
   ```

2. 如果配置文件不存在，系统会使用默认配置

3. 修改配置后需要重启后端服务才能生效

4. 前端会在页面加载时自动获取最新配置
