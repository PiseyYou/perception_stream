# 双目分析上传图片默认 SSH 私钥调整设计

## 背景

“双目分析”页面的“上传图片”按钮通过 `/offline/upload_images_range` 调用后端 `upload_images_range_from_robot()`。该函数使用模块级 `SSH_KEY` 发起 `ssh`/`rsync`，`SSH_KEY` 来自 `robot_monitor/config_loader.py` 的 `get_ssh_key_path()`。

当前 `data/conf/ssh_config.json` 已配置为 `bestmow_rsa_202606`，但 `config_loader.py` 在配置文件缺失时的默认值仍是 `bestmow_rsa_202605`。为避免默认路径回退到旧密钥，需要将默认 SSH 私钥同步为 `bestmow_rsa_202606`。

## 目标

- 双目分析上传图片使用 `data/conf/bestmow_rsa_202606` 作为 SSH 私钥。
- 保持现有 `data/conf/ssh_config.json` 配置入口不变。
- 仅调整默认值，不扩大到其他独立功能或重构配置系统。

## 方案

采用最小修改方案：

1. 修改 `robot_monitor/config_loader.py` 中 `load_ssh_config()` 的默认配置。
2. 将默认 `ssh_key_path` 从 `bestmow_rsa_202605` 改为 `bestmow_rsa_202606`。
3. 保持 `get_ssh_key_path()` 的相对路径转绝对路径逻辑不变。

## 数据流

1. 前端 `src/components/StereoAnalysis2Panel.vue` 调用 `/offline/upload_images_range`。
2. 后端 `robot_monitor/offline_server.py` 调用 `upload_images_range_from_robot()`。
3. `offline_server.py` 的模块级 `SSH_KEY` 调用 `get_ssh_key_path()` 获取密钥路径。
4. `get_ssh_key_path()` 读取 `data/conf/ssh_config.json`；若配置文件缺失，则使用 `config_loader.py` 内的默认值。
5. 默认值调整后，缺省路径解析为 `data/conf/bestmow_rsa_202606`。

## 错误处理

沿用现有错误处理：

- 如果密钥文件不存在或权限不正确，`ssh` / `rsync` 会返回现有 SSH 错误。
- 本次不新增密钥存在性检查，不改变前端错误展示逻辑。
- 因为 `offline_server.py` 在模块加载时设置 `SSH_KEY`，修改后需要重启后端或 Vite dev server 才能让运行中服务重新读取默认值。

## 验证

- 静态检查 `data/conf/ssh_config.json` 仍为 `bestmow_rsa_202606`。
- 静态检查 `robot_monitor/config_loader.py` 默认 `ssh_key_path` 为 `bestmow_rsa_202606`。
- 运行 `python3 robot_monitor/config_loader.py`，确认输出的 SSH Key Path 指向 `data/conf/bestmow_rsa_202606`。

## 范围外

- 不修改 `vite.config.ts` 中 PCL bridge 使用的硬编码密钥。
- 不调整 SSH 端口、主机、用户名。
- 不重构配置加载机制。
