# SSH "EOF during negotiation" 错误修复说明

## 问题描述
在使用 rosbag 上传和监控服务部署功能时，出现 "EOF during negotiation" 错误，导致文件传输失败。

## 根本原因
1. **SFTP 子系统问题**: 远程服务器的 SFTP 子系统不可用或配置有问题，导致 `open_sftp()` 调用失败
2. **SSH 连接不稳定**: 缺少心跳保活机制，连接容易超时
3. **没有重试机制**: 临时性网络问题导致传输失败
4. **rsync 超时设置过短**: 大文件传输容易超时

## 修复内容

### 1. 使用 SCP 替代 SFTP (ssh_bridge.py)
**问题**: 远程服务器的 SFTP 子系统不可用，导致 paramiko 的 `open_sftp()` 调用失败
**解决方案**: 改用 SCP 命令行工具上传文件
- 使用 `subprocess` 调用 `scp` 命令
- 添加 SSH keepalive 选项
- 实现自动重试机制（最多 3 次）
- 每次重试前等待 2 秒

### 2. 增强 SSH 连接稳定性 (ssh_bridge.py)
在主 SSH 连接中添加了以下选项：
- `timeout=30`: 连接超时 30 秒（从 15 秒增加）
- `ServerAliveInterval=10`: 每 10 秒发送心跳包
- `ServerAliveCountMax=3`: 最多允许 3 次心跳失败
- `look_for_keys=False`: 禁用自动密钥搜索
- `allow_agent=False`: 禁用 SSH agent
- `transport.set_keepalive(10)`: 设置传输层 keepalive

### 3. 优化 rsync 参数 (offline_server.py)
- 增加 `--contimeout=30`: 连接超时 30 秒
- 增加 `--timeout=60`: 数据传输超时 60 秒（从 30 秒增加）
- 添加 `ServerAliveInterval=10` 和 `ServerAliveCountMax=3`
- 保留 `--partial`: 支持断点续传

### 4. 实现自动重试机制
- **rsync 下载**: 对临时性错误自动重试最多 3 次
- **SCP 上传**: 对临时性错误自动重试最多 3 次
- 识别的临时性错误:
  - EOF during negotiation
  - Connection reset
  - Connection timed out
  - Connection refused
  - Timeout

### 5. 改进错误处理和日志
- 详细的重试日志输出
- 区分成功、失败和重试状态
- 记录每个操作的详细结果

## 修复的文件和函数

### ssh_bridge.py
1. `SSHConnection.connect()` - 增强主 SSH 连接稳定性
2. `_check_and_start_monitor_service()` - 使用 SCP 替代 SFTP 上传文件

### offline_server.py
1. `upload_images_range_from_robot()` - 图片批量上传，增加重试机制
2. `pull_robot_logs()` - 日志拉取，优化 SSH 选项

## 测试验证

### 测试 1: SSH 和 rsync 连接
```bash
bash test_rsync_fix.sh
```
结果:
- ✓ SSH 连接测试通过
- ✓ rsync 命令格式测试通过

### 测试 2: SCP 上传
```bash
bash test_scp_upload.sh
```
结果:
- ✓ 远程目录创建
- ✓ 脚本文件上传
- ✓ 权限设置
- ✓ 服务文件上传
- ✓ 文件验证

## 使用说明

### 重启服务
```bash
# 停止旧服务
pkill -f offline_server.py
pkill -f ssh_bridge.py

# 启动新服务
cd /home/youfeng/CLionProjects/07_openclaw_auto/project/perception_streaming-master-80b4b0d5e580c3b80e50eea2d3719aad56d8d808

# 启动 offline_server
nohup python3 robot_monitor/offline_server.py > /tmp/offline_server.log 2>&1 &

# 启动 ssh_bridge
nohup python3 robot_monitor/ssh_bridge.py > /tmp/ssh_bridge.log 2>&1 &

# 验证服务运行
ps aux | grep -E "offline_server|ssh_bridge" | grep -v grep
netstat -tlnp | grep -E "8769|8765"
```

### 在界面上使用
1. **刷新浏览器页面**以连接到新的服务器
2. 尝试以下功能:
   - 📤 上传图片 (StereoAnalysis2Panel)
   - 🔬 离线 debug
   - 监控服务部署
3. 如果遇到错误，系统会自动重试最多 3 次

## 技术细节

### 为什么使用 SCP 而不是 SFTP?
1. **SFTP 子系统不可用**: 测试发现远程服务器的 SFTP 子系统返回 "EOF during negotiation" 错误
2. **SCP 更可靠**: SCP 使用标准的 SSH 连接，不依赖 SFTP 子系统
3. **功能等效**: 对于简单的文件上传，SCP 完全可以替代 SFTP

### SSH Keepalive 机制
- `ServerAliveInterval=10`: 客户端每 10 秒发送一个空包给服务器
- `ServerAliveCountMax=3`: 如果连续 3 次没有响应，则断开连接
- 这样可以在 30 秒内检测到连接断开，而不是等待系统默认的超时时间

### 重试策略
- **指数退避**: 每次重试前等待 2 秒
- **最大重试次数**: 3 次
- **智能重试**: 只对临时性错误重试，非临时性错误立即失败

## 注意事项
- 修复后的代码已经在运行中
- 如果仍然遇到问题，请检查：
  1. SSH 密钥文件是否存在且权限正确 (chmod 600)
  2. 网络连接是否稳定
  3. 远程服务器是否正常运行
  4. 端口是否可访问
  5. 远程服务器磁盘空间是否充足

## 相关文件
- `robot_monitor/ssh_bridge.py` - SSH 连接和 SCP 上传
- `robot_monitor/offline_server.py` - rsync 下载和日志拉取
- `test_rsync_fix.sh` - rsync 测试脚本
- `test_scp_upload.sh` - SCP 上传测试脚本
- `SSH_FIX_README.md` - 本文档
