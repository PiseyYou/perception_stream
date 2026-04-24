# Perception Process

割草机器人感知系统开发与调试工作区

## 项目概述

本仓库包含割草机器人感知系统的完整开发环境，包括实时监控平台、离线调试工具和相关脚本。

## 目录结构

```
perception_process/
├── perception_streaming/       # 主项目
│   ├── src/                    # 前端源码（Vue 3 + TypeScript）
│   ├── robot_monitor/          # 后端服务（Python）
│   ├── stereo_perception_multi2_offline_test/  # 双目感知离线测试工具（C++）
│   ├── start.sh                # 一键启动脚本
│   └── README.md               # 详细项目文档
├── logs/                       # 运行日志
└── perception_streaming_*.tar.gz  # 项目备份
```

## 快速开始

进入主项目目录：

```bash
cd perception_streaming
```

查看详细的安装和使用说明：

```bash
cat README.md
```

一键启动所有服务：

```bash
./start.sh
```

## 主要功能

- **实时监控**：视频流、点云可视化、避障监控、日志控制台
- **离线调试**：单目测试、Bag包分析、日志分析、双目分析
- **双目离线测试**：C++ 离线处理工具，支持点云生成、障碍物检测、模式切换
- **高级特性**：点云过滤、SFTP断点续传、端口映射、批量上传校验
- **避障监控**：实时障碍物检测与可视化、障碍物类型分类、距离监控
- **日志获取面板**：支持远程日志拉取、自动解压、目录浏览、文件预览
- **双目分析增强**：支持 DSG/PCD 文件批量处理、自动分类、可视化展示

## 技术栈

- 前端：Vue 3 + TypeScript + Vite + Three.js
- 后端：Python 3.10+ + WebSocket + SSE
- 通信：Agora RTC、MQTT、SSH隧道

## 支持设备

- LK-MR2P1US000015/16/113/115
- LK-MR6P1US000123/124/286

## 更多信息

详细文档请参考主项目目录中的 README.md 和相关文档。
