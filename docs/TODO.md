# KaiBrain 待办任务

## 立即处理 (本周)

### 开发任务

- [x] **D-001** Agent运行时主循环完善 ✅
  - 文件: `kaibrain/agent/runtime/agent_loop.py`
  - 状态: 已完成完整实现（事件驱动、生命周期钩子、流式输出）

- [x] **D-002** 工具执行器完善 ✅
  - 文件: `kaibrain/agent/runtime/tool_executor.py`
  - 状态: 已完成（工具注册、执行、超时控制）

- [x] **D-003** Shell工具安全实现 ✅
  - 文件: `kaibrain/system/tools/builtin/shell.py`
  - 状态: 已完成（白/黑名单、超时、后台执行、安全模式）

- [ ] **D-004** SQLite存储适配器
  - 文件: `kaibrain/data/storage/relational.py`
  - 任务: 实现基础CRUD、连接池
  - 优先级: P0 (阻塞持久化)

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

- [ ] **D-005** 工作流记忆持久化
  - 文件: `kaibrain/data/explicit/workflow_memory.py`
  - 任务: 集成SQLite存储
  - 依赖: D-004

- [x] **D-006** HTTP工具完善 ✅
  - 文件: `kaibrain/system/tools/builtin/http.py`
  - 状态: 已完成（GET/POST、httpx/aiohttp双支持、文件下载）

- [ ] **D-007** 子Agent生成器
  - 文件: `kaibrain/agent/subagent/spawn.py`
  - 任务: 实现动态Agent创建

- [ ] **D-008** 任务拆解器LLM集成
  - 文件: `kaibrain/agent/orchestrator/task_decomposer.py`
  - 任务: 使用LLM自动拆解复杂任务

- [x] **D-009** 行为层框架实现 ✅
  - 目录: `kaibrain/behavior/`
  - 状态: 已完成（基类、注册表、执行器、内置行为）

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

- [x] 七层架构设计（含行为层）
- [x] Agent基类实现
- [x] LLM Provider实现 (OpenAI/Anthropic/Ollama)
- [x] 消息总线实现
- [x] 配置中心实现
- [x] 文件工具实现
- [x] Agent Loop完整实现（事件驱动、生命周期钩子）
- [x] 工具执行器实现（注册、执行、超时）
- [x] Shell工具安全实现（白/黑名单、安全模式）
- [x] HTTP工具实现（GET/POST、文件下载）
- [x] 上下文构建器实现（Bootstrap注入、记忆、压缩）
- [x] WebSocket服务器实现（大脑管道通信）
- [x] Brain-Cerebellum Bridge实现（大小脑桥接）
- [x] 会话存储实现（内存版）
- [x] 工作流记忆实现（内存版 + SQLite持久化）
- [x] SQLite存储适配器（连接池、CRUD、迁移）
- [x] 测试框架搭建（pytest配置、fixtures）
- [x] 行为层框架（基类、注册表、执行器）
- [x] 内置行为（烹饪、清洁）

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
  - RISK: 风险修复

- 优先级:
  - P0: 阻塞性，本周必须完成
  - P1: 重要，下周完成
  - P2: 一般，月内完成
  - P3: 低优先级

---

## 相关文档

- [RISKS.md](./RISKS.md) - 风险管理
- [BUGS.md](./BUGS.md) - BUG跟踪
- [ARCHITECTURE.md](./ARCHITECTURE.md) - 架构文档
