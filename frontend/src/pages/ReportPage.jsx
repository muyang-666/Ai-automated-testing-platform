import { useState } from "react";
import { Button, Card, Form, InputNumber, message, Space, Typography } from "antd";
import api from "../services/api";

const { Paragraph } = Typography;

function ReportPage() {
  const [report, setReport] = useState(null);

  const handleGenerateReport = async (values) => {
    try {
      await api.post(`/reports/${values.run_id}/generate`);
      const res = await api.get(`/reports/${values.run_id}`);
      setReport(res.data);
      message.success("测试报告生成成功");
    } catch (error) {
      message.error("生成测试报告失败");
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card title="生成测试报告">
        <Form layout="inline" onFinish={handleGenerateReport}>
          <Form.Item name="run_id" label="Run ID" rules={[{ required: true }]}>
            <InputNumber min={1} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            生成报告
          </Button>
        </Form>
      </Card>

      {report && (
        <Card title={`测试报告（Run ID: ${report.run_id}）`}>
          <p>总数：{report.total_count}</p>
          <p>通过：{report.passed_count}</p>
          <p>失败：{report.failed_count}</p>
          <p>通过率：{report.pass_rate}%</p>
          <p>风险总结：{report.risk_summary}</p>
          <Paragraph copyable={{ text: report.summary }}>
            {report.summary}
          </Paragraph>
        </Card>
      )}
    </Space>
  );
}

export default ReportPage;