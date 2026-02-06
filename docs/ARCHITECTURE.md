# OpenRoboBrain 系统架构

## 核心设计原则：大脑-小脑解耦

OpenRoboBrain 采用**大脑-小脑双管道架构**，两者完全解耦但通过桥接器保持状态同步。

```
┌─────────────────────────────────────────────────────────────────┐
│                        OpenRoboBrain 系统                             │
├────────────────────────────┬────────────────────────────────────┤
│       大脑 (Brain)          │        小脑 (Cerebellum)            │
│    高层次智能决策            │        低层次运动控制               │
├────────────────────────────┼────────────────────────────────────┤
│ 通信协议: WebSocket JSON   │ 通信协议: ROS2 DDS                  │
│ 时间尺度: 秒级              │ 时间尺度: 毫秒级                    │
│ 目标: 多Agent协作、LLM推理  │ 目标: 运动控制、传感器融合          │
├────────────────────────────┼────────────────────────────────────┤
│ 工具: 认知工具              │ 工具: 硬件驱动                      │
│ - 搜索、文件、HTTP          │ - 传感器、执行器                    │
│ - LLM 调用                  │ - 电机控制、夹爪控制                │
├────────────────────────────┼────────────────────────────────────┤
│ 记忆: 显性数据              │ 记忆: 隐性数据                      │
│ - 知识图谱                  │ - Policy (RL训练结果)              │
│ - 工作流记忆                │ - 机械结构配置                      │
│ - 实体记忆                  │ - 运动学参数                        │
├────────────────────────────┼────────────────────────────────────┤
│ 沙箱: 权限控制/Docker       │ 沙箱: 硬件安全策略                  │
│ - 工具白名单/黑名单         │ - 关节限位保护                      │
│ - 命令审批                  │ - 碰撞检测                          │
└────────────────────────────┴────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │  Bridge (桥接器)   │
                    │  状态同步机制      │
                    └───────────────────┘
```

## 1. 大脑管道 (Brain Pipeline)

### 1.1 通信协议: WebSocket JSON

大脑管道使用 WebSocket JSON 作为多智能体协作的通信机制：

```python
# 消息格式
{
    "id": "msg-uuid",
    "type": "agent.message",  # 消息类型
    "source": "agent-a",      # 发送者
    "target": "agent-b",      # 接收者 (可选)
    "payload": {...},         # 消息内容
    "timestamp": "...",
    "correlationId": "..."    # 请求-响应关联
}
```

### 1.2 消息类型

- `agent.message` - Agent 间消息
- `agent.request` / `agent.response` - 请求-响应
- `agent.broadcast` - 广播
- `event.*` - 事件 (lifecycle, tool, stream)
- `sync.*` - 同步消息 (与小脑通信)

### 1.3 记忆系统 (显性数据)

| 类型 | 说明 | 存储方式 | 可修改 |
|-----|------|---------|--------|
| 工作流记忆 | Agent 执行历史 | SQLite/JSONL | ✓ Agent |
| 实体记忆 | 人物、物体、场景 | 向量数据库 | ✓ Agent |
| 知识图谱 | 关系网络 | 图数据库 | ✓ Agent |

### 1.4 工具系统

大脑工具分组：
- `group:fs` - 文件操作
- `group:runtime` - Shell/进程
- `group:web` - 网络请求
- `group:memory` - 记忆操作
- `group:sessions` - 会话管理

## 2. 小脑管道 (Cerebellum Pipeline)

### 2.1 通信协议: ROS2 DDS

小脑管道使用 ROS2 DDS 实现实时运动控制：

- **Topics**: 传感器数据流 (Camera, IMU, LiDAR)
- **Services**: 同步调用 (规划请求)
- **Actions**: 长时间任务 (导航、抓取)

### 2.2 记忆系统 (隐性数据)

| 类型 | 说明 | 来源 | 可修改 |
|-----|------|-----|--------|
| Policy | RL 训练结果 | 训练管线 | ✗ 仅人工 |
| 机械配置 | 关节限位、DH参数 | URDF/SRDF | ✗ 仅人工 |
| 运动学参数 | 标定结果 | 标定程序 | ✗ 仅人工 |

**重要**: 隐性数据不能被 Agent 修改，只能由人工介入更新。

### 2.3 工具系统

小脑工具分组：
- `group:robot` - 运动控制 (move, rotate, navigate)
- `group:sensors` - 传感器读取
- `group:actuators` - 执行器控制

## 3. 桥接器 (Brain-Cerebellum Bridge)

### 3.1 核心职责

1. **命令下发**: Brain → Cerebellum
   - 语义化命令转换为运动控制指令
   - "移动到位置A" → Nav2 导航请求

