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
import { getProjectList } from "../api/project";
import {
  createApiDocument,
  deleteApiDocument,
  generateApiCasesFromDocument,
  getApiDocumentList,
  saveGeneratedApiCases,
  updateApiDocument,
} from "../api/apiDocument";
import ModuleTree from "../components/ModuleTree";

function getErrorMessage(error) {
  return (
    error?.response?.data?.detail ||
    error?.response?.data?.message ||
    error?.message ||
    "操作失败"
  );
}

const METHOD_OPTIONS = [
  { label: "全部", value: "" },
  { label: "GET", value: "GET" },
  { label: "POST", value: "POST" },
  { label: "PUT", value: "PUT" },
  { label: "DELETE", value: "DELETE" },
  { label: "PATCH", value: "PATCH" },
];

const STATUS_OPTIONS = [
  { label: "全部", value: "" },
  { label: "active", value: "active" },
  { label: "disabled", value: "disabled" },
  { label: "draft", value: "draft" },
];

const FORM_STATUS_OPTIONS = [
  { label: "active", value: "active" },
  { label: "disabled", value: "disabled" },
  { label: "draft", value: "draft" },
];

const PRIORITY_TAG_MAP = {
  P0: { color: "red", label: "P0" },
  P1: { color: "orange", label: "P1" },
  P2: { color: "blue", label: "P2" },
};

