# dataCloud 2.0

dataCloud是一个数智引擎，通过智能构建企业级知识网络，面向大模型、智能应用、业务人员的输出业务化组件能力，提升企业数据获取效率及应用推理的准确性。

## 核心服务

dataCloud 2.0 包含4个核心服务模块：

1. **datacloud-agent** - 超级分析智能体
   - 基于LangGraph框架的极简主义Agent设计
   - 5个原子工具：know/query/compute/render/store
   - 支持会话树、分支探索、自举能力

2. **datacloud-knowledge-service** - 知识服务
   - 根据问题检索知识（业务知识、本体知识）
   - 生成并返回数据查询计划
   - 术语自动发现与沉淀

3. **datacloud-data-service** - 数据服务
   - NL2Data数据查询执行
   - 行列权限控制
   - 异构数据库适配

4. **datacloud-memory** - 记忆服务
   - 短期记忆（会话级）
   - 长期记忆（跨会话）
   - 记忆检索与压缩

## 仓库命名规范

所有仓库遵循GitHub命名最佳实践：
- 使用小写字母
- 使用连字符（`-`）分隔单词
- 命名清晰、描述性
- 保持一致性

详细命名规范请参考：[REPOSITORY_NAMING.md](./REPOSITORY_NAMING.md)