2. **状态反馈**: Cerebellum → Brain
   - 传感器数据摘要
   - 执行状态更新

3. **异常处理**: 双向
   - 紧急停止
   - 错误恢复

### 3.2 命令转换示例

```
大脑命令 (语义化):
{
    "commandType": "grasp",
    "parameters": {
        "object": "红色杯子",
        "approach_direction": "top"
    }
}

        ↓ CommandTranslator

小脑动作序列 (运动控制):
1. MoveIt 规划到预抓取位置
2. 打开夹爪
3. 直线运动到抓取位置
4. 关闭夹爪
```

### 3.3 状态同步

```python
# 同步状态结构
{
    "brain_state": {
        "current_task": "pickup_object",
        "agents_online": ["planner", "vision", "nlp"],
    },
    "cerebellum_state": {
        "robot_pose": {...},
        "joint_states": [...],
        "battery_level": 85,
    },
    "sync_timestamp": "..."
}
```

## 4. 分层架构

```mermaid
flowchart TB
    subgraph BrainDomain [大脑域 Brain Domain]
        direction TB
        subgraph BehaviorLayer [行为层 Behavior Layer]
            direction LR
            BH1[烹饪]
            BH2[驾驶]
            BH3[清洁]
            BH4[搬运]
        end
        
        subgraph CapabilityLayer [能力层 Capability Layer]
            direction LR
            CAP1[感知理解]
            CAP2[认知推理]
            CAP3[语言交互]
            CAP4[知识管理]
            CAP5[任务编排]
        end
        
        subgraph AgentLayer [Agent层]
            direction LR
            SA[Super Agent] --> OA[编排Agent]
            OA --> AA1[原子Agent]
            OA --> AA2[原子Agent]
            OA --> AAN[...]
        end
        
        subgraph SystemLayer [系统层 - Brain Pipeline]
            direction LR
            WS[WebSocket Server<br/>JSON Protocol]
            MB[MessageBus]
            LLM[LLM System]
            TOOL[Tool System]
        end
    end
    
    subgraph BridgeLayer [桥接层]
        BRIDGE[Brain-Cerebellum Bridge<br/>唯一交互点<br/>命令翻译 | 状态同步]
    end
    
    subgraph CerebellumDomain [小脑域 Cerebellum Domain]
        direction TB
        subgraph MiddlewareLayer [中间件层 - Cerebellum Pipeline]
            direction LR
            ROS2[ROS2 DDS]
            TOPIC[Topics]
            SVC[Services]
            ACT[Actions]
        end
        
        subgraph HardwareLayer [硬件层]
            direction TB
            CTRL[控制系统软件]
            DRV[硬件驱动]
            PHY[物理硬件]
            CTRL --> DRV --> PHY
        end
    end
    
    subgraph DataLayer [数据层 - 纵向贯穿全系统]
        direction LR
        subgraph Explicit [显性数据 - Agent可修改]
            WF[工作流记忆]
            ENT[实体数据]
            KG[知识图谱]
        end
        subgraph Implicit [隐性数据 - 仅人工修改]
            POL[Policy]
            MECH[机械配置]
        end
    end
    
    BehaviorLayer --> CapabilityLayer
    CapabilityLayer --> AgentLayer
    AgentLayer --> SystemLayer
    SystemLayer <--> BRIDGE
    BRIDGE <--> MiddlewareLayer
    MiddlewareLayer --> HardwareLayer
    
    DataLayer -.->|读写| BrainDomain
    DataLayer -.->|只读| CerebellumDomain
```

### 层级职责说明

| 层级 | 域 | 职责 |
|------|-----|------|
| **行为层** | 大脑 | 复合行为模式，关联工作流记忆实现经验复用 |
| **能力层** | 大脑 | 原子认知能力，不含运动控制 |
| **Agent层** | 大脑 | Super（管理）→ 编排（调度）→ 原子（执行） |
| **系统层** | 大脑 | WebSocket JSON通信，LLM/工具/消息总线 |
| **Bridge** | 边界 | 唯一交互点，语义命令↔控制指令翻译 |
| **中间件层** | 小脑 | ROS2 DDS实时通信 |
| **硬件层** | 小脑 | 控制软件 → 驱动 → 物理设备 |
| **数据层** | 贯穿 | 显性（可学习）+ 隐性（受保护） |

## 5. 使用指南

### 5.1 启动大脑服务器

```python
from orb.system.brain_pipeline import (
    create_brain_server,
    create_bridge,
)

# 创建并启动大脑 WebSocket 服务器
brain_server = create_brain_server(host="0.0.0.0", port=8765)
await brain_server.start()

# 创建桥接器
bridge = create_bridge(brain_server=brain_server)
await bridge.initialize()
```

