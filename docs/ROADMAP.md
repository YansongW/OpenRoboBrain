# OpenRoboBrain 开发路线图

## 架构基础

OpenRoboBrain 采用**七层大脑-小脑解耦架构**，所有演进在此框架内进行：

```
行为层 → 能力层 → Agent层 → 系统层 → 桥接层 → 中间件层 → 硬件层
                                       ↕
                                    数据层（纵向贯穿）
```

---

## 里程碑总览

| 里程碑 | 阶段 | 状态 | 核心交付 |
|--------|------|------|----------|
| M1 | 核心框架 | ✅ 完成 | 七层架构、Agent系统、消息总线、LLM Provider |
| M2 | 智能管线 | ✅ 完成 | AgentLoop、MemoryRanker、SessionCompactor、双模式管线 |
| M3 | MuJoCo G1 仿真 | ✅ 完成 | Ollama LLM、WebSocket广播、仿真联动、命令队列、ASR/TTS |
| M4 | 能力层深化 | 📋 计划中 | 认知循环、世界模型、自然对话、多模态感知 |
| M5 | 硬件集成 | 📋 计划中 | ROS2真实通信、Sim2Real、传感器/执行器 |
| M6 | 生产就绪 | 📋 计划中 | 监控、部署、文档 |

---

## M1: 核心框架 ✅

- 七层架构设计（含行为层）
- Agent 系统 (Super/Orchestrator/Atomic)
- 消息总线、LLM Provider (8 provider)、工具系统
- Shell/File/HTTP 内置工具
- SQLite 持久化

## M2: 智能管线 ✅

- AgentLoop + LLMInferenceAdapter (ReAct 循环)
- MemoryRanker (5信号类人记忆排序)
- SessionCompactor (自动会话压缩)
- 核心管线贯通 (LLM/规则双模式)
- ToolPolicy 权限系统
- TaskDecomposer 任务拆解

## M3: MuJoCo G1 仿真 ✅ (feature/mujoco-g1-sim)

- Ollama 本地 LLM 集成 (qwen2.5:3b)
- WebSocket 命令广播 + 三终端联动
- unitree_rl_gym 预训练行走策略
- 命令队列系统 (EXEC → QUEUE → NEXT → DONE)
- 参数驱动速度映射 + 组合运动 (circle/spin)
- 结构化 LLM 提示词 (原子动作表)
- ASR (faster-whisper) + TTS (edge-tts) 语音对话

### M3 分支合入分析

| 工作内容 | 应合入 main |
|---------|------------|
| memory.py register 修复 | ✅ Bug fix |
| bridge to_dict() 修复 | ✅ Bug fix |
| stream_handler 队列溢出修复 | ✅ Bug fix |
| broadcaster 重试机制 | ✅ 通用改进 |
| requirements.txt ollama 依赖 | ✅ 依赖 |
| core.py JSON 解析增强 | ✅ 通用改进 |
| ASR/TTS 模块 (audio/) | ✅ 主架构模块 |
| CLI --voice 语音模式 | ✅ 功能增强 |
| core.py 仿真动作提示词 | ⚠️ 仅框架部分 |
| mujoco_g1.py 仿真代码 | ❌ 仿真专用 |
| ros2_monitor.py | ❌ 仿真专用 |
| start_sim.py | ❌ 仿真专用 |

---

## M4: 自然对话 (进行中, feature/m4-natural-dialogue)

**核心思路**: 在现有架构的**能力层**实现自由推理式对话理解，**Agent 层**用 OA 编排执行。

### Phase 4.1: 认知能力 (能力层 → cognition/)

目标：机器人从"被动执行指令"演进为"主动感知-推理-行动"。

**在现有架构内的位置**：

```
能力层 (Capability Layer)
├── perception/    感知理解 (已有框架)
├── cognition/     认知推理 (已有框架，待深化)
│   ├── reasoning.py      已有: LLM推理
│   ├── world_model.py    新增: 环境状态模型
│   ├── goal_manager.py   新增: 目标管理
│   └── reflection.py     新增: 自我反思
├── interaction/   语言交互 (已有框架)
│   └── dialogue.py       新增: 对话状态管理
└── motion/        运动控制 (已有框架)
```

