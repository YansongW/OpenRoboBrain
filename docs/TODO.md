# KaiBrain 待办任务

## 立即处理 (本周)

### 开发任务

- [x] **D-001** Agent运行时主循环完善 ✅
  - 文件: `kaibrain/agent/runtime/agent_loop.py`
  - 状态: 已完成完整实现（事件驱动、生命周期钩子、流式输出）

- [x] **D-002** 工具执行器完善 ✅
  - 文件: `kaibrain/agent/runtime/tool_executor.py`
  - 状态: 已完成（工具注册、执行、超时控制、ToolPolicy集成）

- [x] **D-003** Shell工具安全实现 ✅
  - 文件: `kaibrain/system/tools/builtin/shell.py`
  - 状态: 已完成（白/黑名单、超时、后台执行、安全模式）

- [x] **D-004** SQLite存储适配器 ✅
  - 文件: `kaibrain/data/storage/relational.py`
  - 状态: 已完成（连接池、CRUD、迁移）

### 测试任务

- [x] **T-001** 创建测试目录结构 ✅
  - 目录: `tests/unit/`, `tests/integration/`
  - 状态: 已完成（pytest配置、fixtures）

- [ ] **T-002** LLM Provider测试
  - 任务: 测试OpenAI/Ollama调用
  - 优先级: P1

- [ ] **T-005** MVP端到端测试
  - 任务: 测试CLI输入→chat响应+ROS2命令
  - 优先级: P0

### 文档任务

- [ ] **DOC-001** 补全模块文档字符串
  - 范围: 所有`pass`方法
  - 优先级: P1

- [ ] **DOC-002** CLI使用文档
  - 任务: 编写CLI使用指南和示例
  - 优先级: P1

---

## 短期 (2周内)

### 开发任务

- [ ] **D-005** 工作流记忆持久化
  - 文件: `kaibrain/data/explicit/workflow_memory.py`
  - 任务: 集成SQLite存储
  - 依赖: D-004 ✅

- [x] **D-006** HTTP工具完善 ✅
  - 文件: `kaibrain/system/tools/builtin/http.py`
  - 状态: 已完成（GET/POST、httpx/aiohttp双支持、文件下载）

- [x] **D-007** 子Agent生成器 ✅
  - 文件: `kaibrain/agent/subagent/spawn.py`
  - 状态: 已完成（动态Agent创建、任务追踪、取消机制）

- [ ] **D-008** 任务拆解器LLM集成
  - 文件: `kaibrain/agent/orchestrator/task_decomposer.py`
  - 任务: 使用LLM自动拆解复杂任务

- [x] **D-009** 行为层框架实现 ✅
  - 目录: `kaibrain/behavior/`
  - 状态: 已完成（基类、注册表、执行器、内置行为、GeneralBehavior）

- [ ] **D-015** LLM配置优化
  - 文件: `kaibrain/system/llm/config.py`
  - 任务: 支持更多Provider配置、流式输出优化
  - 优先级: P1

- [ ] **D-016** 多Agent协作测试场景
  - 任务: 创建多Agent协作的示例场景
  - 优先级: P2

### 测试任务

- [ ] **T-003** Agent基础流程测试
  - 范围: 消息发送→处理→响应
  - 覆盖: `agent/base.py`, `brain_pipeline/`

- [ ] **T-004** 工具系统测试
  - 范围: 文件工具、Shell工具
  - 覆盖: `tools/builtin/`

- [x] **T-006** MessageBus单元测试 ✅
  - 文件: `tests/unit/test_message_bus.py`
  - 状态: 已完成

- [x] **T-007** ToolPolicy单元测试 ✅
  - 文件: `tests/unit/test_tool_policy_enforcement.py`
  - 状态: 已完成

- [x] **T-008** SubAgent终止测试 ✅
  - 文件: `tests/unit/test_subagent_termination.py`
  - 状态: 已完成

---

## 中期 (1月内)

### 开发任务

- [ ] **D-010** 技能基类完善
  - 文件: `kaibrain/skills/base.py`
  - 任务: 实现技能生命周期回调

- [ ] **D-011** 文件管理技能
  - 目录: `kaibrain/skills/file_management/`
  - 任务: 文件搜索、整理、备份

- [ ] **D-012** 代码分析技能
  - 目录: `kaibrain/skills/code_analysis/`
  - 任务: 代码阅读、分析、生成

- [ ] **D-013** ChromaDB向量存储
  - 文件: `kaibrain/data/storage/vector.py`
  - 任务: 向量存储、相似度搜索

- [ ] **D-014** 实体记忆向量化
  - 文件: `kaibrain/data/explicit/entity_memory.py`
  - 任务: 集成向量存储

- [x] **D-017** 工具权限系统 ✅
  - 文件: `kaibrain/agent/security/tool_policy.py`
  - 状态: 已完成（ToolPolicy枚举、ToolExecutor集成）

- [ ] **D-018** API接口层
  - 任务: 实现REST API接口，支持HTTP调用
  - 优先级: P1

- [ ] **D-019** WebSocket实时通信
  - 任务: 实现WebSocket接口，支持流式响应
  - 优先级: P2

### 产品任务