function ApiDocPage() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);

  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [selectedModuleId, setSelectedModuleId] = useState(null);
  const [includeChildren, setIncludeChildren] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [methodFilter, setMethodFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  // CRUD modal
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState("create");
  const [currentDoc, setCurrentDoc] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  // Detail modal
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailDoc, setDetailDoc] = useState(null);

  // Generate cases
  const [generating, setGenerating] = useState(null);
  const [genPreviewOpen, setGenPreviewOpen] = useState(false);
  const [genPreview, setGenPreview] = useState(null);
  const [selectedCaseKeys, setSelectedCaseKeys] = useState([]);
  const [saving, setSaving] = useState(false);

  const fetchProjects = async () => {
    try {
      const res = await getProjectList();
      setProjects(res.data || []);
    } catch {
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

  const fetchDocuments = async () => {
    if (!selectedProjectId) return;
    setLoading(true);
    try {
      const params = { project_id: selectedProjectId };
      if (selectedModuleId != null) {
        params.module_id = selectedModuleId;
        if (includeChildren) params.include_children = true;
      }
      if (keyword) params.keyword = keyword;
      if (methodFilter) params.method = methodFilter;
      if (statusFilter) params.status = statusFilter;
      const res = await getApiDocumentList(params);
      setDocuments(res.data || []);
    } catch {
      message.error("获取接口文档列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, [selectedProjectId, selectedModuleId, includeChildren]);

  const handleProjectChange = (value) => {
    setSelectedProjectId(value);
    setSelectedModuleId(null);
  };

  const handleSearch = () => fetchDocuments();

  // ── CRUD ──

  const openCreate = () => {
    if (!selectedProjectId) {
      message.warning("请先选择项目");
      return;
    }
    setModalMode("create");
    setCurrentDoc(null);
    form.resetFields();
    form.setFieldsValue({
      project_id: selectedProjectId,
      module_id: selectedModuleId || undefined,
      status: "active",
    });
    setModalOpen(true);
  };

  const openEdit = (record) => {
    setModalMode("edit");
    setCurrentDoc(record);
    form.setFieldsValue({
      project_id: record.project_id,
      module_id: record.module_id,
      name: record.name,
      content: record.content || "",
      supplementary_prompt: record.supplementary_prompt || "",
      status: record.status,
    });
    setModalOpen(true);
  };

  const handleCancel = () => {
    setModalOpen(false);
    setCurrentDoc(null);
    form.resetFields();
  };

  const handleSubmit = async (values) => {
    setSubmitting(true);
    try {
      if (modalMode === "create") {
        await createApiDocument(values);
        message.success("接口文档创建成功");
      } else {
        await updateApiDocument(currentDoc.id, values);
        message.success("接口文档更新成功");
      }
      handleCancel();
      fetchDocuments();
    } catch (e) {
      message.error(getErrorMessage(e));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await deleteApiDocument(id);
      message.success("接口文档删除成功");
      fetchDocuments();
    } catch (e) {
      message.error(getErrorMessage(e));
    }
  };

  const openDetail = (record) => {
    setDetailDoc(record);
    setDetailOpen(true);
  };

  // ── Generate cases ──

  const handleGenerateCases = async (record) => {
    setGenerating(record.id);
    try {
      const res = await generateApiCasesFromDocument({
        document_id: record.id,
      });
      const data = res.data;
      if (data.errors && data.errors.length > 0 && data.cases.length === 0) {
        message.error(data.errors.join("; "));
        return;
      }
      const casesWithKey = (data.cases || []).map((c, idx) => ({
        ...c,
        _temp_key: idx,
      }));
      setGenPreview({ ...data, cases: casesWithKey });
      setSelectedCaseKeys([]);
      setGenPreviewOpen(true);
      if (data.errors && data.errors.length > 0) {
        message.warning("部分用例解析有警告: " + data.errors.join("; "));
      } else {
        message.success(`生成 ${data.cases.length} 条用例`);
      }
    } catch (e) {
      message.error(getErrorMessage(e));
    } finally {
      setGenerating(null);
    }
  };

  const handleSaveCases = async () => {
    if (selectedCaseKeys.length === 0) {
      message.warning("请至少勾选一条用例");
      return;
    }
    setSaving(true);
    try {
      const selected = selectedCaseKeys
        .map((key) => genPreview.cases.find((c) => c._temp_key === key))
        .filter(Boolean)
        .map(({ _temp_key, ...rest }) => rest);

      await saveGeneratedApiCases({
        document_id: genPreview.document_id,
        project_id: genPreview.project_id || selectedProjectId,
        module_id: genPreview.module_id || selectedModuleId || undefined,
        cases: selected,
      });
      message.success(`已保存 ${selected.length} 条接口用例`);
      setGenPreviewOpen(false);
      setGenPreview(null);
      setSelectedCaseKeys([]);
    } catch (e) {
      message.error(getErrorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  // ── Table columns ──

  const columns = [
    { title: "ID", dataIndex: "id", width: 60 },
    { title: "名称", dataIndex: "name", width: 160, ellipsis: true },
    {
      title: "方法",
      dataIndex: "method",
      width: 80,
      render: (v) => {
        const colorMap = { GET: "green", POST: "blue", PUT: "orange", DELETE: "red", PATCH: "purple" };
        return <Tag color={colorMap[v] || "default"}>{v}</Tag>;
      },
    },
    { title: "URL", dataIndex: "url", width: 200, ellipsis: true },
    {
      title: "模块ID",
      dataIndex: "module_id",
      width: 75,
      render: (v) => (v != null ? v : "-"),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 80,
      render: (v) => (
        <Tag color={v === "active" ? "green" : v === "draft" ? "default" : "red"}>
          {v}
        </Tag>
      ),
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 160,
      render: (v) => (v ? new Date(v).toLocaleString() : "-"),
    },
    {
      title: "操作",
      width: 280,
      render: (_, record) => (
        <Space size="small" wrap>
          <Button size="small" onClick={() => openDetail(record)}>
            详情
          </Button>
          <Button size="small" onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除此接口文档？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button size="small" danger>删除</Button>
          </Popconfirm>
          <Button
            size="small"
            type="primary"
            loading={generating === record.id}
            onClick={() => handleGenerateCases(record)}
          >
            生成用例
          </Button>
        </Space>
      ),
    },
  ];

  const genPreviewColumns = [
    {
      title: "用例名称",
      dataIndex: "name",
      width: 160,
      ellipsis: true,
    },
    {
      title: "方法",
      dataIndex: "method",
      width: 70,
      render: (v) => <Tag>{v}</Tag>,
    },
    {
      title: "URL",
      dataIndex: "url",
      width: 180,
      ellipsis: true,
    },
    {
      title: "类型",
      dataIndex: "case_type",
      width: 100,
      ellipsis: true,
    },
    {
      title: "优先级",
      dataIndex: "priority",
      width: 70,
      render: (v) => {
        const m = PRIORITY_TAG_MAP[v] || { color: "default", label: v };
        return <Tag color={m.color}>{m.label}</Tag>;
      },
    },
    {
      title: "描述",
      dataIndex: "description",
      width: 150,
      ellipsis: true,
      render: (v) => v || "-",
    },
    {
      title: "请求体",
      dataIndex: "body",
      width: 150,
      ellipsis: true,
      render: (v) => (v ? JSON.stringify(v) : "-"),
    },
    {
      title: "预期结果",
      dataIndex: "expected_result",
      width: 150,
      ellipsis: true,
      render: (v) => (v ? JSON.stringify(v) : "-"),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      {/* Top bar */}
      <Card>
        <Row justify="space-between" align="middle" gutter={[16, 12]}>
          <Col>
            <Space wrap>
              <span>项目：</span>
              <Select
                placeholder="请选择项目"
                value={selectedProjectId}
                onChange={handleProjectChange}
                options={projects.map((p) => ({ label: p.name, value: p.id }))}
                style={{ width: 180 }}
                loading={projects.length === 0}
              />
              <Input
                placeholder="关键词搜索"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onPressEnter={handleSearch}
                style={{ width: 160 }}
                allowClear
              />
              <Select
                placeholder="请求方法"
                value={methodFilter}
                onChange={setMethodFilter}
                options={METHOD_OPTIONS}
                style={{ width: 110 }}
                allowClear
              />
              <Select
                placeholder="状态"
                value={statusFilter}
                onChange={setStatusFilter}
                options={STATUS_OPTIONS}
                style={{ width: 110 }}
                allowClear
              />
              <Button onClick={handleSearch}>搜索</Button>
            </Space>
          </Col>
          <Col>
            <Button type="primary" onClick={openCreate}>
              新增接口文档
            </Button>
          </Col>
        </Row>
      </Card>

      {/* Main area */}
      <div style={{ display: "flex", gap: 16 }}>
        <div style={{ width: 260, flexShrink: 0 }}>
          <ModuleTree
            projectId={selectedProjectId}
            selectedModuleId={selectedModuleId}
            onSelect={setSelectedModuleId}
            onChange={fetchDocuments}
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
          <Card title="接口文档列表">
            <Table
              rowKey="id"
              columns={columns}
              dataSource={documents}
              loading={loading}
              pagination={false}
              scroll={{ x: 1100 }}
              size="small"
            />
          </Card>
        </div>
      </div>

      {/* CRUD Modal */}
      <Modal
        title={modalMode === "create" ? "新增接口文档" : "编辑接口文档"}
        open={modalOpen}
        onCancel={handleCancel}
        onOk={() => form.submit()}
        confirmLoading={submitting}
        destroyOnClose
        width={720}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="project_id"
                label="归属项目"
                rules={[{ required: true, message: "请选择项目" }]}
              >
                <Select
                  options={projects.map((p) => ({ label: p.name, value: p.id }))}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="module_id" label="归属模块">
                <InputNumber placeholder="模块ID（可选）" style={{ width: "100%" }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name="name"
            label="文档名称"
            rules={[{ required: true, message: "请输入文档名称" }]}
          >
            <Input placeholder="如 用户模块接口文档" />
          </Form.Item>
          <Form.Item
            name="content"
            label="接口文档内容"
            rules={[{ required: true, message: "请输入接口文档内容" }]}
          >
            <Input.TextArea
              rows={12}
              placeholder={`在此粘贴接口文档内容，可以包含多个接口，例如：

## 用户登录
POST /api/user/login
请求体：{"username":"admin","password":"123456"}
响应：{"code":200,"message":"登录成功","data":{"token":"xxx"}}
错误：401 用户名或密码错误

## 获取用户信息
GET /api/user/info
请求头：Authorization: Bearer <token>
响应：{"code":200,"data":{"id":1,"username":"admin"}}
错误：401 未登录`}
            />
          </Form.Item>
          <Form.Item
            name="supplementary_prompt"
            label="补充提示词（优先级最高）"
            tooltip="此提示词会覆盖默认要求，必须严格遵守"
          >
            <Input.TextArea
              rows={3}
              placeholder="例如：请重点关注分页参数的边界测试、多用户并发场景、SQL注入测试等…"
            />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={FORM_STATUS_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Detail Modal */}
      <Modal
        title="接口文档详情"
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={700}
      >
        {detailDoc && (
          <Space direction="vertical" style={{ width: "100%" }} size={12}>
            <p><b>ID：</b>{detailDoc.id}</p>
            <p><b>名称：</b>{detailDoc.name}</p>
            <p><b>项目ID：</b>{detailDoc.project_id}</p>
            <p><b>模块ID：</b>{detailDoc.module_id ?? "-"}</p>
            <p><b>状态：</b><Tag>{detailDoc.status}</Tag></p>
            {detailDoc.supplementary_prompt && (
              <>
                <p><b>补充提示词：</b></p>
                <pre style={{ whiteSpace: "pre-wrap", background: "#fff7e6", padding: 12, borderRadius: 4, borderLeft: "3px solid #fa8c16" }}>
                  {detailDoc.supplementary_prompt}
                </pre>
              </>
            )}
            <p><b>接口文档内容：</b></p>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                background: "#f5f5f5",
                padding: 12,
                borderRadius: 4,
                maxHeight: 400,
                overflow: "auto",
              }}
            >
              {detailDoc.content || "无"}
            </pre>
          </Space>
        )}
      </Modal>

      {/* Generate Preview Modal */}
      <Modal
        title="生成接口测试用例预览"
        open={genPreviewOpen}
        onCancel={() => {
          setGenPreviewOpen(false);
          setGenPreview(null);
          setSelectedCaseKeys([]);
        }}
        footer={
          <Space>
            <Button
              onClick={() => {
                setGenPreviewOpen(false);
                setGenPreview(null);
                setSelectedCaseKeys([]);
              }}
            >
              取消
            </Button>
            <Button
              type="primary"
              loading={saving}
              disabled={selectedCaseKeys.length === 0}
              onClick={handleSaveCases}
            >
              保存选中 ({selectedCaseKeys.length})
            </Button>
          </Space>
        }
        width={1000}
      >
        {genPreview ? (
          <>
            {genPreview.cases.length === 0 && (
              <p style={{ color: "#999" }}>
                未生成任何用例
                {genPreview.errors?.length > 0 && (
                  <>：{genPreview.errors.join("; ")}</>
                )}
              </p>
            )}
            {genPreview.cases.length > 0 && (
              <Table
                rowKey="_temp_key"
                columns={genPreviewColumns}
                dataSource={genPreview.cases}
                pagination={false}
                scroll={{ x: 1100 }}
                size="small"
                rowSelection={{
                  selectedRowKeys: selectedCaseKeys,
                  onChange: setSelectedCaseKeys,
                }}
              />
            )}
            {genPreview.raw_output && (
              <details style={{ marginTop: 12 }}>
                <summary>查看 LLM 原始返回</summary>
                <pre style={{ whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto", background: "#f5f5f5", padding: 12 }}>
                  {genPreview.raw_output}
                </pre>
              </details>
            )}
          </>
        ) : (
          <p>无预览数据</p>
        )}
      </Modal>
    </Space>
  );
}

export default ApiDocPage;
