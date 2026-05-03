import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Checkbox,
  Col,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import api from "../services/api";
import { getProjectList } from "../api/project";
import ModuleTree from "../components/ModuleTree";

const CASE_TYPE_OPTIONS = [
  { label: "正常场景", value: "正常场景" },
  { label: "异常场景", value: "异常场景" },
  { label: "边界场景", value: "边界场景" },
  { label: "参数缺失", value: "参数缺失" },
  { label: "参数类型错误", value: "参数类型错误" },
  { label: "权限异常", value: "权限异常" },
  { label: "其他", value: "其他" },
];

const SOURCE_OPTIONS = [
  { label: "manual", value: "manual" },
  { label: "llm", value: "llm" },
  { label: "rule", value: "rule" },
];

const PRIORITY_OPTIONS = [
  { label: "P0", value: "P0" },
  { label: "P1", value: "P1" },
  { label: "P2", value: "P2" },
];

const STATUS_OPTIONS = [
  { label: "active", value: "active" },
  { label: "disabled", value: "disabled" },
  { label: "draft", value: "draft" },
];

const { Paragraph } = Typography;

const parseAnalysisContent = (content) => {
  const text = content || "";
  const getSection = (title, nextTitles = []) => {
    const escapedNextTitles = nextTitles.map((item) =>
      item.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
    );
    const allTitles =
      escapedNextTitles.length > 0 ? escapedNextTitles.join("|") : "$";
    const titleRegex = title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(
      `${titleRegex}[：:]?([\\s\\S]*?)(?=${allTitles}|$)`
    );
    const match = text.match(regex);
    return match ? match[1].trim() : "";
  };
  return {
    phenomenon: getSection("问题现象", [
      "问题本质",
      "责任归属",
      "关键证据",
      "修复建议",
      "风险等级",
    ]),
    essence: getSection("问题本质", [
      "责任归属",
      "关键证据",
      "修复建议",
      "风险等级",
    ]),
    owner: getSection("责任归属", ["关键证据", "修复建议", "风险等级"]),
    evidence: getSection("关键证据", ["修复建议", "风险等级"]),
    suggestion: getSection("修复建议", ["风险等级"]),
    risk: getSection("风险等级", []),
  };
};

