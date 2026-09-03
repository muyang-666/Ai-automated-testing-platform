请根据已确认的覆盖计划生成候选用例。

【原子条款】
{atomic_clauses}

【已确认覆盖计划】
{coverage_plan}

【已有用例摘要】（避免重复；系统会做确定性去重，你不需要自报覆盖率）
{existing_cases}

【用户要求】
- 请求覆盖的用例类型：{case_types}
- 最大候选数：{max_cases}
- 补充目标：{user_goal}

【已确认假设】
{assumptions}

【任务】
1. 为覆盖计划中的条款生成候选用例，最多 {max_cases} 条。
2. 每条候选的 covered_clause_ids 必须引用上述真实条款的 clause_id，不要编造。
3. 同一接口（method+url）下的不同测试场景（正常/参数缺失/取值错误/边界）应生成多条不同候选。
4. 字段要求：
   - 功能用例（function）：case_name、case_type、priority、precondition、steps_json（步骤数组）、test_data_json（对象）、expected_result、covered_clause_ids；
   - 接口用例（api）：name、description、method、url、headers（对象）、body（对象/数组/字符串/null）、expected_result（对象/字符串）、case_type、priority、covered_clause_ids。
5. 鉴权相关场景只描述测试意图，不得输出任何真实凭证。
