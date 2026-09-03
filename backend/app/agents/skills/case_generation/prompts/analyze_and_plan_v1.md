请根据以下信息拆解测试覆盖计划。

【来源上下文】
{source_context}

【项目上下文】
{project_context}

【已有用例摘要】（用于避免重复覆盖，格式为摘要 JSON）
{existing_cases}

【相关接口文档摘要】
{related_api_documents}

【用户要求】
- 请求覆盖的用例类型：{case_types}
- 最大候选数：{max_cases}
- 补充目标：{user_goal}

【任务】
1. 把来源拆解为原子测试条款（atomic_clauses）：
   - clause_id 用简短稳定标识（如 REQ-001、API-001）；
   - text 是该条款的可验证内容；
   - priority 为 P0/P1/P2；
   - source_ref 指向来源中的依据（章节或字段，可空）。
2. 为每个条款规划覆盖维度（coverage_plan）：
   - dimension 只能从：正常场景 / 异常场景 / 边界场景 / 业务规则场景 中选择；
   - 每条 coverage_plan 对应一个 clause_id。
3. 无法确认的内容写入 assumptions；发现的风险写入 warnings。
