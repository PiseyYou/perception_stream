# 视觉自动标注工作台实施计划

> **面向执行智能体：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐项执行。步骤采用复选框追踪。

**目标：** 创建独立的 `vision_annotation_workbench`，实现图片文件夹导入、候选标注数据契约、确定性 CVAT XML 导出和人工复核清单的可测试最小闭环。

**架构：** 第一期先建立不依赖 GPU 模型的运行编排和数据契约，使用固定夹具模拟模型候选，验证从安全导入到 CVAT 导出的正确性。第二期接入 Mask2Former，第三期接入 Grounding DINO 与 SAM，第四期接入选择性外部视觉复核；每个模型只通过适配器写入统一的提议/候选契约。

**技术栈：** Python 3.11、Typer、Pydantic v2、Pillow、NumPy、PyYAML、pytest；后续阶段使用 PyTorch、Transformers、Detectron2 或等价推理后端。

---

## 文件结构

```text
vision_annotation_workbench/
  pyproject.toml
  README.md
  app/cli.py
  configs/default.yaml
  domain/models.py
  domain/taxonomy.py
  domain/policy.py
  pipelines/ingest.py
  pipelines/run.py
  exporters/cvat_xml.py
  exporters/review_manifest.py
  schemas/candidate.schema.json
  tests/conftest.py
  tests/test_ingest.py
  tests/test_domain_models.py
  tests/test_taxonomy.py
  tests/test_cvat_xml.py
  tests/test_run.py
```

所有新增说明、日志、错误信息、配置注释、测试名和代码注释使用中文。Python 标识符和标准 JSON/CVAT 字段保留英文。

### 任务 1：建立独立项目与开发环境

**文件：**

- 新建：`vision_annotation_workbench/pyproject.toml`
- 新建：`vision_annotation_workbench/README.md`
- 新建：`vision_annotation_workbench/app/__init__.py`
- 新建：`vision_annotation_workbench/app/cli.py`
- 新建：`vision_annotation_workbench/tests/test_cli.py`

- [ ] **步骤 1：编写命令行帮助的失败测试**

```python
def test_cli_显示中文帮助():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "图片文件夹" in result.stdout
```

- [ ] **步骤 2：运行测试并确认失败**

运行：`pytest tests/test_cli.py::test_cli_显示中文帮助 -v`

预期：失败，原因是项目模块尚不存在。

- [ ] **步骤 3：创建最小 Python 包和 Typer CLI**

实现 `vision-annotation --help` 与 `vision-annotation run <图片目录>` 命令；尚未实现推理时应输出中文的“功能尚未配置”错误，而不是伪造成功。

- [ ] **步骤 4：运行测试并确认通过**

运行：`pytest tests/test_cli.py::test_cli_显示中文帮助 -v`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add vision_annotation_workbench
git commit -m "feat: 初始化视觉自动标注工作台"
```

### 任务 2：实现标签体系与版本化数据契约

**文件：**

- 新建：`vision_annotation_workbench/domain/models.py`
- 新建：`vision_annotation_workbench/domain/taxonomy.py`
- 新建：`vision_annotation_workbench/schemas/candidate.schema.json`
- 新建：`vision_annotation_workbench/tests/test_domain_models.py`
- 新建：`vision_annotation_workbench/tests/test_taxonomy.py`

- [ ] **步骤 1：编写候选提议与候选标注的失败测试**

测试 `Proposal` 的归一化框范围、`CandidateAnnotation` 的原图尺寸与 RLE 工件哈希、状态枚举、失败错误码，以及未知标签的拒绝行为。

- [ ] **步骤 2：运行测试并确认失败**

运行：`pytest tests/test_domain_models.py tests/test_taxonomy.py -v`

预期：失败，原因是模型与标签加载器尚未定义。

- [ ] **步骤 3：实现 Pydantic 模型和标签加载器**

从现有 `perception_streaming/robot_monitor/prelabel_pipeline` 的 `labels.csv`、`labels_mapping.yaml` 和导出映射构造规范标签；新增独立标签配置覆盖 `thing_or_stuff`、最小面积、互斥组与高风险标记。模型必须产出可序列化的版本、哈希和来源字段。

- [ ] **步骤 4：运行测试并确认通过**

运行：`pytest tests/test_domain_models.py tests/test_taxonomy.py -v`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add vision_annotation_workbench/domain vision_annotation_workbench/schemas vision_annotation_workbench/tests
git commit -m "feat: 定义标注数据契约和标签体系"
```

### 任务 3：实现安全、确定性的图片文件夹导入

**文件：**

- 新建：`vision_annotation_workbench/pipelines/ingest.py`
- 新建：`vision_annotation_workbench/tests/conftest.py`
- 新建：`vision_annotation_workbench/tests/test_ingest.py`

- [ ] **步骤 1：编写导入失败测试**

覆盖 JPEG/PNG/TIFF/BMP 接受、EXIF 方向归正、RGB 转换、内容哈希去重、损坏图片跳过、目录外符号链接拒绝、递归目录、规范化路径排序和超大图片拒绝。

- [ ] **步骤 2：运行测试并确认失败**

运行：`pytest tests/test_ingest.py -v`

