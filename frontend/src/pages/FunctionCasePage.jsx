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
} from "antd";
import {
  createFunctionCase,
  deleteFunctionCase,
  getFunctionCaseList,
  updateFunctionCase,
} from "../api/functionCase";
import { getProjectList } from "../api/project";
import { getRequirementList } from "../api/requirement";
import ModuleTree from "../components/ModuleTree";

function getErrorMessage(error) {
  return (
    error?.response?.data?.detail ||
    error?.response?.data?.message ||
    error?.message ||
    "操作失败"
  );
}

function parseJsonField(value, fieldName) {
  if (!value || value.trim() === "") return null;
  try {
    return JSON.parse(value);
  } catch (e) {
    message.error(`${fieldName}不是合法 JSON`);
    throw e;
  }
}

function formatJson(value) {
  if (value == null) return "";
  return JSON.stringify(value, null, 2);
}

const CASE_TYPE_OPTIONS = [
  { label: "正常场景", value: "正常场景" },
  { label: "异常场景", value: "异常场景" },
  { label: "边界场景", value: "边界场景" },
  { label: "业务规则场景", value: "业务规则场景" },
  { label: "其他", value: "其他" },
];

const SOURCE_OPTIONS = [
  { label: "manual", value: "manual" },
  { label: "llm", value: "llm" },
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

const SOURCE_TAG_MAP = {
  manual: { color: "blue", label: "manual" },
  llm: { color: "green", label: "llm" },
};

const PRIORITY_TAG_MAP = {
  P0: { color: "red", label: "P0" },
  P1: { color: "orange", label: "P1" },
  P2: { color: "blue", label: "P2" },
};

const STATUS_TAG_MAP = {
  active: { color: "green", label: "active" },
  disabled: { color: "error", label: "disabled" },
  draft: { color: "default", label: "draft" },
};

const FILTER_ALL = "";

export default function FunctionCasePage() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState("create");
  const [editingCase, setEditingCase] = useState(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [detailCase, setDetailCase] = useState(null);
  const [form] = Form.useForm();

  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [selectedModuleId, setSelectedModuleId] = useState(null);
  const [includeChildren, setIncludeChildren] = useState(false);
  const [requirements, setRequirements] = useState([]);
  const [selectedRequirementId, setSelectedRequirementId] = useState(FILTER_ALL);
  const [keyword, setKeyword] = useState("");
  const [caseTypeFilter, setCaseTypeFilter] = useState(FILTER_ALL);
  const [sourceFilter, setSourceFilter] = useState(FILTER_ALL);
  const [priorityFilter, setPriorityFilter] = useState(FILTER_ALL);
  const [statusFilter, setStatusFilter] = useState(FILTER_ALL);

  const fetchProjects = async () => {
    try {
      const res = await getProjectList();
      setProjects(res.data || []);
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const fetchRequirements = async (projectId) => {
    if (!projectId) {
      setRequirements([]);
      return;
    }
    try {
      const res = await getRequirementList({ project_id: projectId });
      setRequirements(res.data || []);
    } catch (error) {
      message.error(getErrorMessage(error));
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

  useEffect(() => {
    if (selectedProjectId) {
      fetchCases();
    }
  }, [
    selectedProjectId,
    selectedModuleId,
    includeChildren,
    selectedRequirementId,
    keyword,
    caseTypeFilter,
    sourceFilter,
    priorityFilter,
    statusFilter,
  ]);

  const fetchCases = async () => {
    if (!selectedProjectId) return;
    setLoading(true);
    try {
      const params = { project_id: selectedProjectId };
      if (selectedModuleId != null) {
        params.module_id = selectedModuleId;
        if (includeChildren) params.include_children = true;
      }
      if (selectedRequirementId) params.requirement_id = selectedRequirementId;
      if (keyword) params.keyword = keyword;
      if (caseTypeFilter) params.case_type = caseTypeFilter;
      if (sourceFilter) params.source = sourceFilter;
      if (priorityFilter) params.priority = priorityFilter;
      if (statusFilter) params.status = statusFilter;
      const res = await getFunctionCaseList(params);
      setCases(res.data || []);
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const handleProjectChange = (value) => {
    setSelectedProjectId(value);
    setSelectedModuleId(null);
    setSelectedRequirementId(FILTER_ALL);
    fetchRequirements(value);
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
    setEditingCase(null);
    form.resetFields();
    form.setFieldsValue({
      project_id: selectedProjectId,
      module_id: selectedModuleId || undefined,
      source: "manual",
      priority: "P1",
      status: "active",
    });
    setModalOpen(true);
  };

  const openEditModal = (record) => {
    setModalMode("edit");
    setEditingCase(record);
    form.setFieldsValue({
      project_id: record.project_id,
      module_id: record.module_id,
      requirement_id: record.requirement_id,
      case_code: record.case_code,
      case_name: record.case_name,
      case_type: record.case_type,
      source: record.source,
      priority: record.priority,
      precondition: record.precondition,
      steps_json: formatJson(record.steps_json),
      test_data_json: formatJson(record.test_data_json),
      expected_result: record.expected_result,
      status: record.status,
      remark: record.remark,
    });
    setModalOpen(true);
  };

  const openDetailModal = (record) => {
    setDetailCase(record);
    setDetailModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingCase(null);
    form.resetFields();
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      const data = { ...values };
      data.steps_json = parseJsonField(values.steps_json, "测试步骤");
      data.test_data_json = parseJsonField(values.test_data_json, "测试数据");

      if (modalMode === "create") {
        await createFunctionCase(data);
        message.success("功能测试用例创建成功");
      } else {
        await updateFunctionCase(editingCase.id, data);
        message.success("功能测试用例更新成功");
      }

      closeModal();
      fetchCases();
    } catch (error) {
      if (error?.response) {
        message.error(getErrorMessage(error));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (caseId) => {
    try {
      await deleteFunctionCase(caseId);
      message.success("功能测试用例删除成功");
      fetchCases();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const columns = [
    { title: "ID", dataIndex: "id", width: 55 },
    { title: "编号", dataIndex: "case_code", width: 120, ellipsis: true, render: (v) => v || "-" },
    { title: "名称", dataIndex: "case_name", width: 160, ellipsis: true },
    {
      title: "模块ID",
      dataIndex: "module_id",
      width: 70,
      render: (value) => (value != null ? value : "-"),
    },
    {
      title: "需求ID",
      dataIndex: "requirement_id",
      width: 70,
      render: (value) => (value != null ? value : "-"),
    },
    {
      title: "类型",
      dataIndex: "case_type",
      width: 100,
      ellipsis: true,
      render: (value) => value || "-",
    },
    {
      title: "来源",
      dataIndex: "source",
      width: 75,
      render: (value) => {
        if (!value) return "-";
        const tag = SOURCE_TAG_MAP[value] || { color: "default", label: value };
        return <Tag color={tag.color}>{tag.label}</Tag>;
      },
    },
    {
      title: "优先级",
      dataIndex: "priority",
      width: 65,
      render: (value) => {
        if (!value) return "-";
        const tag = PRIORITY_TAG_MAP[value] || { color: "default", label: value };
        return <Tag color={tag.color}>{tag.label}</Tag>;
      },
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 75,
      render: (value) => {
        if (!value) return "-";
        const tag = STATUS_TAG_MAP[value] || { color: "default", label: value };
        return <Tag color={tag.color}>{tag.label}</Tag>;
      },
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 150,
      render: (value) => (value ? new Date(value).toLocaleString("zh-CN") : "-"),
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      width: 150,
      render: (value) => (value ? new Date(value).toLocaleString("zh-CN") : "-"),
    },
    {
      title: "操作",
      width: 260,
      render: (_, record) => (
        <Space size="small">
          <Button size="small" onClick={() => openDetailModal(record)}>
            查看详情
          </Button>
          <Button size="small" onClick={() => openEditModal(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该功能测试用例吗？"
            okText="确认"
            cancelText="取消"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Row justify="space-between" align="middle" gutter={[16, 8]}>
          <Col flex="auto">
            <Space wrap>
              <span>项目：</span>
              <Select
                placeholder="请选择项目"
                value={selectedProjectId}
                onChange={handleProjectChange}
                options={projects.map((p) => ({ label: p.name, value: p.id }))}
                style={{ width: 180 }}
              />
              <Input.Search
                placeholder="搜索编号/名称/前置条件/预期"
                allowClear
                onSearch={(v) => setKeyword(v)}
                style={{ width: 220 }}
              />
              <Select
                placeholder="需求筛选"
                allowClear
                value={selectedRequirementId || undefined}
                onChange={(v) => setSelectedRequirementId(v || FILTER_ALL)}
                options={requirements.map((r) => ({ label: r.title, value: r.id }))}
                style={{ width: 160 }}
              />
              <Select
                placeholder="类型"
                allowClear
                value={caseTypeFilter || undefined}
                onChange={(v) => setCaseTypeFilter(v || FILTER_ALL)}
                options={CASE_TYPE_OPTIONS}
                style={{ width: 120 }}
              />
              <Select
                placeholder="来源"
                allowClear
                value={sourceFilter || undefined}
                onChange={(v) => setSourceFilter(v || FILTER_ALL)}
                options={SOURCE_OPTIONS}
                style={{ width: 100 }}
              />
              <Select
                placeholder="优先级"
                allowClear
                value={priorityFilter || undefined}
                onChange={(v) => setPriorityFilter(v || FILTER_ALL)}
                options={PRIORITY_OPTIONS}
                style={{ width: 90 }}
              />
              <Select
                placeholder="状态"
                allowClear
                value={statusFilter || undefined}
                onChange={(v) => setStatusFilter(v || FILTER_ALL)}
                options={STATUS_OPTIONS}
                style={{ width: 100 }}
              />
            </Space>
          </Col>
          <Col>
            <Button type="primary" onClick={openCreateModal}>
              新增功能用例
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
          <Card title="功能测试用例列表">
            <Table
              rowKey="id"
              columns={columns}
              dataSource={cases}
              loading={loading}
              pagination={false}
              scroll={{ x: 1500 }}
              size="small"
            />
          </Card>
        </div>
      </div>

      <Modal
        title={modalMode === "create" ? "新增功能测试用例" : "编辑功能测试用例"}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={closeModal}
        confirmLoading={submitting}
        destroyOnClose
        width={700}
      >
        <Form form={form} layout="vertical">
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
            <InputNumber placeholder="模块ID（可选）" style={{ width: "100%" }} />
          </Form.Item>

          <Form.Item name="requirement_id" label="关联需求">
            <Select
              placeholder="请选择需求（可选）"
              allowClear
              options={requirements.map((r) => ({ label: r.title, value: r.id }))}
            />
          </Form.Item>

          <Form.Item name="case_code" label="用例编号">
            <Input placeholder="如 FC-LOGIN-001" maxLength={100} />
          </Form.Item>

          <Form.Item
            name="case_name"
            label="用例名称"
            rules={[{ required: true, message: "请输入用例名称" }]}
          >
            <Input placeholder="请输入用例名称" maxLength={200} />
          </Form.Item>

          <Form.Item name="case_type" label="用例类型">
            <Select placeholder="请选择用例类型" allowClear options={CASE_TYPE_OPTIONS} />
          </Form.Item>

          <Form.Item name="source" label="来源">
            <Select options={SOURCE_OPTIONS} />
          </Form.Item>

          <Form.Item name="priority" label="优先级">
            <Select options={PRIORITY_OPTIONS} />
          </Form.Item>

          <Form.Item name="precondition" label="前置条件">
            <Input.TextArea rows={2} placeholder="前置条件（可选）" />
          </Form.Item>

          <Form.Item name="steps_json" label="测试步骤 (JSON)">
            <Input.TextArea
              rows={3}
              placeholder='["步骤1", "步骤2", "步骤3"]'
            />
          </Form.Item>

          <Form.Item name="test_data_json" label="测试数据 (JSON)">
            <Input.TextArea
              rows={3}
              placeholder='{"key1": "value1", "key2": "value2"}'
            />
          </Form.Item>

          <Form.Item name="expected_result" label="预期结果">
            <Input.TextArea rows={3} placeholder="预期结果（可选）" />
          </Form.Item>

          <Form.Item name="status" label="状态">
            <Select options={STATUS_OPTIONS} />
          </Form.Item>

          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} placeholder="备注（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="功能用例详情"
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalOpen(false)}>
            关闭
          </Button>,
        ]}
        width={700}
      >
        {detailCase && (
          <div style={{ maxHeight: "60vh", overflow: "auto" }}>
            <p><strong>用例编号：</strong>{detailCase.case_code || "-"}</p>
            <p><strong>用例名称：</strong>{detailCase.case_name}</p>
            <p><strong>用例类型：</strong>{detailCase.case_type || "-"}</p>
            <p><strong>来源：</strong>{detailCase.source || "-"}</p>
            <p><strong>优先级：</strong>{detailCase.priority || "-"}</p>
            <p><strong>状态：</strong>{detailCase.status || "-"}</p>
            <p><strong>项目ID：</strong>{detailCase.project_id}</p>
            <p><strong>模块ID：</strong>{detailCase.module_id ?? "-"}</p>
            <p><strong>需求ID：</strong>{detailCase.requirement_id ?? "-"}</p>
            <p><strong>前置条件：</strong></p>
            <pre style={{ background: "#f5f5f5", padding: 8, borderRadius: 4 }}>
              {detailCase.precondition || "-"}
            </pre>
            <p><strong>测试步骤：</strong></p>
            <pre style={{ background: "#f5f5f5", padding: 8, borderRadius: 4, maxHeight: 200, overflow: "auto" }}>
              {formatJson(detailCase.steps_json) || "-"}
            </pre>
            <p><strong>测试数据：</strong></p>
            <pre style={{ background: "#f5f5f5", padding: 8, borderRadius: 4, maxHeight: 200, overflow: "auto" }}>
              {formatJson(detailCase.test_data_json) || "-"}
            </pre>
            <p><strong>预期结果：</strong></p>
            <pre style={{ background: "#f5f5f5", padding: 8, borderRadius: 4 }}>
              {detailCase.expected_result || "-"}
            </pre>
            {detailCase.remark && (
              <>
                <p><strong>备注：</strong></p>
                <pre style={{ background: "#f5f5f5", padding: 8, borderRadius: 4 }}>
                  {detailCase.remark}
                </pre>
              </>
            )}
          </div>
        )}
      </Modal>
    </Space>
  );
}
