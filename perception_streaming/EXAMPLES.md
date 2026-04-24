# 使用示例

本文档展示如何使用避障分析工具进行日常分析。

## 示例1: 分析今天的避障日志

```bash
# 使用test_machine_1配置
./scripts/analyze_avoidance.sh test_machine_1
```

**输出**:
```
=== 避障日志分析 ===
[INFO] 机器: 测试机1 (120.25.121.3:10286)
[INFO] 日期: 20260414

[✓] SSH连接正常
[✓] 找到 129 张避障图片
[✓] DSG避障: 93次
[✓] SUB避障: 36次

[✓] 分析完成！
```

**查看报告**:
```bash
cat reports/avoidance_20260414_*.md
```

## 示例2: 分析指定日期

```bash
# 分析2026年4月14日的日志
./scripts/analyze_avoidance.sh test_machine_1 20260414
```

## 示例3: 分析指定时间段

```bash
# 只分析凌晨3:14到3:36的避障
./scripts/analyze_avoidance.sh test_machine_1 20260414 "03:14-03:36"
```

## 示例4: 添加新机器

编辑 `config/machine_config.json`:

```json
{
  "machines": {
    "my_robot": {
      "name": "我的割草机器人",
      "host": "192.168.1.100",
      "port": 22,
      "ssh_key": "/home/user/.ssh/id_rsa",
      "user": "root",
      "log_base_path": "/userdata/log_dir/ros2_log",
      "image_base_path": "/userdata/bestmow_data/image_save_path"
    }
  }
}
```

然后运行:
```bash
./scripts/analyze_avoidance.sh my_robot
```

## 示例5: 批量分析多台机器

```bash
#!/bin/bash
# batch_analyze.sh

MACHINES=("robot1" "robot2" "robot3")
DATE=$(date +%Y%m%d)

for machine in "${MACHINES[@]}"; do
    echo "=== 分析 $machine ==="
    ./scripts/analyze_avoidance.sh "$machine" "$DATE"
    echo ""
done

# 汇总报告
echo "=== 汇总 ==="
for machine in "${MACHINES[@]}"; do
    REPORT=$(ls -t reports/*${machine}*.md 2>/dev/null | head -1)
    if [ -f "$REPORT" ]; then
        echo "$machine:"
        grep "执行摘要" -A 5 "$REPORT"
        echo ""
    fi
done
```

## 示例6: 定时任务

添加到crontab，每天早上9点自动分析前一天的日志:

```bash
# 编辑crontab
crontab -e

# 添加以下行
0 9 * * * cd /path/to/project && ./scripts/analyze_avoidance.sh test_machine_1 $(date -d "yesterday" +\%Y\%m\%d) >> /var/log/avoidance_analysis.log 2>&1
```

## 示例7: 对比分析

分析最近7天的趋势:

```bash
#!/bin/bash
# trend_analysis.sh

echo "最近7天避障统计:"
echo "日期       | DSG | SUB | 总计"
echo "-----------|-----|-----|-----"

for i in {6..0}; do
    DATE=$(date -d "$i days ago" +%Y%m%d)
    ./scripts/analyze_avoidance.sh test_machine_1 $DATE > /dev/null 2>&1

    REPORT=$(ls -t reports/avoidance_${DATE}_*.md 2>/dev/null | head -1)
    if [ -f "$REPORT" ]; then
        DSG=$(grep "DSG避障:" "$REPORT" | grep -oP '\d+(?=次)')
        SUB=$(grep "SUB避障:" "$REPORT" | grep -oP '\d+(?=次)')
        TOTAL=$((DSG + SUB))
        echo "$DATE | $DSG | $SUB | $TOTAL"
    fi
done
```

## 示例8: 导出避障图片

```bash
#!/bin/bash
# export_images.sh

MACHINE=$1
DATE=$2
OUTPUT_DIR=$3

# 读取配置
CONFIG_FILE="config/machine_config.json"
HOST=$(cat "$CONFIG_FILE" | jq -r ".machines.\"$MACHINE\".host")
PORT=$(cat "$CONFIG_FILE" | jq -r ".machines.\"$MACHINE\".port")
SSH_KEY=$(cat "$CONFIG_FILE" | jq -r ".machines.\"$MACHINE\".ssh_key")
USER=$(cat "$CONFIG_FILE" | jq -r ".machines.\"$MACHINE\".user")
IMAGE_PATH=$(cat "$CONFIG_FILE" | jq -r ".machines.\"$MACHINE\".image_base_path")

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 使用rsync同步图片
rsync -avz -e "ssh -i $SSH_KEY -p $PORT" \
    "$USER@$HOST:$IMAGE_PATH/$DATE/" \
    "$OUTPUT_DIR/"

echo "图片已导出到: $OUTPUT_DIR"
```

使用:
```bash
./export_images.sh test_machine_1 20260414 /tmp/avoidance_images
```

## 示例9: 生成HTML报告

```bash
#!/bin/bash
# generate_html_report.sh

REPORT_MD=$1
REPORT_HTML="${REPORT_MD%.md}.html"

# 使用pandoc转换（需要安装pandoc）
if command -v pandoc &> /dev/null; then
    pandoc "$REPORT_MD" -o "$REPORT_HTML" \
        --standalone \
        --css=style.css \
        --metadata title="避障分析报告"

    echo "HTML报告已生成: $REPORT_HTML"
else
    echo "请安装pandoc: sudo apt-get install pandoc"
fi
```

## 示例10: 集成到监控系统

```python
#!/usr/bin/env python3
# monitor_integration.py

import subprocess
import json
import requests
from datetime import datetime

def analyze_and_alert(machine, date):
    """分析避障并发送告警"""

    # 运行分析
    result = subprocess.run(
        ['./scripts/analyze_avoidance.sh', machine, date],
        capture_output=True,
        text=True
    )

    # 解析报告
    report_file = f"reports/avoidance_{date}_*.md"
    # ... 解析逻辑 ...

    # 如果避障次数超过阈值，发送告警
    if total_avoidance > 100:
        send_alert(machine, total_avoidance, report_file)

def send_alert(machine, count, report):
    """发送告警到监控系统"""
    payload = {
        'machine': machine,
        'count': count,
        'report': report,
        'timestamp': datetime.now().isoformat()
    }

    # 发送到Webhook
    requests.post('https://your-webhook-url', json=payload)

if __name__ == '__main__':
    analyze_and_alert('test_machine_1', datetime.now().strftime('%Y%m%d'))
```

## 常见问题

### Q: 如何只分析刀片堵转的避障？

修改Python脚本，添加过滤条件。

### Q: 如何导出JSON格式的报告？

在Python脚本中添加JSON输出选项。

### Q: 如何可视化避障趋势？

使用matplotlib或其他可视化工具处理报告数据。

## 更多示例

查看 `examples/` 目录获取更多使用示例。
