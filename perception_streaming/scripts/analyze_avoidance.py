#!/usr/bin/env python3
"""
避障日志深度分析脚本
"""

import argparse
import json
import subprocess
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict


class AvoidanceAnalyzer:
    def __init__(self, config: Dict, machine_name: str, date: str):
        self.config = config
        self.machine_config = config['machines'][machine_name]
        self.analysis_config = config['analysis']
        self.date = date
        self.ssh_cmd = self._build_ssh_cmd()

        # 分析结果
        self.results = {
            'blade_stall': [],
            'uplift_trigger': [],
            'perception_trigger': [],
            'localization_failure': [],
            'goal_cancellation': []
        }

    def _build_ssh_cmd(self) -> List[str]:
        """构建SSH命令前缀"""
        return [
            'ssh',
            '-i', self.machine_config['ssh_key'],
            f"{self.machine_config['user']}@{self.machine_config['host']}",
            '-p', str(self.machine_config['port'])
        ]

    def _run_ssh_command(self, command: str) -> str:
        """执行SSH命令"""
        full_cmd = self.ssh_cmd + [command]
        try:
            result = subprocess.run(full_cmd, capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"SSH命令执行失败: {e}")
            return ""

    def analyze_chassis_logs(self, timestamps: List[str]):
        """分析底盘日志"""
        print("  分析底盘日志...")
        log_pattern = f"{self.machine_config['log_base_path']}/chassis_node_*.log"

        # 查找刀片警告
        for ts in timestamps:
            time_str = self._format_timestamp_for_grep(ts)
            cmd = f"grep '{time_str}' {log_pattern} 2>/dev/null | grep -E 'cut motor_warning|fault_stall_flg|chassis_incident' | head -20"
            output = self._run_ssh_command(cmd)

            if 'motor_warning' in output or 'fault_stall' in output:
                self.results['blade_stall'].append({
                    'timestamp': ts,
                    'details': output.strip()
                })

        # 查找uplift传感器触发
        for ts in timestamps:
            time_str = self._format_timestamp_for_grep(ts)
            cmd = f"grep '{time_str}' {log_pattern} 2>/dev/null | grep -c 'hall_uplift' || echo 0"
            count = int(self._run_ssh_command(cmd).strip())

            if count > self.analysis_config['uplift_count_threshold']:
                self.results['uplift_trigger'].append({
                    'timestamp': ts,
                    'count': count
                })

    def analyze_navigation_logs(self, timestamps: List[str]):
        """分析导航日志"""
        print("  分析导航日志...")
        log_pattern = f"{self.machine_config['log_base_path']}/nav2_single_node_navigator_*.log"

        for ts in timestamps:
            time_str = self._format_timestamp_for_grep(ts)
            cmd = f"grep '{time_str}' {log_pattern} 2>/dev/null | grep -E 'Goal was canceled|Speed limit' | head -10"
            output = self._run_ssh_command(cmd)

            if 'Goal was canceled' in output:
                self.results['goal_cancellation'].append({
                    'timestamp': ts,
                    'details': output.strip()
                })

    def analyze_decision_logs(self, timestamps: List[str]):
        """分析决策日志"""
        print("  分析决策日志...")
        log_pattern = f"{self.machine_config['log_base_path']}/robot_decision_*.log"

        for ts in timestamps:
            time_str = self._format_timestamp_for_grep(ts)
            cmd = f"grep '{time_str}' {log_pattern} 2>/dev/null | grep -E 'Work:AVOIDING|Error_code|Can not get transform' | head -10"
            output = self._run_ssh_command(cmd)

            if 'Can not get transform' in output:
                self.results['localization_failure'].append({
                    'timestamp': ts,
                    'details': output.strip()
                })

    def analyze_coverage_logs(self, timestamps: List[str]):
        """分析覆盖导航日志"""
        print("  分析覆盖导航日志...")
        log_pattern = f"{self.machine_config['log_base_path']}/coverage_navigator_server_*.log"

        for ts in timestamps:
            time_str = self._format_timestamp_for_grep(ts)
            cmd = f"grep '{time_str}' {log_pattern} 2>/dev/null | grep -E 'cut motor maybe blocked|COVER_OBSTACLE_AVOIDING' | head -10"
            output = self._run_ssh_command(cmd)

            if 'cut motor maybe blocked' in output:
                # 这是刀片堵转的确认证据
                for item in self.results['blade_stall']:
                    if item['timestamp'] == ts:
                        item['confirmed'] = True
                        break

    def _format_timestamp_for_grep(self, ts: str) -> str:
        """将时间戳格式化为grep可用的格式"""
        # ts格式: 20260414_031457_7
        # 转换为: 2026/04/14 03:14:57
        if len(ts) < 15:
            return ts

        year = ts[0:4]
        month = ts[4:6]
        day = ts[6:8]
        hour = ts[9:11]
        minute = ts[11:13]
        second = ts[13:15]

        return f"{year}/{month}/{day} {hour}:{minute}:{second}"

    def generate_report(self, output_dir: Path) -> str:
        """生成分析报告"""
        print("  生成详细报告...")

        # 统计各类原因
        blade_stall_count = len(self.results['blade_stall'])
        uplift_count = len(self.results['uplift_trigger'])
        perception_count = len(self.results['perception_trigger'])
        localization_count = len(self.results['localization_failure'])

        total = blade_stall_count + uplift_count + perception_count + localization_count
        if total == 0:
            total = 1  # 避免除零

        # 生成报告
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = output_dir / f"avoidance_{self.date}_{timestamp}.md"

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"# 避障分析报告\n\n")
            f.write(f"**机器**: {self.machine_config['name']}\n")
            f.write(f"**日期**: {self.date}\n")
            f.write(f"**分析时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write(f"## 执行摘要\n\n")
            f.write(f"- 刀片电机堵转: {blade_stall_count}次 ({blade_stall_count*100//total}%)\n")
            f.write(f"- 底盘抬升触发: {uplift_count}次 ({uplift_count*100//total}%)\n")
            f.write(f"- 感知系统触发: {perception_count}次 ({perception_count*100//total}%)\n")
            f.write(f"- 定位失败: {localization_count}次 ({localization_count*100//total}%)\n\n")

            # 详细分析
            if blade_stall_count > 0:
                f.write(f"## 1. 刀片电机堵转 ({blade_stall_count}次)\n\n")
                f.write(f"**主要原因**: 刀片电机堵转是最常见的避障触发原因\n\n")
                f.write(f"**触发链路**:\n")
                f.write(f"```\n")
                f.write(f"底盘检测堵转 → 覆盖导航进入AVOIDING → 决策层切换状态 → \n")
                f.write(f"导航取消目标 → 感知保存现场图片\n")
                f.write(f"```\n\n")

                f.write(f"**典型案例**:\n\n")
                for i, item in enumerate(self.results['blade_stall'][:3], 1):
                    f.write(f"### 案例 {i}: {item['timestamp']}\n\n")
                    f.write(f"```\n{item['details'][:500]}\n```\n\n")

            if uplift_count > 0:
                f.write(f"## 2. 底盘抬升传感器 ({uplift_count}次)\n\n")
                f.write(f"**可能原因**: 不平整地形、障碍物碰撞\n\n")
                for item in self.results['uplift_trigger'][:5]:
                    f.write(f"- {item['timestamp']}: 触发{item['count']}次\n")
                f.write(f"\n")

            if localization_count > 0:
                f.write(f"## 3. 定位失败 ({localization_count}次)\n\n")
                f.write(f"**可能原因**: 地图漂移、TF变换失败\n\n")

            # 优化建议
            f.write(f"## 优化建议\n\n")
            if blade_stall_count > 0:
                f.write(f"1. **刀片高度调整**: 提高刀片离地高度2-3cm\n")
                f.write(f"2. **草密度检测**: 在高密度区域降低速度\n")
                f.write(f"3. **错误处理**: 刀片堵转后立即停止，避免重复尝试\n")

            if uplift_count > 0:
                f.write(f"4. **地形适应**: 改进抬升传感器阈值\n")
                f.write(f"5. **路径规划**: 避开不平整区域\n")

            f.write(f"\n## 附件\n\n")
            f.write(f"- 配置文件: config/machine_config.json\n")
            f.write(f"- 时间戳列表: logs/timestamps_{self.date}.txt\n")

        return str(report_file)


def main():
    parser = argparse.ArgumentParser(description='避障日志深度分析')
    parser.add_argument('--machine', required=True, help='机器名称')
    parser.add_argument('--date', required=True, help='日期 (YYYYMMDD)')
    parser.add_argument('--time-range', help='时间范围 (HH:MM-HH:MM)')
    parser.add_argument('--config', required=True, help='配置文件路径')
    parser.add_argument('--timestamps', required=True, help='时间戳文件路径')
    parser.add_argument('--output', required=True, help='输出目录')

    args = parser.parse_args()

    # 加载配置
    with open(args.config, 'r') as f:
        config = json.load(f)

    # 加载时间戳
    with open(args.timestamps, 'r') as f:
        timestamps = [line.strip() for line in f if line.strip()]

    # 创建分析器
    analyzer = AvoidanceAnalyzer(config, args.machine, args.date)

    # 执行分析
    print("  ✓ 底盘日志分析...")
    analyzer.analyze_chassis_logs(timestamps)

    print("  ✓ 导航日志分析...")
    analyzer.analyze_navigation_logs(timestamps)

    print("  ✓ 决策日志分析...")
    analyzer.analyze_decision_logs(timestamps)

    print("  ✓ 覆盖导航日志分析...")
    analyzer.analyze_coverage_logs(timestamps)

    # 生成报告
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_file = analyzer.generate_report(output_dir)

    print(f"  ✓ 报告已保存: {report_file}")


if __name__ == '__main__':
    main()