- [x] **P-001** CLI交互界面 ✅
  - 文件: `kaibrain/cli.py`
  - 状态: 已完成（REPL、彩色输出、verbose模式、单命令执行）

- [ ] **P-002** 配置校验
  - 任务: 启动时校验配置完整性
  - 用于: 减少运行时错误

- [ ] **P-003** Web演示界面
  - 任务: 简单的Web界面用于演示
  - 优先级: P2

---

## 长期 (需评估)

### ROS2集成
- [ ] **D-020** ROS2节点实现
- [ ] **D-021** 话题发布订阅
- [x] **D-022** 大脑-小脑桥接 ✅
  - 文件: `kaibrain/system/brain_pipeline/brain_cerebellum_bridge.py`
  - 状态: 已完成（命令转换、mock模式、状态反馈）

### 硬件集成
- [ ] **D-030** 传感器驱动框架
- [ ] **D-031** 执行器控制框架
- [ ] **D-032** URDF解析器

### 知识图谱
- [ ] **D-040** Neo4j集成
- [ ] **D-041** 图查询接口
- [ ] **D-042** 关系推理

### 性能优化
- [ ] **D-050** LLM调用缓存
- [ ] **D-051** 并发处理优化
- [ ] **D-052** 内存管理优化

---

## 已完成

### 核心架构
- [x] 七层架构设计（含行为层）
- [x] Agent基类实现
- [x] 消息总线实现（含超时、请求清理）
- [x] 配置中心实现

### LLM集成
- [x] LLM Provider实现 (OpenAI/Anthropic/Ollama/Kimi/GLM/Qwen/DeepSeek/Doubao)
- [x] LLMFactory工厂模式
- [x] 流式输出支持

### Agent系统
- [x] Agent Loop完整实现（事件驱动、生命周期钩子）
- [x] 工具执行器实现（注册、执行、超时、ToolPolicy）
- [x] 上下文构建器实现（Bootstrap注入、记忆、压缩）
- [x] SubAgent生成器（动态创建、任务追踪、取消）
- [x] ToolPolicy权限系统（ALLOW/DENY/REQUIRE_APPROVAL）
- [x] ReasoningAgent（LLM驱动的认知推理）
- [x] OrchestratorAgent.execute_with_llm()

### 工具系统
- [x] 文件工具实现
- [x] Shell工具安全实现（白/黑名单、安全模式）
- [x] HTTP工具实现（GET/POST、文件下载）

### 通信系统
- [x] WebSocket服务器实现（大脑管道通信）
- [x] Brain-Cerebellum Bridge实现（命令转换、mock模式）

### 数据存储
- [x] 会话存储实现（内存版）
- [x] 工作流记忆实现（内存版 + SQLite持久化）
- [x] SQLite存储适配器（连接池、CRUD、迁移）

### 行为层
- [x] 行为层框架（基类、注册表、执行器）
- [x] 内置行为（烹饪、清洁、GeneralBehavior）
- [x] BehaviorContext（trace_id、ros2_commands、chat_response）

### MVP调用链路
- [x] KaiBrain.process()入口方法
- [x] ProcessResult数据类（chat_response + ros2_commands）
- [x] CLI交互界面（REPL、彩色输出、verbose模式）
- [x] 增强日志系统（trace_id、层级标识、trace_context）

### 测试
- [x] 测试框架搭建（pytest配置、fixtures）
- [x] MessageBus单元测试
- [x] ToolPolicy单元测试
- [x] SubAgent终止测试

### 质量保障
- [x] 风险管理机制（RISKS.md）
- [x] BUG管理机制（BUGS.md）
- [x] RiskMonitor服务

---

## 阻塞问题

| ID | 问题 | 影响 | 状态 |
|----|------|------|------|
| B-001 | ~~无测试环境~~ | ~~无法验证功能~~ | ✅ 已解决 |
| B-002 | ROS2环境缺失 | 硬件集成无法进行 | 使用mock模式 |
| B-003 | 无真实硬件 | 只能模拟测试 | 使用mock模式 |
| B-004 | LLM API配置 | 需要配置API Key | 待用户配置 |

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

## MVP使用指南

### 快速开始

```bash
# 启动CLI（模拟ROS2模式）
python -m kaibrain.cli

# 详细模式（显示trace_id、执行时间）
python -m kaibrain.cli -v

# 执行单条命令
python -m kaibrain.cli -e "帮我倒杯水"

# 连接真实ROS2
python -m kaibrain.cli --real-ros2
```

### CLI命令

| 命令 | 说明 |
|------|------|
| /help | 显示帮助 |
| /verbose | 切换详细模式 |
| /status | 显示系统状态 |
| /quit | 退出程序 |

### 代码调用

```python
from kaibrain import KaiBrain

brain = KaiBrain(mock_ros2=True)
await brain.initialize()
await brain.start()

result = await brain.process("帮我倒杯水")
print(result.chat_response)   # 对话响应
print(result.ros2_commands)   # ROS2控制命令

await brain.stop()
```

---

## 相关文档

- [RISKS.md](./RISKS.md) - 风险管理
- [BUGS.md](./BUGS.md) - BUG跟踪
- [ARCHITECTURE.md](./ARCHITECTURE.md) - 架构文档
- [ROADMAP.md](./ROADMAP.md) - 路线图
