# 视觉自动标注工作台实施计划

> **面向执行智能体：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐项执行。步骤采用复选框追踪。

**目标：** 创建独立的 `vision_annotation_workbench`，实现图片文件夹导入、多模型候选、边界精修、选择性外部复核、CVAT 导出、评测与训练清单的可测试自动标注闭环。

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
  pipelines/evaluate.py
  pipelines/corrections.py
  pipelines/train_manifest.py
  adapters/base.py
  adapters/mask2former.py
  adapters/grounding_dino.py
  adapters/sam.py
  adapters/external_review.py
  artifacts/store.py
  exporters/cvat_xml.py
  exporters/review_manifest.py
  schemas/candidate.schema.json
  tests/conftest.py
  tests/test_ingest.py
  tests/test_domain_models.py
  tests/test_taxonomy.py
  tests/test_cvat_xml.py
  tests/test_run.py
  tests/test_artifact_store.py
  tests/test_mask2former.py
  tests/test_grounding_sam.py
  tests/test_external_review.py
  tests/test_evaluate.py
  tests/test_corrections.py
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

测试 `Proposal` 的图片 ID/哈希/尺寸、提议 ID、归一化框范围、裁剪变换、正负点、来源版本和配置哈希；测试 `CandidateAnnotation` 的实例 ID、双置信度、RLE 工件哈希、完整 provenance、状态枚举、失败错误码，以及未知标签的拒绝行为。

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

验证 CVAT for images 1.1 XML 的 `<image>` 文件名/宽高、稳定排序、多边形闭合、标签映射、`source/confidence/review_state/instance_id` 属性；验证含孔、失败和未解决人工复核候选不进入 XML，而进入复核清单；验证每个候选关联导出 task/job 占位信息。

- [ ] **步骤 2：运行测试并确认失败**

运行：`pytest tests/test_cvat_xml.py tests/test_review_manifest.py -v`

预期：失败，原因是导出器尚未定义。

- [ ] **步骤 3：实现 XML 和 JSON 导出器**

只导出无孔 `accepted` 候选，保留所有非发布候选的工件路径、原因、来源和 task/job 关联信息到 JSON 复核清单。XML 内不写入不受 CVAT 1.1 支持的自定义几何格式。

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

以临时图片文件夹和固定候选适配器夹具运行一次，断言生成不可变 `run_manifest.json`、CVAT XML、复核清单；再次执行同一输入和种子时结果字节一致；单图失败不阻断其他图片；全部图片失败时不可发布；取消和恢复只能复用哈希与配置一致的步骤。

- [ ] **步骤 2：运行测试并确认失败**

运行：`pytest tests/test_run.py -v`

预期：失败，原因是运行编排器不存在。

- [ ] **步骤 3：实现编排器和 CLI `run` 命令**

串联导入、固定候选适配器、融合、导出；将输入、配置、标签、随机种子和工件哈希写入清单。实现取消、恢复、GPU 批处理上限、磁盘配额和工件保留期配置。恢复时只复用哈希和配置均匹配的已完成步骤。

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

### 任务 7：实现内容寻址工件库与质量报告

**文件：**

- 新建：`vision_annotation_workbench/artifacts/store.py`
- 新建：`vision_annotation_workbench/pipelines/report.py`
- 新建：`vision_annotation_workbench/tests/test_artifact_store.py`
- 新建：`vision_annotation_workbench/tests/test_report.py`

- [ ] **步骤 1：编写工件库失败测试**

覆盖 COCO RLE 掩码写入、SHA-256 内容寻址、重复写入去重、叠加图生成、质量报告引用完整性，以及含孔候选保留 RLE 后转人工复核。

- [ ] **步骤 2：运行测试并确认失败**

运行：`pytest tests/test_artifact_store.py tests/test_report.py -v`

预期：失败，原因是工件库尚未实现。

- [ ] **步骤 3：实现工件库和报告器**

掩码、叠加图和报告按内容哈希落盘；报告列出每个候选的模型来源、置信度、状态、规则命中和工件引用。写入后重新读取并校验哈希。

- [ ] **步骤 4：运行测试并确认通过**

运行：`pytest tests/test_artifact_store.py tests/test_report.py -v`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add vision_annotation_workbench/artifacts vision_annotation_workbench/pipelines/report.py vision_annotation_workbench/tests
git commit -m "feat: 添加标注工件库与质量报告"
```

### 任务 8：接入 Mask2Former、校准与评测

**文件：**

- 新建：`vision_annotation_workbench/adapters/base.py`
- 新建：`vision_annotation_workbench/adapters/mask2former.py`
- 新建：`vision_annotation_workbench/pipelines/evaluate.py`
- 新建：`vision_annotation_workbench/tests/test_mask2former.py`
- 新建：`vision_annotation_workbench/tests/test_evaluate.py`

- [ ] **步骤 1：编写适配器和评测失败测试**

使用伪推理后端测试全景 `thing/stuff` 映射、GPU 不可用中文降级、检查点/模型版本 provenance、类别置信度校准、逐像素 mIoU、实例 IoU 0.50 匹配、2 像素容差边界 F-score、高风险召回率与 MP-Former 基线比较。

- [ ] **步骤 2：运行测试并确认失败**

运行：`pytest tests/test_mask2former.py tests/test_evaluate.py -v`

预期：失败，原因是适配器与评测器尚未实现。

- [ ] **步骤 3：实现模型适配器和评测器**

适配器必须隔离推理框架，支持伪后端和真实 PyTorch 后端；评测集清单按内容哈希、场景分层和来源序列切分。真实 GPU 缺失时不能生成伪标注。

- [ ] **步骤 4：运行测试并确认通过**

运行：`pytest tests/test_mask2former.py tests/test_evaluate.py -v`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add vision_annotation_workbench/adapters vision_annotation_workbench/pipelines/evaluate.py vision_annotation_workbench/tests
git commit -m "feat: 接入主分割模型与评测框架"
```

