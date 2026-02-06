# OpenRoboBrain 待办任务

## 里程碑状态

| 里程碑 | 状态 |
|--------|------|
| M1 核心框架 | ✅ 完成 |
| M2 智能管线 | ✅ 完成 |
| M3 MuJoCo G1 仿真 | ✅ 完成 |
| M4 自然对话 | 🔨 进行中 |

---

## 已完成: M3 → main 合入

- [x] Cherry-pick bug fixes + ASR/TTS + 文档到 master (commit d458305)

---

## M4: 自然对话 (进行中, feature/m4-natural-dialogue)

### Phase 4.2: 自然对话 (能力层 interaction/) — 基础完成

- [x] **D-210** DialogueManager 自由推理式理解
  - 文件: `orb/capability/interaction/dialogue.py`
  - 实现: LLM 思维链推理，无枚举分类，Understanding 数据结构
  - 9 个集成测试通过

- [x] **D-211** 意图-行动分离架构
  - core.py 重构: DialogueManager(能力层) 推理 → OA(Agent层) 编排
  - OrchestratorAgent.execute_understanding() 接收推理结果
  - 消除了"LLM 必须同时理解+生成JSON"的问题

- [x] **D-212** 完整推理链日志
  - trace_id 串联完整决策链路
  - reasoning 存入记忆系统

- [ ] **D-213** 多轮澄清完善
  - 优先级: P1

- [ ] **D-214** 对话记忆持久化
  - DialogueContext 跨会话保持
  - 优先级: P1

### Phase 4.1: 认知能力 (能力层 cognition/) — 待开发

- [ ] **D-200** 世界模型 (WorldModel)
  - 文件: `orb/capability/cognition/world_model.py`
  - 任务: 结构化场景图 (物体/人/空间关系/状态)
  - 优先级: P0

- [ ] **D-201** 目标管理系统 (GoalManager)
  - 文件: `orb/capability/cognition/goal_manager.py`
  - 任务: 分层目标栈 (长期 → 当前 → 即时)
  - 优先级: P0

- [ ] **D-202** 认知循环 (CognitiveLoop)
  - 文件: `orb/capability/cognition/cognitive_loop.py`
  - 任务: 持续运行的感知-推理-行动循环
  - 优先级: P0

- [ ] **D-203** 自我反思 (Reflection)
  - 文件: `orb/capability/cognition/reflection.py`
  - 优先级: P1
  - 优先级: P1

- [ ] **D-212** 隐含意图推理
  - 任务: "这里好暗" → 推理出开灯, "好渴" → 推理出倒水
  - 基于世界模型 + 常识推理
  - 优先级: P2

### Phase 4.3: 多模态感知 (能力层 perception/ + Agent层 atomic/)

- [ ] **D-220** 视觉理解模块
  - 文件: `orb/agent/atomic/vision/image_understand.py` (已有框架)
  - 任务: 集成视觉模型 (YOLO/CLIP/LLaVA)
  - 优先级: P1

- [ ] **D-221** ASR 增强
  - 任务: 打断支持、实时流式识别、多语言
  - 可选: CosyVoice 高质量中文 TTS 替代 edge-tts
  - 优先级: P2

- [ ] **D-222** 空间感知
  - 任务: 语义地图 (不只障碍物，而是"厨房的桌子")
  - 优先级: P2

### Phase 4.4: 经验学习 (数据层 memory/)

- [ ] **D-230** 情景记忆 (EpisodicMemory)
  - 文件: `orb/data/memory/episodic_memory.py`
  - 任务: 从事件列表升级为因果链叙事
  - 优先级: P1

- [ ] **D-231** 技能习得
  - 任务: 从重复成功执行中提取技能模式
  - 可复用、组合、迁移
  - 优先级: P2

- [ ] **D-232** 向量检索
  - 文件: `orb/data/storage/vector.py`
  - 任务: 语义搜索 (ChromaDB 或 SQLite+Embeddings)
  - 优先级: P1

---

## M5: 硬件集成

- [ ] **D-300** ROS2 真实节点
- [ ] **D-301** 话题发布/订阅
- [ ] **D-302** 传感器驱动框架
- [ ] **D-303** 执行器控制框架
- [ ] **D-304** Sim2Real 策略迁移
- [ ] **D-305** 安全系统 (碰撞/急停)

---

## 已完成

### M1 核心框架
- [x] 七层架构设计（含行为层）
- [x] Agent 系统 (Super/Orchestrator/Atomic)
- [x] 消息总线 + 配置中心
- [x] LLM Provider (OpenAI/Anthropic/Ollama/Kimi/GLM/Qwen/DeepSeek/Doubao)
- [x] 工具系统 (File/Shell/HTTP/Memory)
- [x] SQLite 存储适配器

### M2 智能管线
- [x] AgentLoop ReAct 循环
- [x] LLMInferenceAdapter (流式/非流式)
- [x] MemoryRanker (5信号类人排序)
- [x] SessionCompactor (自动压缩)
- [x] ToolPolicy 权限系统
- [x] TaskDecomposer 任务拆解
- [x] CLI 交互界面

### M3 MuJoCo G1 仿真
- [x] Ollama 自动检测 + 本地 LLM
- [x] WebSocket 命令广播器 (含重试/端口回退)
- [x] ROS2 报文监控终端
- [x] MuJoCo G1 仿真终端 (unitree_rl_gym 策略)
- [x] 三终端启动脚本
- [x] 命令队列系统 (EXEC→QUEUE→NEXT→DONE)
- [x] 参数驱动速度 + 组合运动 (circle/spin)
- [x] 结构化 LLM 提示词 (原子动作表)
- [x] 健壮 JSON 解析 (混合格式支持)
- [x] ASR (faster-whisper) 语音识别
- [x] TTS (edge-tts) 语音合成
- [x] CLI --voice 语音对话模式

### Bug Fixes (M3 期间)
- [x] memory.py register → registry.register
- [x] bridge to_dict() snake_case/camelCase 双格式
- [x] stream_handler 队列溢出处理
- [x] broadcaster 端口重试/reuse_address
- [x] requirements.txt ollama 依赖

### 测试
- [x] 219+ 单元/集成测试通过
- [x] 端到端测试 (LLM + 仿真 + WebSocket)

---

## 备注

- 任务ID: D-开发, T-测试, MERGE-合入, DOC-文档
- 优先级: P0 阻塞性 / P1 重要 / P2 一般
- 所有新能力在现有七层架构的**能力层**中实现，不替换架构
