# 避障分析快速开始指南

## 1. 首次使用配置

### 安装依赖
```bash
# 安装系统依赖
sudo apt-get install jq ssh

# Python依赖（当前版本无需额外依赖）
pip3 install -r requirements.txt
```

### 配置机器信息
编辑 `config/machine_config.json`，添加你的机器：

```json
{
  "machines": {
    "my_robot": {
      "name": "我的机器人",
      "host": "192.168.1.100",
      "port": 22,
      "ssh_key": "/path/to/ssh/key",
      "user": "root",
      "log_base_path": "/userdata/log_dir/ros2_log",
      "image_base_path": "/userdata/bestmow_data/image_save_path"
    }
  }
}
```

## 2. 运行分析

### 基本用法
```bash
# 分析今天的避障日志
./scripts/analyze_avoidance.sh my_robot

# 分析指定日期
./scripts/analyze_avoidance.sh my_robot 20260414

# 分析指定时间段
./scripts/analyze_avoidance.sh my_robot 20260414 "03:14-03:36"
```

### 输出示例
```
=== 避障日志分析 ===
[INFO] 机器: 我的机器人 (192.168.1.100:22)
[INFO] 日期: 20260414

[INFO] 测试SSH连接...
[✓] SSH连接正常

[INFO] [1/4] 数据收集...
[✓] 找到 129 张避障图片
[✓] DSG避障: 93次
[✓] SUB避障: 36次

[INFO] [2/4] 日志关联分析...
  分析底盘日志...
  分析导航日志...
  分析决策日志...
  分析覆盖导航日志...

[INFO] [3/4] 生成报告...
[✓] 报告已保存到: reports/

[✓] 分析完成！
```

## 3. 查看报告

报告保存在 `reports/` 目录：
```bash
# 查看最新报告
ls -lt reports/ | head -5

# 打开报告
cat reports/avoidance_20260414_103000.md
```

## 4. 常见场景

### 场景1: 每日例行检查
```bash
# 创建每日检查脚本
cat > daily_check.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d)
./scripts/analyze_avoidance.sh my_robot $DATE
EOF

chmod +x daily_check.sh

# 添加到crontab (每天早上9点执行)
# 0 9 * * * /path/to/daily_check.sh
```

### 场景2: 多机器批量分析
```bash
# 分析多台机器
for machine in robot1 robot2 robot3; do
    echo "分析 $machine..."
    ./scripts/analyze_avoidance.sh $machine
done
```

### 场景3: 历史数据分析
```bash
# 分析过去7天的数据
for i in {0..6}; do
    DATE=$(date -d "$i days ago" +%Y%m%d)
    ./scripts/analyze_avoidance.sh my_robot $DATE
done
```

## 5. 故障排查

### 问题1: SSH连接失败
```bash
# 测试SSH连接
ssh -i /path/to/key user@host -p port "echo 'test'"

# 检查SSH密钥权限
chmod 600 /path/to/ssh/key
```

### 问题2: 未找到避障图片
```bash
# 检查日期格式是否正确 (YYYYMMDD)
# 检查图片路径是否正确
ssh -i /path/to/key user@host "ls /userdata/bestmow_data/image_save_path/"
```

### 问题3: jq命令未找到
```bash
sudo apt-get install jq
```

## 6. 高级用法

### 自定义分析阈值
编辑 `config/machine_config.json` 中的 `analysis` 部分：
```json
{
  "analysis": {
    "blade_current_threshold": 1500,
    "uplift_count_threshold": 50,
    "perception_distance_threshold": 5.0
  }
}
```

### 导出避障图片
```bash
# 创建导出脚本
cat > scripts/export_images.sh << 'EOF'
#!/bin/bash
MACHINE=$1
DATE=$2
OUTPUT_DIR=$3

# 读取配置并导出图片
# (实现略)
EOF
```

## 7. 报告解读

### 报告结构
```markdown
# 避障分析报告
- 执行摘要: 各类原因统计
- 详细分析: 每种原因的详细说明
- 典型案例: 具体日志片段
- 优化建议: 针对性改进建议
```

### 关键指标
- **刀片电机堵转**: 最常见原因，需要调整刀片高度
- **底盘抬升触发**: 地形问题，需要改进路径规划
- **感知系统触发**: 真实障碍物，正常避障
- **定位失败**: 地图或定位问题

## 8. 维护

### 清理旧报告
```bash
# 删除30天前的报告
find reports/ -name "*.md" -mtime +30 -delete
find logs/ -name "*.txt" -mtime +30 -delete
```

### 更新脚本
```bash
# 拉取最新版本
git pull origin master

# 检查配置文件格式
jq . config/machine_config.json
```

## 9. 获取帮助

```bash
# 查看脚本帮助
./scripts/analyze_avoidance.sh

# 查看Python脚本帮助
python3 scripts/analyze_avoidance.py --help
```

## 10. 示例工作流

```bash
# 1. 配置机器
vim config/machine_config.json

# 2. 测试连接
./scripts/analyze_avoidance.sh my_robot

# 3. 查看报告
cat reports/avoidance_*.md | tail -50

# 4. 根据建议优化
# - 调整刀片高度
# - 修改路径规划参数
# - 更新感知阈值

# 5. 持续监控
# 添加到每日检查流程
```
