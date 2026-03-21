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

// 兼容两种返回风格：
// 1. axios 原始响应对象 -> { data: ... }
// 2. 项目自定义封装后直接返回 data
const unwrapResponse = (res) => {
  return res?.data !== undefined ? res.data : res;
};

// 把 AI 分析结果按结构拆出来，方便前端精炼展示
const parseAnalysisContent = (content) => {
  const text = content || "";

  const getSection = (title, nextTitles = []) => {
    const escapedNextTitles = nextTitles.map((item) => item.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const allTitles = escapedNextTitles.length > 0 ? escapedNextTitles.join("|") : "$";
    const titleRegex = title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(`${titleRegex}[：:]?([\\s\\S]*?)(?=${allTitles}|$)`);
    const match = text.match(regex);
    return match ? match[1].trim() : "";
  };

  return {
    phenomenon: getSection("问题现象", ["问题本质", "责任归属", "关键证据", "修复建议", "风险等级"]),
    essence: getSection("问题本质", ["责任归属", "关键证据", "修复建议", "风险等级"]),
    owner: getSection("责任归属", ["关键证据", "修复建议", "风险等级"]),
    evidence: getSection("关键证据", ["修复建议", "风险等级"]),
    suggestion: getSection("修复建议", ["风险等级"]),
    risk: getSection("风险等级", []),
  };
};

function RunPage() {
  // 最近一次执行结果，只保留概要展示
  const [runResult, setRunResult] = useState(null);

  // 执行记录表格数据
  const [runList, setRunList] = useState([]);
  const [loading, setLoading] = useState(false);

  // 日志弹窗相关状态
  const [logModalOpen, setLogModalOpen] = useState(false);
  const [currentLog, setCurrentLog] = useState("");

  // 响应结果弹窗相关状态
  const [responseModalOpen, setResponseModalOpen] = useState(false);
  const [currentResponseContent, setCurrentResponseContent] = useState("");
  const [currentResponseStatusCode, setCurrentResponseStatusCode] = useState(null);

  // AI分析弹窗相关状态
  const [analysisModalOpen, setAnalysisModalOpen] = useState(false);
  const [currentAnalysis, setCurrentAnalysis] = useState(null);

  // 获取执行记录列表
  const fetchRuns = async () => {
    setLoading(true);
    try {
      const res = await api.get("/runs");
      const data = unwrapResponse(res);
      setRunList(data || []);
    } catch (error) {
      message.error(error?.response?.data?.detail || "获取执行记录列表失败");
    } finally {
      setLoading(false);
    }
  };

  // 执行测试
  const handleExecute = async (values) => {
    try {
      const res = await api.post(`/runs/${values.case_id}/execute`);
      const data = unwrapResponse(res);
      setRunResult(data);
      message.success("测试执行完成");
      fetchRuns();
    } catch (error) {
      const detail = error?.response?.data?.detail || "测试执行失败";
      message.error(detail);
    }
  };

  // 触发 AI 分析，并直接使用 POST 返回值展示
  const handleAnalyze = async (runId) => {
    try {
      const res = await api.post(`/ai/analyze/${runId}`);
      const data = unwrapResponse(res);

      setCurrentAnalysis(data);
      setAnalysisModalOpen(true);
      message.success("AI 日志分析完成");
    } catch (error) {
      const detail = error?.response?.data?.detail || "AI 日志分析失败";
      message.error(detail);
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
      message.error(error?.response?.data?.detail || "删除执行记录失败");
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
      title: "AI分析结果",
      width: 140,
      render: (_, record) => {
        if (record.result !== "failed") {
          return <Tag color="default">仅失败记录可分析</Tag>;
        }

        return (
          <Button onClick={() => handleAnalyze(record.run_id)}>
            查看AI分析
          </Button>
        );
      },
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
          <Form.Item
            name="case_id"
            label="Case ID"
            rules={[{ required: true, message: "请输入 Case ID" }]}
          >
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
            {currentResponseContent || "当前无响应结果"}
          </pre>
        </Paragraph>
      </Modal>

      {/* AI分析结果弹窗 */}
      <Modal
        title="AI 分析结果"
        open={analysisModalOpen}
        onCancel={() => {
          setAnalysisModalOpen(false);
          setCurrentAnalysis(null);
        }}
        footer={null}
        width={900}
      >
        {currentAnalysis ? (
          (() => {
            const parsed = parseAnalysisContent(currentAnalysis.content);

            return (
              <Space direction="vertical" style={{ width: "100%" }} size={12}>
                <p>分析类型：{currentAnalysis.analysis_type}</p>
                <p>风险等级：{currentAnalysis.risk_level}</p>

                {parsed.owner && <p><b>责任归属：</b>{parsed.owner}</p>}
                {parsed.phenomenon && <p><b>问题现象：</b>{parsed.phenomenon}</p>}
                {parsed.essence && <p><b>问题本质：</b>{parsed.essence}</p>}

                {parsed.evidence && (
                  <Paragraph>
                    <b>关键证据：</b>
                    <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", marginTop: 8 }}>
                      {parsed.evidence}
                    </pre>
                  </Paragraph>
                )}

                {parsed.suggestion && (
                  <Paragraph>
                    <b>修复建议：</b>
                    <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", marginTop: 8 }}>
                      {parsed.suggestion}
                    </pre>
                  </Paragraph>
                )}

                <Paragraph copyable={{ text: currentAnalysis.content || "" }}>
                  <details>
                    <summary>查看原始分析全文</summary>
                    <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", marginTop: 8 }}>
                      {currentAnalysis.content || "当前无分析内容"}
                    </pre>
                  </details>
                </Paragraph>
              </Space>
            );
          })()
        ) : (
          <p>当前无分析内容</p>
        )}
      </Modal>
    </Space>
  );
}

export default RunPage;