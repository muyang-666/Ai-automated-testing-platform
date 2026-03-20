// 消费测试内容并产出执行结果

import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Form,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import api from "../services/api";

const { Paragraph } = Typography;

function RunPage() {
  // runResult表示：最近一次测试执行接口返回的结果
  const [runResult, setRunResult] = useState(null);
  // analysisResult表示：AI 日志分析接口返回的结果
  const [analysisResult, setAnalysisResult] = useState(null);
  // runList表示：执行记录管理表格数据
  const [runList, setRunList] = useState([]);
  // loading表示：执行记录列表是否在加载
  const [loading, setLoading] = useState(false);

  // 日志弹窗相关状态
  const [logModalOpen, setLogModalOpen] = useState(false);
  const [currentLog, setCurrentLog] = useState("");

  // 响应结果弹窗相关状态
  const [responseModalOpen, setResponseModalOpen] = useState(false);
  const [currentResponseContent, setCurrentResponseContent] = useState("");
  const [currentResponseStatusCode, setCurrentResponseStatusCode] = useState(null);

  // 获取执行记录列表
  const fetchRuns = async () => {
    setLoading(true);
    try {
      const res = await api.get("/runs");
      setRunList(res.data);
    } catch (error) {
      message.error("获取执行记录列表失败");
    } finally {
      setLoading(false);
    }
  };

  // 执行测试的前端入口
  const handleExecute = async (values) => {
    try {
      const res = await api.post(`/runs/${values.case_id}/execute`);
      // 执行完成后，把返回结果保存到页面状态里
      setRunResult(res.data);
      // 当用户重新执行一条测试时，先把上一次的 AI 分析结果清空
      setAnalysisResult(null);
      message.success("测试执行完成");
      fetchRuns(); // 执行成功后刷新执行记录表格
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

  // 打开日志弹窗
  const openLogModal = (logContent) => {
    setCurrentLog(logContent || "");
    setLogModalOpen(true);
  };

  // 打开响应结果弹窗
  const openResponseModal = (responseStatusCode, responseContent) => {
    setCurrentResponseStatusCode(responseStatusCode);
    setCurrentResponseContent(responseContent || "");
    setResponseModalOpen(true);
  };

  // 删除执行记录
  const handleDeleteRun = async (runId) => {
    try {
      await api.delete(`/runs/${runId}`);
      message.success("执行记录删除成功");
      fetchRuns();
    } catch (error) {
      message.error("删除执行记录失败");
    }
  };

  useEffect(() => {
    fetchRuns();
  }, []);

  // 执行记录表格列定义
  const columns = [
    { title: "Run ID", dataIndex: "run_id", width: 100 },
    { title: "关联 Case ID", dataIndex: "case_id", width: 120 },
    {
      title: "结果",
      dataIndex: "result",
      width: 100,
      render: (value) => {
        if (value === "passed") {
          return <Tag color="success">passed</Tag>;
        }
        if (value === "failed") {
          return <Tag color="error">failed</Tag>;
        }
        return <Tag>{value || "unknown"}</Tag>;
      },
    },
    {
      title: "查看详细日志",
      width: 140,
      render: (_, record) => (
        <Button onClick={() => openLogModal(record.log_content)}>
          查看详细日志
        </Button>
      ),
    },
    {
      title: "查看响应结果",
      width: 160,
      render: (_, record) => (
        <Button
          type="primary"
          onClick={() =>
            openResponseModal(record.response_status_code, record.response_content)
          }
        >
          查看响应结果
        </Button>
      ),
    },
    {
      title: "操作",
      width: 100,
      render: (_, record) => (
        <Popconfirm
          title="确认删除这条执行记录吗？"
          okText="确认"
          cancelText="取消"
          onConfirm={() => handleDeleteRun(record.run_id)}
        >
          <Button danger>删除</Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card title="执行测试">
        <Form layout="inline" onFinish={handleExecute}>
          <Form.Item name="case_id" label="Case ID" rules={[{ required: true, message: "请输入 Case ID" }]}>
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
          <p>接口响应状态码：{runResult.response_status_code ?? "无"}</p>

          <Paragraph copyable={{ text: runResult.log_content || "" }}>
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
          <Paragraph copyable={{ text: analysisResult.content || "" }}>
            {analysisResult.content}
          </Paragraph>
        </Card>
      )}

      <Card title="执行管理">
        <Table
          rowKey="run_id"
          columns={columns}
          dataSource={runList}
          loading={loading}
          pagination={{ pageSize: 5 }}
        />
      </Card>

      {/* 详细日志弹窗 */}
      <Modal
        title="详细日志"
        open={logModalOpen}
        onCancel={() => setLogModalOpen(false)}
        footer={null}
        width={900}
      >
        <Paragraph copyable={{ text: currentLog || "" }}>
          <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {currentLog || "当前无日志内容"}
          </pre>
        </Paragraph>
      </Modal>

      {/* 响应结果弹窗 */}
      <Modal
        title="响应结果"
        open={responseModalOpen}
        onCancel={() => setResponseModalOpen(false)}
        footer={null}
        width={900}
      >
        <p>接口响应状态码：{currentResponseStatusCode ?? "无"}</p>
        <Paragraph copyable={{ text: currentResponseContent || "" }}>
          <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {currentResponseContent || "当前无响应结果（可能请求异常、未成功拿到 response，或这条执行记录是旧数据）"}
          </pre>
        </Paragraph>
      </Modal>
    </Space>
  );
}

export default RunPage;