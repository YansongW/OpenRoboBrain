# KaiBrain BUG 管理

## 概述

本文档记录 KaiBrain 项目的已知BUG、修复进度和历史记录。

---

## 严重程度定义

| 等级 | 标识 | 描述 | 响应时间 |
|------|------|------|----------|
| **P0-阻塞** | 🔴 BLOCKER | 系统无法启动、核心功能完全失效、安全漏洞 | 立即修复 |
| **P1-严重** | 🟠 CRITICAL | 主要功能异常、数据丢失风险、频繁崩溃 | 24小时内 |
| **P2-一般** | 🟡 MAJOR | 功能部分失效、有workaround、性能问题 | 1周内 |
| **P3-轻微** | 🟢 MINOR | UI问题、日志错误、边缘场景 | 下次迭代 |
| **P4-建议** | 🔵 TRIVIAL | 代码优化、文档错误、改进建议 | 可选修复 |

---

## BUG状态

| 状态 | 说明 |
|------|------|
| `NEW` | 新提交，待确认 |
| `CONFIRMED` | 已确认，待分配 |
| `IN_PROGRESS` | 修复中 |
| `IN_REVIEW` | 修复完成，待评审 |
| `RESOLVED` | 已修复，待验证 |
| `VERIFIED` | 已验证，待关闭 |
| `CLOSED` | 已关闭 |
| `WONTFIX` | 不修复 |
| `DUPLICATE` | 重复 |
| `CANNOT_REPRODUCE` | 无法复现 |

---

## BUG分类

| 类别 | 代码前缀 | 说明 |
|------|----------|------|
| 功能 | FUNC | 功能不符合预期 |
| 崩溃 | CRASH | 程序崩溃、异常退出 |
| 性能 | PERF | 性能问题、响应慢 |
| 安全 | SEC | 安全相关问题 |
| 内存 | MEM | 内存泄漏、OOM |
| 并发 | CONC | 竞态条件、死锁 |
| 集成 | INT | 第三方集成问题 |
| 配置 | CONF | 配置相关问题 |
| 文档 | DOC | 文档错误 |

---

## 当前BUG清单

### 🔴 P0-阻塞 (BLOCKER)

> 暂无

---

### 🟠 P1-严重 (CRITICAL)

#### BUG-CONC-001: MessageBus pending_responses 内存泄漏

| 属性 | 值 |
|------|-----|
| **位置** | `kaibrain/system/brain_pipeline/message_bus.py` |
| **版本** | v0.1.0-alpha |
| **描述** | `request()` 方法创建的 Future 在超时后未从 `_pending_responses` 中清理，导致字典持续增长 |
| **复现步骤** | 1. 发送大量请求<br>2. 让部分请求超时<br>3. 检查 `_pending_responses` 大小 |
| **预期结果** | 超时后自动清理 |
| **实际结果** | Future 一直保留在字典中 |
| **状态** | `RESOLVED` ✅ |
| **负责人** | - |
| **创建日期** | 2026-02-02 |
| **解决日期** | 2026-02-02 |
| **解决方案** | 使用 `PendingRequest` 包装器记录创建时间，添加定时清理任务（`_cleanup_pending_loop`）自动清理过期的 pending_responses。使用锁保护并发访问。 |

---

#### BUG-CONC-002: TaskPipeline cleanup_timer 竞态

| 属性 | 值 |
|------|-----|
| **位置** | `kaibrain/system/brain_pipeline/task_pipeline.py` |
| **版本** | v0.1.0-alpha |
| **描述** | 并发调用时可能为同一 task_id 创建多个清理定时器 |
| **复现步骤** | 1. 并发调用 `schedule_cleanup()` 使用相同 task_id<br>2. 观察定时器数量 |
| **状态** | `CONFIRMED` |
| **负责人** | - |
| **创建日期** | 2026-02-02 |

---

### 🟡 P2-一般 (MAJOR)

#### BUG-FUNC-001: Shell工具命令提取不完整

| 属性 | 值 |
|------|-----|
| **位置** | `kaibrain/system/tools/builtin/shell.py:_extract_base_command()` |
| **版本** | v0.1.0-alpha |
| **描述** | 命令提取使用简单字符串分割，无法正确处理引号内的分隔符 |
| **示例** | `echo "hello; world"` 被错误拆分 |
| **状态** | `CONFIRMED` |
| **负责人** | - |
| **创建日期** | 2026-02-02 |

---

#### BUG-FUNC-002: WebSocket心跳时间解析错误

