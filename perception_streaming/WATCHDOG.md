# Vite开发服务器看门狗

## 功能说明

自动监控Vite开发服务器状态，一旦检测到服务掉线，自动重启服务。

## 监控机制

看门狗每10秒执行以下检查：
1. **进程检查**：检查vite进程是否存在
2. **端口检查**：检查192.168.55.247:5173端口是否监听
3. **HTTPS检查**：检查HTTPS响应是否为200

任何一项检查失败，立即触发自动重启。

## 保护机制

- **重启限制**：连续重启最多3次
- **冷却时间**：达到重启上限后等待60秒再重试
- **计数重置**：成功运行60秒后重置重启计数器

## 使用方法

### 启动看门狗
```bash
./start-watchdog.sh
```

### 停止看门狗
```bash
./stop-watchdog.sh
```

### 查看日志
```bash
tail -f /tmp/vite-watchdog.log
```

### 查看Vite日志
```bash
tail -f /tmp/vite-dev.log
```

## 日志示例

```
[2026-05-07 18:20:34] =========================================
[2026-05-07 18:20:34] Vite看门狗启动
[2026-05-07 18:20:34] 项目目录: /media/sda1/perception_process/perception_streaming
[2026-05-07 18:20:34] 检查间隔: 10秒
[2026-05-07 18:20:34] =========================================
[2026-05-07 18:20:34] 初始检查：Vite服务正常运行
[2026-05-07 18:20:54] ⚠ 检测到服务掉线，尝试重启 (第1次)...
[2026-05-07 18:20:54] 启动Vite开发服务器...
[2026-05-07 18:21:04] ✓ Vite服务器启动成功
```

## 开机自启动（推荐 systemd）

长期运行请使用 systemd 管理看门狗。systemd 负责开机启动和守护 `watchdog.sh`，`watchdog.sh` 负责通过 HTTPS 健康检查并重启 Vite。

### 安装并启动

```bash
sudo ./script/install_perception_streaming_watchdog.sh
```

### 查看状态

```bash
sudo systemctl status perception-streaming-watchdog.service
```

### 重启服务

```bash
sudo systemctl restart perception-streaming-watchdog.service
```

### 查看 systemd 日志

```bash
sudo journalctl -u perception-streaming-watchdog.service -f
```

### 查看 watchdog / Vite 日志

```bash
tail -f /tmp/vite-watchdog.log
tail -f /tmp/vite-dev.log
```

### 停止开机自启动

```bash
sudo systemctl disable --now perception-streaming-watchdog.service
```

### 临时调试方式

如果只是当前登录会话里临时调试，也可以继续使用：

```bash
./start-watchdog.sh
./stop-watchdog.sh
```

不建议用 `crontab @reboot` 作为长期方案，因为它不能在 watchdog 进程异常退出后继续守护该进程。

## 文件说明

- `watchdog.sh` - 看门狗主脚本
- `start-watchdog.sh` - 启动脚本
- `stop-watchdog.sh` - 停止脚本
- `/tmp/vite-watchdog.log` - 看门狗日志
- `/tmp/vite-dev.log` - Vite服务器日志
- `/tmp/vite-watchdog.pid` - 看门狗进程ID文件

## 测试验证

手动停止Vite服务测试自动重启：
```bash
pkill -f "vite"
# 等待10-20秒，看门狗会自动重启服务
```

## 当前状态

✅ 看门狗已启动并正常运行
✅ 自动重启功能已验证通过
✅ 服务地址：http://192.168.55.247:5173/
