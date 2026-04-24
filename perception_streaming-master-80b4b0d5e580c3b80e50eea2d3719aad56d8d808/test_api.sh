#!/bin/bash

echo "=== 测试后端服务 ==="
echo ""

echo "1. 检查服务器进程..."
ps aux | grep -E "(offline_server|ssh_bridge)" | grep -v grep
echo ""

echo "2. 测试配置 API..."
curl -s "http://localhost:8769/offline/config" | python3 -m json.tool
echo ""

echo "3. 测试 camera bag 文件列表 API..."
curl -s "http://localhost:8769/offline/list_camera_bag_files?bag_dir=data/bag_debug/0111/0327/rosbag_LK-MR6P1US000111_camera_202603220059" | python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"OK: {d['ok']}, Files: {len(d.get('files', []))}\")"
echo ""

echo "4. 测试图片文件访问..."
curl -s "http://localhost:8769/offline/local_file?path=data/bag_debug/0111/0327/rosbag_LK-MR6P1US000111_camera_202603220059/bag_extract_camera/bag_extract_stereo/match_0000_ts1774112357158060009_245917_158.jpg" | file -
echo ""

echo "5. 测试点云文件访问..."
curl -s "http://localhost:8769/offline/local_file?path=data/bag_debug/0111/0327/rosbag_LK-MR6P1US000111_camera_202603220059/bag_extract_camera/bag_extract_pcd/match_0000_ts1774112357158060009_245917_158.pcd" | head -5
echo ""

echo "=== 测试完成 ==="
