# 避障分析工具 - 项目总结

## 已创建的文件

### 文档
- `AVOIDANCE_ANALYSIS_README.md` - 完整的分析流程文档
- `QUICKSTART.md` - 快速开始指南
- `EXAMPLES.md` - 使用示例集合
- `requirements.txt` - Python依赖列表

### 配置
- `config/machine_config.json` - 机器配置文件（包含test_machine_1示例）

### 脚本
- `scripts/analyze_avoidance.sh` - 主分析脚本（Bash）
- `scripts/analyze_avoidance.py` - 深度分析脚本（Python）
- `scripts/test_setup.sh` - 配置测试脚本

### 目录
- `reports/` - 分析报告输出目录
- `logs/` - 临时日志缓存目录

## 快速使用

### 1. 测试配置
```bash
./scripts/test_setup.sh
```

### 2. 运行分析
```bash
# 使用已配置的test_machine_1
./scripts/analyze_avoidance.sh test_machine_1

# 或指定日期
./scripts/analyze_avoidance.sh test_machine_1 20260414
```

### 3. 查看报告
```bash
cat reports/avoidance_*.md
```

## 核心功能

### 自动化分析流程
1. **数据收集**: 自动连接机器，列出避障图片，提取时间戳
2. **日志关联**: 分析5类日志（感知、导航、决策、底盘、覆盖导航）
3. **根因分析**: 识别避障真实原因（刀片堵转、抬升传感器、感知触发等）
4. **报告生成**: 生成Markdown格式的详细分析报告

### 支持的避障原因分类
- 刀片电机堵转（最常见）
- 底盘抬升传感器触发
- 碰撞检测
- 地图漂移/定位失败
- 虚拟边界违规
- 感知系统检测到障碍物

## 配置说明

### 机器配置
```json
{
  "name": "显示名称",
  "host": "IP地址",
  "port": SSH端口,
  "ssh_key": "SSH密钥路径",
  "user": "用户名",
  "log_base_path": "/userdata/log_dir/ros2_log",
  "image_base_path": "/userdata/bestmow_data/image_save_path"
}
```

### 分析阈值
```json
{
  "blade_current_threshold": 1500,      // 刀片电流阈值(mA)
  "uplift_count_threshold": 50,         // 抬升传感器触发次数阈值
  "perception_distance_threshold": 5.0, // 感知距离阈值(m)
  "speed_limit_threshold": 0.05,        // 速度限制阈值(m/s)
  "image_sync_delay_threshold": 0.2     // 图像同步延迟阈值(s)
}
```

## 扩展性

### 添加新机器
编辑 `config/machine_config.json`，添加新的机器配置即可。

### 自定义分析逻辑
修改 `scripts/analyze_avoidance.py`，添加新的分析方法。

### 集成到监控系统
参考 `EXAMPLES.md` 中的监控集成示例。

## 维护建议

### 定期清理
```bash
# 删除30天前的报告
find reports/ -name "*.md" -mtime +30 -delete
find logs/ -name "*.txt" -mtime +30 -delete
```

### 备份配置
```bash
# 备份配置文件
cp config/machine_config.json config/machine_config.json.bak
```

### 更新文档
当添加新功能时，记得更新相应的文档。

## 已知限制

1. **SSH连接**: 需要配置SSH密钥认证
2. **日志格式**: 依赖特定的日志格式，如果日志格式变化需要更新脚本
3. **Python版本**: 需要Python 3.6+
4. **系统依赖**: 需要jq和ssh命令

## 未来改进方向

1. **可视化**: 添加图表展示避障趋势
2. **实时监控**: 支持实时日志流分析
3. **告警集成**: 集成到企业微信、钉钉等告警系统
4. **Web界面**: 提供Web UI进行交互式分析
5. **机器学习**: 使用ML预测避障模式

## 技术栈

- **Shell**: Bash脚本用于流程控制
- **Python**: 深度日志分析
- **jq**: JSON配置解析
- **SSH**: 远程机器连接
- **Markdown**: 报告格式

## 贡献指南

欢迎贡献代码和文档！

### 提交流程
1. Fork项目
2. 创建特性分支
3. 提交更改
4. 发起Pull Request

### 代码规范
- Shell脚本遵循Google Shell Style Guide
- Python代码遵循PEP 8
- 添加适当的注释和文档

## 许可证

本项目采用MIT许可证。

## 联系方式

如有问题或建议，请通过以下方式联系:
- 提交Issue
- 发送邮件
- 内部沟通渠道

## 致谢

感谢所有贡献者和使用者的反馈！

---

**最后更新**: 2026-04-14
**版本**: 1.0.0
