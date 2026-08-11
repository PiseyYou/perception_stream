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

## A/B 影子预标注与盲评

1. 在“预标注”页选择 **A/B 影子验证**，上传或选择一个图片目录后启动。系统会冻结该批图片，并分别创建基线与候选 CVAT 任务；默认模型不会被替换。
2. 两个分支均完成帧校验、标注导入后，在该运行详情中点击“匿名盲评”。系统会签发一个单次评审链接；每位评审者使用各自链接，页面只展示 X/Y 覆盖图，不显示任务、模型或文件路径。链接是访问能力凭据，请通过受控渠道发送。
3. 为全部抽样图片选择 `X better`、`Y better`、`tie` 或 `undecidable` 后提交。评估阈值为至少 24 个有效判断，候选相对基线至少领先 20 个百分点；否则为“无结论”。
4. 仅运行创建者可点击“揭示结果（所有者）”，随后可访问已揭示的 CVAT 任务链接。

候选权重、哈希、GPU 与标签契约在 `robot_monitor/prelabel_pipeline/prelabel_config.yaml` 的 `alpha50_candidate` 中固定。远程 CVAT 当前明确使用私网 HTTP opt-in；部署 TLS 后应改为 `scheme: https` 并移除 `allow_insecure_private_http`。

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
