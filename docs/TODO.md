# KaiBrain 待办任务

## 立即处理 (本周)

### 开发任务

- [ ] **D-001** Agent运行时主循环完善
  - 文件: `kaibrain/agent/runtime/agent_loop.py`
  - 任务: 补全`pass`占位的方法实现
  - 优先级: P0

- [ ] **D-002** 工具执行器完善
  - 文件: `kaibrain/agent/runtime/tool_executor.py`
  - 任务: 实现工具调用、结果处理
  - 优先级: P0

- [ ] **D-003** Shell工具安全实现
  - 文件: `kaibrain/system/tools/builtin/shell.py`
  - 任务: 实现命令白名单、超时控制
  - 优先级: P0

### 测试任务

- [ ] **T-001** 创建测试目录结构
  - 任务: `tests/unit/`, `tests/integration/`
  - 优先级: P0

- [ ] **T-002** LLM Provider测试
  - 任务: 测试OpenAI/Ollama调用
  - 优先级: P1

### 文档任务

- [ ] **DOC-001** 补全模块文档字符串
  - 范围: 所有`pass`方法
  - 优先级: P1

---

## 短期 (2周内)

### 开发任务

- [ ] **D-004** SQLite存储适配器
  - 文件: `kaibrain/data/storage/relational.py`
  - 任务: 实现基础CRUD、连接池
  - 依赖: 无

- [ ] **D-005** 工作流记忆持久化
  - 文件: `kaibrain/data/explicit/workflow_memory.py`
  - 任务: 集成SQLite存储
  - 依赖: D-004

- [ ] **D-006** HTTP工具完善
  - 文件: `kaibrain/system/tools/builtin/http.py`
  - 任务: 实现请求、响应解析

- [ ] **D-007** 子Agent生成器
  - 文件: `kaibrain/agent/subagent/spawn.py`
  - 任务: 实现动态Agent创建

- [ ] **D-008** 任务拆解器LLM集成
  - 文件: `kaibrain/agent/orchestrator/task_decomposer.py`
  - 任务: 使用LLM自动拆解复杂任务

### 测试任务

- [ ] **T-003** Agent基础流程测试
  - 范围: 消息发送→处理→响应
  - 覆盖: `agent/base.py`, `brain_pipeline/`

- [ ] **T-004** 工具系统测试
  - 范围: 文件工具、Shell工具
  - 覆盖: `tools/builtin/`

---

## 中期 (1月内)

### 开发任务

- [ ] **D-009** 技能基类完善
  - 文件: `kaibrain/skills/base.py`
  - 任务: 实现技能生命周期回调

- [ ] **D-010** 文件管理技能
  - 目录: `kaibrain/skills/file_management/`
  - 任务: 文件搜索、整理、备份

- [ ] **D-011** 代码分析技能
  - 目录: `kaibrain/skills/code_analysis/`
  - 任务: 代码阅读、分析、生成

- [ ] **D-012** ChromaDB向量存储
  - 文件: `kaibrain/data/storage/vector.py`
  - 任务: 向量存储、相似度搜索

- [ ] **D-013** 实体记忆向量化
  - 文件: `kaibrain/data/explicit/entity_memory.py`
  - 任务: 集成向量存储

- [ ] **D-014** 工具权限系统
  - 文件: `kaibrain/agent/security/tool_policy.py`
  - 任务: 实现权限检查逻辑

### 产品任务

- [ ] **P-001** CLI交互界面
  - 任务: 实现命令行对话界面
  - 用于: 开发测试、演示

- [ ] **P-002** 配置校验
  - 任务: 启动时校验配置完整性
  - 用于: 减少运行时错误

---

## 长期 (需评估)

### ROS2集成
- [ ] **D-020** ROS2节点实现
- [ ] **D-021** 话题发布订阅
- [ ] **D-022** 大脑-小脑桥接

### 硬件集成
- [ ] **D-030** 传感器驱动框架
- [ ] **D-031** 执行器控制框架
- [ ] **D-032** URDF解析器

### 知识图谱
- [ ] **D-040** Neo4j集成
- [ ] **D-041** 图查询接口
- [ ] **D-042** 关系推理

---

## 已完成

- [x] 六层架构设计
- [x] Agent基类实现
- [x] LLM Provider实现 (OpenAI/Anthropic/Ollama)
- [x] 消息总线实现
- [x] 配置中心实现
- [x] 文件工具实现

---

## 阻塞问题

| ID | 问题 | 影响 | 状态 |
|----|------|------|------|
| B-001 | 无测试环境 | 无法验证功能 | 待解决 |
| B-002 | ROS2环境缺失 | 硬件集成无法进行 | 待评估 |
| B-003 | 无真实硬件 | 只能模拟测试 | 待评估 |

---

## 备注

- 任务ID格式: `{类型}-{序号}`
  - D: 开发 Development
  - T: 测试 Test
  - P: 产品 Product
  - DOC: 文档 Documentation
  - B: 阻塞 Blocker

- 优先级:
  - P0: 阻塞性，本周必须完成
  - P1: 重要，下周完成
  - P2: 一般，月内完成
  - P3: 低优先级