| 属性 | 值 |
|------|-----|
| **位置** | `kaibrain/system/brain_pipeline/websocket_server.py` |
| **版本** | v0.1.0-alpha |
| **描述** | `datetime.fromisoformat()` 解析错误未处理，可能导致假断开 |
| **状态** | `CONFIRMED` |
| **负责人** | - |
| **创建日期** | 2026-02-02 |

---

#### BUG-MEM-001: Agent状态回调异常处理

| 属性 | 值 |
|------|-----|
| **位置** | `kaibrain/system/brain_pipeline/state_sync.py:_notify_state_change()` |
| **版本** | v0.1.0-alpha |
| **描述** | 一个回调异常会阻塞后续回调执行 |
| **状态** | `CONFIRMED` |
| **负责人** | - |
| **创建日期** | 2026-02-02 |

---

#### BUG-FUNC-003: Bridge action状态检查竞态

| 属性 | 值 |
|------|-----|
| **位置** | `kaibrain/system/brain_pipeline/brain_cerebellum_bridge.py` |
| **版本** | v0.1.0-alpha |
| **描述** | `all_completed` 和 `any_failed` 检查之间状态可能变化 |
| **状态** | `CONFIRMED` |
| **负责人** | - |
| **创建日期** | 2026-02-02 |

---

### 🟢 P3-轻微 (MINOR)

#### BUG-FUNC-004: 环境变量注入未验证

| 属性 | 值 |
|------|-----|
| **位置** | `kaibrain/system/tools/builtin/shell.py` |
| **版本** | v0.1.0-alpha |
| **描述** | 用户提供的 `env` 字典直接合并，未验证键值安全性 |
| **状态** | `NEW` |
| **创建日期** | 2026-02-02 |

---

#### BUG-DOC-001: 模块文档字符串缺失

| 属性 | 值 |
|------|-----|
| **位置** | 多个模块 |
| **版本** | v0.1.0-alpha |
| **描述** | 部分 `pass` 方法缺少文档字符串 |
| **状态** | `NEW` |
| **创建日期** | 2026-02-02 |

---

### 🔵 P4-建议 (TRIVIAL)

> 暂无

---

## 已修复BUG历史

| ID | 描述 | 严重程度 | 修复版本 | 修复日期 |
|----|------|----------|----------|----------|
| BUG-CONC-001 | MessageBus pending_responses 内存泄漏 | P1-严重 | v0.1.0-alpha | 2026-02-02 |

---

## BUG统计

### 按严重程度

| 等级 | 数量 | OPEN | IN_PROGRESS | RESOLVED |
|------|------|------|-------------|----------|
| 🔴 P0-阻塞 | 0 | 0 | 0 | 0 |
| 🟠 P1-严重 | 2 | 1 | 0 | 1 |
| 🟡 P2-一般 | 4 | 4 | 0 | 0 |
| 🟢 P3-轻微 | 2 | 2 | 0 | 0 |
| 🔵 P4-建议 | 0 | 0 | 0 | 0 |
| **总计** | **8** | **7** | **0** | **1** |

### 按类别

| 类别 | 数量 | RESOLVED |
|------|------|----------|
| CONC (并发) | 2 | 1 |
| FUNC (功能) | 4 | 0 |
| MEM (内存) | 1 | 0 |
| DOC (文档) | 1 | 0 |

---

## BUG提交流程

### 1. 发现BUG时

1. 检查是否已存在相同BUG
2. 收集复现步骤、环境信息、日志
3. 按模板添加到对应严重程度分类下

### 2. BUG确认后

1. 更新状态为 `CONFIRMED`
2. 评估严重程度
3. 分配负责人（如有）

### 3. 修复完成后

1. 更新状态为 `RESOLVED`
2. 添加修复说明
3. 移至"已修复BUG历史"

---

## 附录：BUG模板

```markdown
#### BUG-{类别}-{序号}: {简短描述}

| 属性 | 值 |
|------|-----|
| **位置** | `文件路径` |
| **版本** | vX.X.X |
| **描述** | 详细描述BUG |
| **复现步骤** | 1. 步骤1<br>2. 步骤2 |
| **预期结果** | 描述预期行为 |
| **实际结果** | 描述实际行为 |
| **环境** | OS, Python版本等 |
| **日志** | 相关错误日志 |
| **状态** | `NEW` |
| **负责人** | - |
| **创建日期** | YYYY-MM-DD |
```

---

## 相关文档

- [RISKS.md](./RISKS.md) - 风险管理
- [TODO.md](./TODO.md) - 待办任务
- [ARCHITECTURE.md](./ARCHITECTURE.md) - 架构文档
