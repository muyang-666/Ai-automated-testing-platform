请针对以下缺口做**局部修正**，不要全量重新生成。

【原子条款】
{atomic_clauses}

【校验错误】（candidate_id 与错误列表）
{validation_errors}

【重复摘要】（安全指纹信息）
{duplicate_summary}

【缺失覆盖的条款】
{missing_coverage}

【需要修正的候选子集】（只包含有问题的候选）
{problem_candidates}

【用户要求】
- 请求覆盖的用例类型：{case_types}
- 最大候选数：{max_cases}
- 补充目标：{user_goal}

【任务】
1. 只修复或补充与上述错误/缺口相关的候选：
   - 修正已有候选时，candidate_id 必须与问题候选一致；
   - 新增候选时 candidate_id 留空（由系统分配）。
2. 不要重发未修改的候选，不要重发无关内容。
3. covered_clause_ids 必须引用真实条款 clause_id。