- [ ] **世界模型** — 结构化环境状态（物体/人/空间关系），不同于 MemoryStream 的事件流
- [ ] **目标系统** — 分层目标管理（长期目标 → 当前目标 → 即时子目标）
- [ ] **认知循环** — 从 `process()` 单次调用演进为持续的感知-推理-行动循环
- [ ] **自我反思** — 回顾近期执行，从错误中学习

### Phase 4.2: 自然对话 (能力层 → interaction/) ✅ 基础完成

目标：像人一样对话，不只是"解析命令生成JSON"。

- [x] **LanguageUnderstanding** — 自由推理式理解（认知能力，无枚举分类），LLM 思维链推理
- [x] **Understanding 数据结构** — 完整推理链记录（reasoning, summary, requires_action）
- [x] **意图-行动分离** — LanguageUnderstanding(cognition/) 理解 → OA(Agent层) 编排
- [x] **OA.execute_understanding()** — OrchestratorAgent 接收推理结果，smart_decompose 分解
- [x] **core.py 两步架构** — process() 重构为 LU 推理 → OA 编排
- [x] **隐含意图推理** — LLM 自由推理涌现（"这里好暗" → 开灯）
- [x] **完整推理链日志** — trace_id 串联，reasoning 存入记忆
- [ ] **多轮澄清** — 待进一步完善
- [ ] **对话记忆持久化** — DialogueContext 跨会话保持

### Phase 4.3: 多模态感知 (能力层 → perception/ + Agent层 → atomic/)

目标：机器人通过视觉和听觉理解世界。

- [ ] **视觉理解** — 物体检测、场景理解、人体姿态
- [ ] **ASR/TTS 增强** — CosyVoice 高质量中文语音、打断支持、实时流式
- [ ] **空间感知** — 语义地图构建

### Phase 4.4: 经验学习 (数据层 → memory/)

目标：从经验中学习，越用越聪明。

- [ ] **情景记忆** — 从"事件列表"升级为"因果链"
- [ ] **技能习得** — 从重复成功中提取可复用技能模式
- [ ] **向量检索** — 语义搜索支持

---

## M5: 硬件集成 (计划中)

**在现有架构内的位置**: 桥接层 + 中间件层 + 硬件层

### Phase 5.1: ROS2 真实通信

- [ ] `middleware/cerebellum_pipeline/ros2_node.py` — 真实 ROS2 节点
- [ ] 话题发布/订阅、服务调用、Action 长时间任务
- [ ] 大脑-小脑消息转换 (替代当前 mock 模式)

### Phase 5.2: 硬件抽象

- [ ] 传感器驱动 (Camera/IMU/LiDAR/力传感器)
- [ ] 执行器控制 (电机/夹爪)
- [ ] URDF 解析、关节限位保护

### Phase 5.3: Sim2Real

- [ ] 仿真策略迁移到真实硬件
- [ ] Domain Randomization
- [ ] 安全系统 (碰撞检测、紧急停止)

---

## M6: 生产就绪 (计划中)

- [ ] Prometheus 指标 + 结构化日志 + 分布式追踪
- [ ] Docker 镜像 + Kubernetes 部署
- [ ] REST API + WebSocket 实时通信接口
- [ ] 完整文档 (API/部署/开发者指南)

---

## 技术债务

| 位置 | 问题 | 影响 | 优先级 |
|------|------|------|--------|
| `core.py` 系统提示词 | 硬编码在代码中，应外置为配置 | 不灵活 | P1 |
| `hardware/*.py` | 全部为抽象接口 | 无法控制硬件 | P2 |
| `middleware/ros2_node.py` | ROS2 调用为模拟 | 无实际通信 | P2 |
| 全局 | 测试覆盖率需提升 | 质量风险 | P1 |