### 5.2 Agent 连接

```python
from orb.system.brain_pipeline import create_brain_client

# Agent 连接到大脑服务器
client = create_brain_client(
    agent_id="planner-agent",
    server_url="ws://localhost:8765"
)
await client.connect()

# 发送消息
await client.send_to_agent("vision-agent", {"query": "检测红色物体"})

# 请求-响应
response = await client.request("vision-agent", {"query": "..."}, timeout=30.0)
```

### 5.3 发送命令到小脑

```python
from orb.system.brain_pipeline import BrainCommand, CommandPriority

command = BrainCommand(
    command_type="move_to",
    parameters={
        "target_position": {"x": 1.0, "y": 2.0, "z": 0.0},
        "velocity": 0.5,
    },
    priority=CommandPriority.NORMAL,
    source_agent="planner-agent",
)

feedback = await bridge.send_command(command, wait_for_completion=True)
```

## 6. 设计原则总结

1. **解耦优先**: 大脑和小脑使用完全不同的技术栈
2. **职责分离**: 大脑负责"思考"，小脑负责"执行"
3. **数据隔离**: 显性数据可学习，隐性数据受保护
4. **统一桥接**: 通过 Bridge 实现必要的状态同步
5. **安全优先**: 各自独立的安全机制

## 7. 质量保障

### 7.1 风险管理

项目使用多层风险管理机制：

| 机制 | 文件 | 说明 |
|------|------|------|
| 风险文档 | [RISKS.md](./RISKS.md) | 记录已识别风险和缓解措施 |
| BUG跟踪 | [BUGS.md](./BUGS.md) | 跟踪已知问题和修复进度 |
| 运行时监控 | `risk_monitor.py` | 启动检查和运行时监控 |

### 7.2 风险等级

| 等级 | 描述 | 部署要求 |
|------|------|----------|
| 🔴 CRITICAL | 致命风险，可能导致人身伤害 | **必须修复** |
| 🟠 HIGH | 高风险，影响系统安全 | 强烈建议修复 |
| 🟡 MEDIUM | 中风险，影响稳定性 | 计划内修复 |
| 🟢 LOW | 低风险，可接受 | 可选修复 |

### 7.3 启动检查

在部署前运行风险检查：

```python
from orb.system.services import run_risk_check

# 运行启动检查
report = await run_risk_check()

# 检查致命风险
critical_risks = [r for r in report.risks if r.level.value == "critical"]
if critical_risks:
    print("⚠️ 存在致命风险，不建议部署")
    for risk in critical_risks:
        print(f"  - {risk.id}: {risk.title}")
```

### 7.4 相关文档

- [RISKS.md](./RISKS.md) - 完整风险清单
- [BUGS.md](./BUGS.md) - BUG跟踪列表
- [TODO.md](./TODO.md) - 待办任务

---

## 8. MuJoCo G1 仿真架构 (feature/mujoco-g1-sim)

### 8.1 三终端通信架构

```
终端1 (CLI)                终端2 (ROS2 Monitor)      终端3 (MuJoCo G1)
    |                           |                         |
    v                           |                         |
OpenRoboBrain.process()         |                         |
    |                           |                         |
    v                           |                         |
AgentLoop -> Ollama LLM         |                         |
    |                           |                         |
    v                           |                         |
BrainCerebellumBridge           |                         |
    |                           |                         |
    v                           v                         v
CommandBroadcaster -------> WebSocket :8765 ---------> ws client
                          (JSON broadcast)           cmd -> RL Policy
                                                     -> PD Control
                                                     -> MuJoCo Step
```

### 8.2 命令流转

1. 用户自然语言输入 -> AgentLoop -> LLM 推理 (Ollama Qwen2.5)
2. LLM 输出 JSON (chat_response + ros2_commands)
3. BrainCommand 通过 Bridge 执行 + 通过 WebSocket 广播
4. ROS2 Monitor 以 Topic 格式显示
5. MuJoCo 终端将 command_type 映射为速度指令 [vx, vy, wz]
6. unitree_rl_gym 预训练策略推理 -> 关节力矩 -> MuJoCo 步进 -> 渲染

### 8.3 技术栈

- **LLM**: Ollama + Qwen2.5:3b (本地, Tool Calling)
- **策略**: unitree_rl_gym/deploy/pre_train/g1/motion.pt (PPO, 29-DOF)
- **仿真**: MuJoCo (Python) + G1 MJCF 模型
- **通信**: WebSocket (JSON) 松耦合广播
