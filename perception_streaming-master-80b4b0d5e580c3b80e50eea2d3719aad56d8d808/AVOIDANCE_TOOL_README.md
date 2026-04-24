# 避障日志分析工具

一个标准化的避障日志分析工具，用于快速诊断机器人避障的真实原因。

## 特性

- ✅ 自动化数据收集和日志关联
- ✅ 多维度根因分析（刀片堵转、传感器触发、感知系统等）
- ✅ 支持多机器配置管理
- ✅ 生成详细的Markdown分析报告
- ✅ 可扩展的分析框架
- ✅ 命令行友好的交互界面

## 快速开始

### 1. 测试配置

```bash
./scripts/test_setup.sh
```

### 2. 配置机器

编辑 `config/machine_config.json`:

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

### 3. 运行分析

```bash
# 分析今天的日志
./scripts/analyze_avoidance.sh my_robot

# 分析指定日期
./scripts/analyze_avoidance.sh my_robot 20260414

# 分析指定时间段
./scripts/analyze_avoidance.sh my_robot 20260414 "03:14-03:36"
```

### 4. 查看报告

```bash
cat reports/avoidance_*.md
```

## 文档

- 📖 [完整文档](AVOIDANCE_ANALYSIS_README.md) - 详细的分析流程和方法论
- 🚀 [快速开始](QUICKSTART.md) - 快速上手指南
- 💡 [使用示例](EXAMPLES.md) - 各种使用场景示例
- 📊 [项目总结](PROJECT_SUMMARY.md) - 项目概览和技术细节

## 目录结构

```
.
├── AVOIDANCE_ANALYSIS_README.md    # 完整文档
├── QUICKSTART.md                   # 快速开始
├── EXAMPLES.md                     # 使用示例
├── PROJECT_SUMMARY.md              # 项目总结
├── config/
│   └── machine_config.json         # 机器配置
├── scripts/
│   ├── analyze_avoidance.sh        # 主分析脚本
│   ├── analyze_avoidance.py        # Python分析脚本
│   └── test_setup.sh               # 配置测试
├── reports/                        # 分析报告输出
├── logs/                           # 临时日志缓存
└── requirements.txt                # Python依赖
```

## 分析流程

```
1. 数据收集
   ├── 连接远程机器
   ├── 列出避障图片
   └── 提取时间戳

2. 日志关联分析
   ├── 感知日志 (stereo_perception_multi)
   ├── 导航日志 (nav2_single_node_navigator)
   ├── 决策日志 (robot_decision)
   ├── 底盘日志 (chassis_node)
   └── 覆盖导航日志 (coverage_navigator_server)

3. 根因分析
   ├── 刀片电机堵转
   ├── 底盘抬升传感器
   ├── 碰撞检测
   ├── 地图漂移/定位失败
   ├── 虚拟边界违规
   └── 感知系统触发

4. 生成报告
   ├── 执行摘要
   ├── 详细分析
   ├── 典型案例
   └── 优化建议
```

## 依赖

- jq (JSON处理)
- ssh (远程连接)
- Python 3.6+ (深度分析)

安装:
```bash
sudo apt-get install jq ssh
pip3 install -r requirements.txt
```

## 使用场景

### 日常检查
```bash
./scripts/analyze_avoidance.sh my_robot
```

### 历史分析
```bash
for i in {0..6}; do
    DATE=$(date -d "$i days ago" +%Y%m%d)
    ./scripts/analyze_avoidance.sh my_robot $DATE
done
```

### 批量分析
```bash
for machine in robot1 robot2 robot3; do
    ./scripts/analyze_avoidance.sh $machine
done
```

## 报告示例

```markdown
# 避障分析报告

**机器**: 测试机1
**日期**: 2026-04-14

## 执行摘要

- 刀片电机堵转: 93次 (72%)
- 底盘抬升触发: 36次 (28%)
- 感知系统触发: 0次 (0%)

## 详细分析

### 1. 刀片电机堵转 (93次)

**触发链路**:
```
底盘检测堵转 → 覆盖导航进入AVOIDING → 
决策层切换状态 → 导航取消目标 → 感知保存现场图片
```

## 优化建议

1. 刀片高度调整: 提高2-3cm
2. 草密度检测: 降低速度
3. 错误处理: 立即停止避免重复
```

## 常见问题

### Q: SSH连接失败？
检查SSH密钥权限: `chmod 600 /path/to/key`

### Q: 未找到避障图片？
检查日期格式 (YYYYMMDD) 和路径配置

### Q: 如何添加新机器？
编辑 `config/machine_config.json` 添加配置

更多问题请查看 [QUICKSTART.md](QUICKSTART.md)

## 贡献

欢迎提交Issue和Pull Request！

## 许可证

MIT License

## 更新日志

### v1.0.0 (2026-04-14)
- 初始版本发布
- 支持基本的避障分析功能
- 完整的文档和示例

---

**快速链接**: [完整文档](AVOIDANCE_ANALYSIS_README.md) | [快速开始](QUICKSTART.md) | [使用示例](EXAMPLES.md)