function CasePage() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState("create");
  const [currentCase, setCurrentCase] = useState(null);
  const [form] = Form.useForm();

  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [selectedModuleId, setSelectedModuleId] = useState(null);
  const [includeChildren, setIncludeChildren] = useState(false);

  const [executing, setExecuting] = useState(null);
  const [executeResult, setExecuteResult] = useState(null);
  const [executeResultModalOpen, setExecuteResultModalOpen] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisModalOpen, setAnalysisModalOpen] = useState(false);
  const [currentAnalysis, setCurrentAnalysis] = useState(null);

  const fetchProjects = async () => {
    try {
      const res = await getProjectList();
      setProjects(res.data || []);
    } catch (error) {
      message.error("获取项目列表失败");
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  useEffect(() => {
    if (projects.length > 0 && selectedProjectId == null) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects]);

  const fetchCases = async () => {
    if (!selectedProjectId) return;
    setLoading(true);
    try {
      const params = { project_id: selectedProjectId };
      if (selectedModuleId != null) {
        params.module_id = selectedModuleId;
        if (includeChildren) {
          params.include_children = true;
        }
      }
      const res = await api.get("/cases", { params });
      setCases(res.data);
    } catch (error) {
      message.error("获取用例列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCases();
  }, [selectedProjectId, selectedModuleId, includeChildren]);

  const handleProjectChange = (value) => {
    setSelectedProjectId(value);
    setSelectedModuleId(null);
  };

  const handleModuleSelect = (moduleId) => {
    setSelectedModuleId(moduleId);
  };

  const handleModuleChange = () => {
    fetchCases();
  };

  const openCreateModal = () => {
    if (!selectedProjectId) {
      message.warning("请先选择项目");
      return;
    }
    setModalMode("create");
    setCurrentCase(null);
    form.resetFields();
    form.setFieldsValue({
      project_id: selectedProjectId,
      module_id: selectedModuleId || undefined,
      method: "",
    });
    setModalOpen(true);
  };

  const openEditModal = (record) => {
    setModalMode("edit");
    setCurrentCase(record);
    form.setFieldsValue({
      name: record.name,
      description: record.description,
      method: record.method,
      url: record.url,
      headers: record.headers,
      body: record.body,
      expected_result: record.expected_result,
      project_id: record.project_id,
      module_id: record.module_id,
      case_type: record.case_type,
      source: record.source,
      priority: record.priority,
      status: record.status,
    });
    setModalOpen(true);
  };

  const handleCancelModal = () => {
    setModalOpen(false);
    setCurrentCase(null);
    form.resetFields();
  };

  const handleSubmitCase = async (values) => {
    setSubmitting(true);
    try {
      if (modalMode === "create") {
        await api.post("/cases", values);
        message.success("测试用例创建成功");
      } else {
        await api.put(`/cases/${currentCase.id}`, values);
        message.success("测试用例更新成功");
      }
      handleCancelModal();
      fetchCases();
    } catch (error) {
      message.error(
        modalMode === "create" ? "创建测试用例失败" : "更新测试用例失败"
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteCase = async (caseId) => {
    try {
      await api.delete(`/cases/${caseId}`);
      message.success("测试用例删除成功");
      fetchCases();
    } catch (error) {
      message.error("删除测试用例失败");
    }
  };

  const handleGenerateByLLM = async (caseId) => {
    try {
      const res = await api.post(`/ai/generate-case/${caseId}`);
      message.success(`AI生成成功（来源：${res.data.generated_by}）`);
      try {
        await fetchCases();
      } catch (refreshError) {
        message.warning("代码已生成成功，但列表刷新失败，请手动刷新页面");
      }
    } catch (error) {
      const detail = error?.response?.data?.detail || "AI生成失败";
      message.error(detail);
    }
  };

  const handleGenerateByRule = async (caseId) => {
    try {
      const res = await api.post(`/ai/generate-rule-case/${caseId}`);
      message.success(`规则生成成功（来源：${res.data.generated_by}）`);
      try {
        await fetchCases();
      } catch (refreshError) {
        message.warning("代码已生成成功，但列表刷新失败，请手动刷新页面");
      }
    } catch (error) {
      const detail = error?.response?.data?.detail || "规则生成失败";
      message.error(detail);
    }
  };

  const handleExecute = async (caseId) => {
    setExecuting(caseId);
    try {
      const res = await api.post(`/runs/${caseId}/execute`);
      setExecuteResult(res.data);
      setExecuteResultModalOpen(true);
      message.success("测试执行完成");
    } catch (error) {
      const detail = error?.response?.data?.detail || "测试执行失败";
      message.error(detail);
    } finally {
      setExecuting(null);
    }
  };

  const handleAnalyze = async (runId) => {
    setAnalyzing(true);
    try {
      const res = await api.post(`/ai/analyze/${runId}`);
      setCurrentAnalysis(res.data);
      setAnalysisModalOpen(true);
      message.success("AI 分析完成");
    } catch (error) {
      const detail = error?.response?.data?.detail || "AI 分析失败";
      message.error(detail);
    } finally {
      setAnalyzing(false);
    }
  };

  const columns = [
    { title: "ID", dataIndex: "id", width: 60 },
    { title: "名称", dataIndex: "name", width: 120, ellipsis: true },
    { title: "方法", dataIndex: "method", width: 80 },
    { title: "URL", dataIndex: "url", width: 160, ellipsis: true },
    {
      title: "项目ID",
      dataIndex: "project_id",
      width: 75,
      render: (value) => (value != null ? value : "-"),
    },
    {
      title: "模块ID",
      dataIndex: "module_id",
      width: 75,
      render: (value) => (value != null ? value : "-"),
    },
    {
      title: "类型",
      dataIndex: "case_type",
      width: 90,
      ellipsis: true,
      render: (value) => value || "-",
    },
    {
      title: "来源",
      dataIndex: "source",
      width: 70,
      render: (value) => {
        if (!value) return "-";
        const colorMap = { manual: "blue", llm: "green", rule: "orange" };
        return <Tag color={colorMap[value] || "default"}>{value}</Tag>;
      },
    },
    {
      title: "优先级",
      dataIndex: "priority",
      width: 70,
      render: (value) => {
        if (!value) return "-";
        const colorMap = { P0: "red", P1: "orange", P2: "blue" };
        return <Tag color={colorMap[value] || "default"}>{value}</Tag>;
      },
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 75,
      render: (value) => {
        if (!value) return "-";
        const colorMap = { active: "green", disabled: "red", draft: "default" };
        return <Tag color={colorMap[value] || "default"}>{value}</Tag>;
      },
    },
    {
      title: "已生成代码",
      dataIndex: "generated_test_code",
      width: 110,
      render: (value) => (value ? "是" : "否"),
    },
    {
      title: "操作",
      width: 420,
      render: (_, record) => (
        <Space size="small" wrap>
          <Button size="small" onClick={() => openEditModal(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除这条测试用例吗？"
            okText="确认"
            cancelText="取消"
            onConfirm={() => handleDeleteCase(record.id)}
          >
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
          <Button size="small" onClick={() => handleGenerateByRule(record.id)}>
            规则生成
          </Button>
          <Button
            size="small"
            type="primary"
            loading={executing === record.id}
            onClick={() => handleExecute(record.id)}
          >
            执行测试
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Row justify="space-between" align="middle">
          <Col>
            <Space>
              <span>项目：</span>
              <Select
                placeholder="请选择项目"
                value={selectedProjectId}
                onChange={handleProjectChange}
                options={projects.map((p) => ({ label: p.name, value: p.id }))}
                style={{ width: 200 }}
                loading={projects.length === 0}
              />
            </Space>
          </Col>
          <Col>
            <Button type="primary" onClick={openCreateModal}>
              新建测试用例
            </Button>
          </Col>
        </Row>
      </Card>

      <div style={{ display: "flex", gap: 16 }}>
        <div style={{ width: 260, flexShrink: 0 }}>
          <ModuleTree
            projectId={selectedProjectId}
            selectedModuleId={selectedModuleId}
            onSelect={handleModuleSelect}
            onChange={handleModuleChange}
          />
          <Checkbox
            checked={includeChildren}
            onChange={(e) => setIncludeChildren(e.target.checked)}
            style={{ marginTop: 8 }}
          >
            包含子模块
          </Checkbox>
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <Card title="测试用例列表">
            <Table
              rowKey="id"
              columns={columns}
              dataSource={cases}
              loading={loading}
              pagination={false}
              scroll={{ x: 1400 }}
              size="small"
            />
          </Card>
        </div>
      </div>

      <Modal
        title={modalMode === "create" ? "新建测试用例" : "编辑测试用例"}
        open={modalOpen}
        onCancel={handleCancelModal}
        onOk={() => form.submit()}
        confirmLoading={submitting}
        destroyOnClose
        width={640}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmitCase}>
          <Form.Item
            name="name"
            label="用例名称"
            rules={[{ required: true, message: "请输入用例名称" }]}
          >
            <Input />
          </Form.Item>

          <Form.Item name="description" label="用例描述">
            <Input />
          </Form.Item>

          <Form.Item
            name="method"
            label="请求方法"
            rules={[{ required: true, message: "请输入请求方法" }]}
          >
            <Input placeholder="POST" />
          </Form.Item>

          <Form.Item
            name="url"
            label="请求地址"
            rules={[{ required: true, message: "请输入请求地址" }]}
          >
            <Input placeholder="http://example.com/api/login" />
          </Form.Item>

          <Form.Item name="headers" label="请求头">
            <Input.TextArea
              rows={2}
              placeholder='{"Content-Type": "application/json"}'
            />
          </Form.Item>

          <Form.Item name="body" label="请求体">
            <Input.TextArea
              rows={3}
              placeholder='{"username": "test", "password": "123456"}'
            />
          </Form.Item>

          <Form.Item name="expected_result" label="预期结果">
            <Input.TextArea
              rows={3}
              placeholder='{"code": 200, "message": "success"}'
            />
          </Form.Item>

          <Form.Item
            name="project_id"
            label="归属项目"
            rules={[{ required: true, message: "请选择项目" }]}
          >
            <Select
              placeholder="请选择项目"
              options={projects.map((p) => ({ label: p.name, value: p.id }))}
            />
          </Form.Item>

          <Form.Item name="module_id" label="归属模块">
            <InputNumber
              placeholder="模块ID（可选）"
              style={{ width: "100%" }}
            />
          </Form.Item>

          <Form.Item name="case_type" label="用例类型">
            <Select
              placeholder="请选择用例类型"
              allowClear
              options={CASE_TYPE_OPTIONS}
            />
          </Form.Item>

          <Form.Item name="source" label="来源">
            <Select
              placeholder="请选择来源"
              allowClear
              options={SOURCE_OPTIONS}
            />
          </Form.Item>

          <Form.Item name="priority" label="优先级">
            <Select
              placeholder="请选择优先级"
              allowClear
              options={PRIORITY_OPTIONS}
            />
          </Form.Item>

          <Form.Item name="status" label="状态">
            <Select
              placeholder="请选择状态"
              allowClear
              options={STATUS_OPTIONS}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`执行结果（Run ID: ${executeResult?.run_id ?? "-"}）`}
        open={executeResultModalOpen}
        onCancel={() => {
          setExecuteResultModalOpen(false);
          setExecuteResult(null);
        }}
        footer={null}
        width={700}
      >
        {executeResult ? (
          <Space direction="vertical" style={{ width: "100%" }} size={12}>
            <p>
              状态：<Tag>{executeResult.status}</Tag>
            </p>
            <p>
              结果：
              <Tag
                color={
                  executeResult.result === "passed"
                    ? "success"
                    : executeResult.result === "failed"
                      ? "error"
                      : "default"
                }
              >
                {executeResult.result ?? "unknown"}
              </Tag>
            </p>
            <p>总数：{executeResult.total_count ?? "-"}</p>
            <p>通过：{executeResult.passed_count ?? "-"}</p>
            <p>失败：{executeResult.failed_count ?? "-"}</p>
            <p>
              接口响应状态码：{executeResult.response_status_code ?? "无"}
            </p>
            {executeResult.response_content && (
              <>
                <p>
                  <b>响应内容：</b>
                </p>
                <Paragraph copyable={{ text: executeResult.response_content }}>
                  <pre
                    style={{
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                      maxHeight: 300,
                      overflow: "auto",
                      background: "#f5f5f5",
                      padding: 12,
                      borderRadius: 4,
                    }}
                  >
                    {executeResult.response_content}
                  </pre>
                </Paragraph>
              </>
            )}
            {executeResult.result === "failed" && (
              <Button
                type="primary"
                loading={analyzing}
                onClick={() => handleAnalyze(executeResult.run_id)}
              >
                AI 分析
              </Button>
            )}
          </Space>
        ) : (
          <p>无执行结果</p>
        )}
      </Modal>

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
                {parsed.owner && (
                  <p>
                    <b>责任归属：</b>
                    {parsed.owner}
                  </p>
                )}
                {parsed.phenomenon && (
                  <p>
                    <b>问题现象：</b>
                    {parsed.phenomenon}
                  </p>
                )}
                {parsed.essence && (
                  <p>
                    <b>问题本质：</b>
                    {parsed.essence}
                  </p>
                )}
                {parsed.evidence && (
                  <Paragraph>
                    <b>关键证据：</b>
                    <pre
                      style={{
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        marginTop: 8,
                      }}
                    >
                      {parsed.evidence}
                    </pre>
                  </Paragraph>
                )}
                {parsed.suggestion && (
                  <Paragraph>
                    <b>修复建议：</b>
                    <pre
                      style={{
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        marginTop: 8,
                      }}
                    >
                      {parsed.suggestion}
                    </pre>
                  </Paragraph>
                )}
                <Paragraph copyable={{ text: currentAnalysis.content || "" }}>
                  <details>
                    <summary>查看原始分析全文</summary>
                    <pre
                      style={{
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        marginTop: 8,
                      }}
                    >
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

export default CasePage;