### 任务 9：接入 Grounding DINO 提议和 SAM 边界精修

**文件：**

- 新建：`vision_annotation_workbench/adapters/grounding_dino.py`
- 新建：`vision_annotation_workbench/adapters/sam.py`
- 新建：`vision_annotation_workbench/tests/test_grounding_sam.py`
- 修改：`vision_annotation_workbench/pipelines/fuse.py`

- [ ] **步骤 1：编写提议和精修失败测试**

测试 DINO 只产生 `Proposal`；框加点如何生成 SAM 提示；仅框路径的 `predicted_iou >= 0.75` 接受规则；已有掩码路径的 `IoU >= 0.50`、面积比和轮廓校验；拒绝结果进入人工复核。

- [ ] **步骤 2：运行测试并确认失败**

运行：`pytest tests/test_grounding_sam.py -v`

预期：失败，原因是两个适配器尚未实现。

- [ ] **步骤 3：实现两个可替换适配器**

使用配置中的标签别名构造 DINO 提示；将 DINO 提议转换为 SAM 输入；真实模型后端与伪后端共用数据契约；更新融合器以接收提议和候选两种输入。

- [ ] **步骤 4：运行测试并确认通过**

运行：`pytest tests/test_grounding_sam.py tests/test_fuse.py -v`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add vision_annotation_workbench/adapters vision_annotation_workbench/pipelines/fuse.py vision_annotation_workbench/tests
git commit -m "feat: 添加候选发现与边界精修"
```

### 任务 10：接入选择性外部视觉复核

**文件：**

- 新建：`vision_annotation_workbench/adapters/external_review.py`
- 新建：`vision_annotation_workbench/schemas/external_review.schema.json`
- 新建：`vision_annotation_workbench/tests/test_external_review.py`
- 修改：`vision_annotation_workbench/pipelines/run.py`

- [ ] **步骤 1：编写外部复核失败测试**

验证固定种子选择、10% 图片/每图 3 区域/每日预算限制、1536 px 裁剪、中文日志脱敏、幂等键、20 秒超时和两次重试；验证未知标签、越界坐标、无效 JSON 和 API 失败转 `failed` 或人工复核。

- [ ] **步骤 2：运行测试并确认失败**

运行：`pytest tests/test_external_review.py -v`

预期：失败，原因是外部复核适配器尚未定义。

- [ ] **步骤 3：实现供应商无关适配器**

适配器只接受裁剪图、叠加图、封闭标签表和坐标变换；默认禁用外部网络。所有响应先过 JSON Schema，再进入策略层；预算耗尽和服务错误必须以本地结果继续运行。

- [ ] **步骤 4：运行测试并确认通过**

运行：`pytest tests/test_external_review.py tests/test_run.py -v`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add vision_annotation_workbench/adapters/external_review.py vision_annotation_workbench/schemas vision_annotation_workbench/pipelines/run.py vision_annotation_workbench/tests
git commit -m "feat: 添加选择性视觉复核"
```

### 任务 11：实现 CVAT 修订导入与困难样本训练清单

**文件：**

- 新建：`vision_annotation_workbench/pipelines/corrections.py`
- 新建：`vision_annotation_workbench/pipelines/train_manifest.py`
- 新建：`vision_annotation_workbench/tests/test_corrections.py`
- 新建：`vision_annotation_workbench/tests/test_train_manifest.py`

- [ ] **步骤 1：编写修订闭环失败测试**

测试 CVAT task/job 和标注哈希版本化、源候选关联、复核后修改率、冻结评测集泄漏拒绝、模型分歧/低置信/人工修改样本排序，以及内容哈希可复现的训练清单。

- [ ] **步骤 2：运行测试并确认失败**

运行：`pytest tests/test_corrections.py tests/test_train_manifest.py -v`

预期：失败，原因是修订导入和训练清单尚未实现。

- [ ] **步骤 3：实现修订与挖掘管线**

解析 CVAT XML，保留原始来源与版本；将修订样本按困难评分排序，排除冻结评测集和同一来源序列，输出具有输入哈希、标签版本和划分信息的训练清单。

- [ ] **步骤 4：运行测试并确认通过**

运行：`pytest tests/test_corrections.py tests/test_train_manifest.py -v`

预期：通过。

- [ ] **步骤 5：运行完整验证并提交**

运行：`pytest -v && python -m compileall vision_annotation_workbench`

预期：全部通过，退出码为 0。

```bash
git add vision_annotation_workbench
git commit -m "feat: 完成训练数据闭环"
```