预期：失败，原因是导入函数不存在。

- [ ] **步骤 3：实现 `ingest_folder`**

返回不可变图片清单及每张图片的相对 ID、SHA-256、EXIF 归正后的宽高、状态和错误码。任何拒绝项都写入清单；不跟随逃离输入根目录的符号链接。

- [ ] **步骤 4：运行测试并确认通过**

运行：`pytest tests/test_ingest.py -v`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add vision_annotation_workbench/pipelines/ingest.py vision_annotation_workbench/tests
git commit -m "feat: 添加安全图片文件夹导入"
```

### 任务 4：实现策略校验、确定性融合与复核路由

**文件：**

- 新建：`vision_annotation_workbench/domain/policy.py`
- 新建：`vision_annotation_workbench/pipelines/fuse.py`
- 新建：`vision_annotation_workbench/tests/test_policy.py`
- 新建：`vision_annotation_workbench/tests/test_fuse.py`

- [ ] **步骤 1：编写融合与复核失败测试**

验证同类 `IoU >= 0.70` 的合并、异类互斥转人工复核、`0.85/0.55` 默认阈值、稳定排序的决胜规则、含孔候选转人工复核、失败候选不发布，以及运行种子下外部复核数量不超过 10% 图片和每图 3 个区域。

- [ ] **步骤 2：运行测试并确认失败**

运行：`pytest tests/test_policy.py tests/test_fuse.py -v`

预期：失败，原因是策略和融合函数尚未实现。

- [ ] **步骤 3：实现纯函数策略和融合器**

实现掩码 IoU、状态路由、标签互斥校验、基于运行种子的选择性复核排序。此阶段不调用任何真实模型或 API，使用夹具候选验证业务规则。

- [ ] **步骤 4：运行测试并确认通过**

运行：`pytest tests/test_policy.py tests/test_fuse.py -v`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add vision_annotation_workbench/domain/policy.py vision_annotation_workbench/pipelines/fuse.py vision_annotation_workbench/tests
git commit -m "feat: 添加标注融合与复核策略"
```

### 任务 5：实现 CVAT XML 与人工复核清单导出

**文件：**

- 新建：`vision_annotation_workbench/exporters/cvat_xml.py`
- 新建：`vision_annotation_workbench/exporters/review_manifest.py`
- 新建：`vision_annotation_workbench/tests/test_cvat_xml.py`
- 新建：`vision_annotation_workbench/tests/test_review_manifest.py`

- [ ] **步骤 1：编写导出失败测试**

验证 CVAT for images 1.1 XML 的 `<image>` 文件名/宽高、稳定排序、多边形闭合、标签映射、`source/confidence/review_state/instance_id` 属性；验证含孔、失败和未解决人工复核候选不进入 XML，而进入复核清单。

- [ ] **步骤 2：运行测试并确认失败**

运行：`pytest tests/test_cvat_xml.py tests/test_review_manifest.py -v`

预期：失败，原因是导出器尚未定义。

- [ ] **步骤 3：实现 XML 和 JSON 导出器**

只导出无孔 `accepted` 候选，保留所有非发布候选的工件路径、原因和来源到 JSON 复核清单。XML 内不写入不受 CVAT 1.1 支持的自定义几何格式。

- [ ] **步骤 4：运行测试并确认通过**

运行：`pytest tests/test_cvat_xml.py tests/test_review_manifest.py -v`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add vision_annotation_workbench/exporters vision_annotation_workbench/tests
git commit -m "feat: 添加 CVAT 与复核清单导出"
```

### 任务 6：编排端到端运行与可恢复清单

**文件：**

- 新建：`vision_annotation_workbench/pipelines/run.py`
- 修改：`vision_annotation_workbench/app/cli.py`
- 新建：`vision_annotation_workbench/tests/test_run.py`
- 修改：`vision_annotation_workbench/README.md`

- [ ] **步骤 1：编写端到端失败测试**

以临时图片文件夹和固定候选适配器夹具运行一次，断言生成不可变 `run_manifest.json`、CVAT XML、复核清单；再次执行同一输入和种子时结果字节一致；单图失败不阻断其他图片。

- [ ] **步骤 2：运行测试并确认失败**

运行：`pytest tests/test_run.py -v`

预期：失败，原因是运行编排器不存在。

- [ ] **步骤 3：实现编排器和 CLI `run` 命令**

串联导入、固定候选适配器、融合、导出；将输入、配置、标签、随机种子和工件哈希写入清单。恢复时只复用哈希和配置均匹配的已完成步骤。

- [ ] **步骤 4：运行端到端与完整测试**

运行：`pytest -v`

预期：全部通过。

- [ ] **步骤 5：静态检查和提交**

运行：`python -m compileall vision_annotation_workbench`

预期：退出码为 0。

```bash
git add vision_annotation_workbench
git commit -m "feat: 完成标注工作台最小闭环"
```

## 后续阶段门槛

只有任务 1 至任务 6 全部通过，且 CVAT 导出夹具完成导入验证后，才开始接入真实模型。模型接入顺序固定为 Mask2Former、Grounding DINO + SAM、选择性外部 API。每个适配器必须先有离线夹具契约测试，再允许访问 GPU 或外部网络。
