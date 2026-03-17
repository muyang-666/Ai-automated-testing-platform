// 消费测试内容并产出执行结果

import { useState } from "react";
import { Button, Card, Form, InputNumber, message, Space, Typography } from "antd";
import api from "../services/api";

const { Paragraph } = Typography;

function RunPage() {
  // runResult表示：测试执行接口返回的结果
  const [runResult, setRunResult] = useState(null);
  // analysisResult表示：AI 日志分析接口返回的结果
  const [analysisResult, setAnalysisResult] = useState(null);

  // 执行测试的前端入口
  const handleExecute = async (values) => {
    try {
      const res = await api.post(`/runs/${values.case_id}/execute`);
      // 执行完成后，把返回结果保存到页面状态里
      setRunResult(res.data);
      // 当用户重新执行一条测试时，先把上一次的 AI 分析结果清空
      setAnalysisResult(null);
      message.success("测试执行完成");
    } catch (error) {
      message.error("测试执行失败");
    }
  };

  // 触发 AI 日志分析
  const handleAnalyze = async (runId) => {
    try {
      const res = await api.post(`/ai/analyze/${runId}`);
      setAnalysisResult(res.data);
      message.success("AI 日志分析完成");
    } catch (error) {
      message.error("AI 日志分析失败");
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card title="执行测试">
        <Form layout="inline" onFinish={handleExecute}>
          <Form.Item name="case_id" label="Case ID" rules={[{ required: true }]}>
            <InputNumber min={1} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            执行测试
          </Button>
        </Form>
      </Card>

      {runResult && (
        <Card title={`执行结果（Run ID: ${runResult.run_id}）`}>
          <p>状态：{runResult.status}</p>
          <p>结果：{runResult.result}</p>
          <p>总数：{runResult.total_count}</p>
          <p>通过：{runResult.passed_count}</p>
          <p>失败：{runResult.failed_count}</p>
          <Paragraph copyable={{ text: runResult.log_content }}>
            日志：{runResult.log_content}
          </Paragraph>

          <Button type="primary" onClick={() => handleAnalyze(runResult.run_id)}>
            AI分析失败日志
          </Button>
        </Card>
      )}

      {analysisResult && (
        <Card title="AI 分析结果">
          <p>分析类型：{analysisResult.analysis_type}</p>
          <p>风险等级：{analysisResult.risk_level}</p>
          <Paragraph copyable={{ text: analysisResult.content }}>
            {analysisResult.content}
          </Paragraph>
        </Card>
      )}
    </Space>
  );
}

export default RunPage;