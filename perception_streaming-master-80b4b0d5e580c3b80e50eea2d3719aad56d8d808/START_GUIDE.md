# 启动指南

## 问题说明

由于项目中 `data/` 目录包含大量文件和符号链接，直接运行 `npm run dev` 可能会遇到 `EMFILE: too many open files` 错误。

## 解决方案

### 方法 1: 使用启动脚本（推荐）

```bash
./start.sh
```

### 方法 2: 手动设置环境变量

```bash
CHOKIDAR_USEPOLLING=false npm run dev
```

## 验证服务

运行测试脚本验证所有 API 正常工作：

```bash
./test_api.sh
```

应该看到：
- ✓ 服务器进程运行中
- ✓ 配置 API 正常
- ✓ Camera bag 文件列表 API 返回 9 个文件
- ✓ 图片文件可访问（JPEG）
- ✓ 点云文件可访问（PCD）

## 访问应用

浏览器打开：http://localhost:5173/

## 故障排除

如果仍然遇到问题：

1. 检查进程是否运行：
   ```bash
   ps aux | grep -E "(vite|offline_server|ssh_bridge)" | grep -v grep
   ```

2. 查看日志：
   ```bash
   tail -f /tmp/vite_fixed.log
   ```

3. 重启所有服务：
   ```bash
   pkill -f "vite|offline_server|ssh_bridge"
   ./start.sh
   ```
