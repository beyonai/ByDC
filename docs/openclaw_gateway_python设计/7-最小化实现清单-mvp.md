# 7. 最小化实现清单 (MVP)

## 7.1 Phase 1: 核心功能 (必需)
- [ ] **多租户架构** - TenantContext, TenantResolution, 三层根目录
- [ ] **队列系统** - 6种队列模式 (COLLECT/STEER/STEER_BACKLOG/FOLLOWUP/INTERRUPT/QUEUE)
- [ ] **四层文件架构** - SystemPromptBuilder支持身份层/操作层/知识层/协作层
- [ ] SessionManager (租户感知, 内存存储)
- [ ] AgentRegistry (支持 2-3 个预设 Agent)
- [ ] CommandRouter (`/model`, `/reset`, `/help`)
- [ ] GatewayServer (WebSocket 基础)
- [ ] deepagents 集成 (单轮对话)

## 7.2 Phase 2: 增强功能
- [ ] 会话持久化 (JSONL, 租户隔离路径)
- [ ] 流式输出 (WebSocket 事件)
- [ ] 更多命令 (`/think`, `/verbose`, `/context`)
- [ ] HTTP API (OpenAI 兼容端点)
- [ ] STEER模式完整实现 (LangGraph interrupt)

## 7.3 Phase 3: 高级功能
- [ ] 工具执行 (sandbox)
- [ ] 子 Agent 支持
- [ ] 配置热重载
- [ ] 分布式队列后端 (Redis)
- [ ] 高级认证/授权

---
