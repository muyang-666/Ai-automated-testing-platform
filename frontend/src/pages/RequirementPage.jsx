import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Checkbox,
  Col,
  Drawer,
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
  createRequirement,
  deleteRequirement,
  getRequirementList,
  updateRequirement,
} from "../api/requirement";
import {
  generateFunctionCasesFromRequirement,
  saveGeneratedFunctionCases,
} from "../api/functionCase";
import ModuleTree from "../components/ModuleTree";

function getErrorMessage(error) {
  return (
    error?.response?.data?.detail ||
    error?.response?.data?.message ||
    error?.message ||
    "操作失败"
  );
}

const STATUS_OPTIONS = [
  { label: "全部", value: "" },
  { label: "draft", value: "draft" },
  { label: "confirmed", value: "confirmed" },
  { label: "disabled", value: "disabled" },
];

const STATUS_TAG_MAP = {
  draft: { color: "default", label: "draft" },
  confirmed: { color: "success", label: "confirmed" },
  disabled: { color: "error", label: "disabled" },
};

const TYPE_OPTIONS = [
  { label: "全部", value: "" },
  { label: "login", value: "login" },
  { label: "user", value: "user" },
  { label: "product", value: "product" },
  { label: "order", value: "order" },
  { label: "payment", value: "payment" },
  { label: "other", value: "other" },
];

const FORM_STATUS_OPTIONS = [
  { label: "draft", value: "draft" },
  { label: "confirmed", value: "confirmed" },
  { label: "disabled", value: "disabled" },
];

const FORM_TYPE_OPTIONS = [
  { label: "login", value: "login" },
  { label: "user", value: "user" },
  { label: "product", value: "product" },
  { label: "order", value: "order" },
  { label: "payment", value: "payment" },
  { label: "other", value: "other" },
];

export default function RequirementPage() {
  const [requirements, setRequirements] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState("create");
  const [editingRequirement, setEditingRequirement] = useState(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [detailRequirement, setDetailRequirement] = useState(null);
  const [form] = Form.useForm();

  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [selectedModuleId, setSelectedModuleId] = useState(null);
  const [unboundModuleOnly, setUnboundModuleOnly] = useState(false);
  const [includeChildren, setIncludeChildren] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  const [generatingId, setGeneratingId] = useState(null);
  const [generateModalOpen, setGenerateModalOpen] = useState(false);
  const [generatedCases, setGeneratedCases] = useState([]);
  const [selectedCaseKeys, setSelectedCaseKeys] = useState([]);
  const [generatedMeta, setGeneratedMeta] = useState(null);
  const [generateErrors, setGenerateErrors] = useState([]);


  const fetchProjects = async () => {
    try {
      const res = await getProjectList();
      setProjects(res.data || []);
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
      fetchRequirements();
    }
  }, [
    selectedProjectId,
    selectedModuleId,
    unboundModuleOnly,
    includeChildren,
    keyword,
    statusFilter,
    typeFilter,
  ]);

  const fetchRequirements = async () => {
    if (!selectedProjectId) return;
    setLoading(true);
    try {
      const params = { project_id: selectedProjectId };
      if (unboundModuleOnly) {
        params.unbound_module = true;
      } else if (selectedModuleId != null) {
        params.module_id = selectedModuleId;
        if (includeChildren) {
          params.include_children = true;
        }
      }
      if (keyword) params.keyword = keyword;
      if (statusFilter) params.status = statusFilter;
      if (typeFilter) params.requirement_type = typeFilter;
      const res = await getRequirementList(params);
      setRequirements(res.data || []);
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const handleProjectChange = (value) => {
    setSelectedProjectId(value);
    setSelectedModuleId(null);
    setUnboundModuleOnly(false);
  };

  const handleModuleSelect = (moduleId) => {
    setSelectedModuleId(moduleId);
    setUnboundModuleOnly(false);
  };

  const handleUnboundModuleClick = () => {
    setSelectedModuleId(null);
    setIncludeChildren(false);
    setUnboundModuleOnly(true);
  };

  const handleModuleChange = () => {
    fetchRequirements();
  };

  const openCreateModal = () => {
    if (!selectedProjectId) {
      message.warning("请先选择项目");
      return;
    }
    setModalMode("create");
    setEditingRequirement(null);
    form.resetFields();
    form.setFieldsValue({
      project_id: selectedProjectId,
      module_id: selectedModuleId || undefined,
      status: "confirmed",
    });
    setModalOpen(true);
  };

  const openEditModal = (record) => {
    setModalMode("edit");
    setEditingRequirement(record);
    form.setFieldsValue({
      project_id: record.project_id,
      module_id: record.module_id,
      title: record.title,
      content: record.content,
      requirement_type: record.requirement_type,
      status: record.status,
      remark: record.remark,
      supplementary_prompt: record.supplementary_prompt || "",
    });
    setModalOpen(true);
  };

  const openDetailModal = (record) => {
    setDetailRequirement(record);
    setDetailModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingRequirement(null);
    form.resetFields();
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      if (modalMode === "create") {
        await createRequirement(values);
        message.success("需求文本创建成功");
      } else {
        await updateRequirement(editingRequirement.id, values);
        message.success("需求文本更新成功");
      }

      closeModal();
      fetchRequirements();
    } catch (error) {
      if (error?.response) {
        message.error(getErrorMessage(error));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (requirementId) => {
    try {
      await deleteRequirement(requirementId);
      message.success("需求文本删除成功");
      fetchRequirements();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const handleGenerate = async (record) => {
    setGeneratingId(record.id);
    setGenerateErrors([]);
    try {
      const res = await generateFunctionCasesFromRequirement({
        requirement_id: record.id,
      });
      const data = res.data;
      const casesWithKey = (data.cases || []).map((c, i) => ({
        ...c,
        _temp_key: `gen-${i}-${Date.now()}`,
      }));
      setGeneratedCases(casesWithKey);
      setSelectedCaseKeys([]);
      setGeneratedMeta({
        requirement_id: data.requirement_id,
        project_id: data.project_id,
        module_id: data.module_id,
        model_name: data.model_name,
        provider_name: data.provider_name,
      });
      setGenerateErrors(data.errors || []);
      setGenerateModalOpen(true);
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setGeneratingId(null);
    }
  };

  const handleSaveSelected = async () => {
    if (selectedCaseKeys.length === 0) {
      message.warning("请选择要保存的用例");
      return;
    }
    const selectedCases = generatedCases
      .filter((c) => selectedCaseKeys.includes(c._temp_key))
      .map((item) => {
        const next = { ...item };
        delete next._temp_key;
        return next;
      });
    try {
      const res = await saveGeneratedFunctionCases({
        requirement_id: generatedMeta.requirement_id,
        project_id: generatedMeta.project_id,
        module_id: generatedMeta.module_id,
        cases: selectedCases,
      });
      message.success(`已保存 ${res.data.saved_count} 条功能测试用例`);
      setGenerateModalOpen(false);
      setGeneratedCases([]);
      setGeneratedMeta(null);
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const handleSearch = (value) => {
    setKeyword(value);
  };

  const handleStatusChange = (value) => {
    setStatusFilter(value);
  };

  const handleTypeChange = (value) => {
    setTypeFilter(value);
  };

  const columns = [
    { title: "ID", dataIndex: "id", width: 60 },
    { title: "标题", dataIndex: "title", width: 200, ellipsis: true },
    {
      title: "模块ID",
      dataIndex: "module_id",
      width: 80,
      render: (value) => (value != null ? value : "-"),
    },
    {
      title: "类型",
      dataIndex: "requirement_type",
      width: 90,
      render: (value) => value || "-",
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value) => {
        const tag = STATUS_TAG_MAP[value] || { color: "default", label: value };
        return <Tag className="requirement-status-tag">{tag.label}</Tag>;
      },
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 160,
      render: (value) => (value ? new Date(value).toLocaleString("zh-CN") : "-"),
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      width: 160,
      render: (value) => (value ? new Date(value).toLocaleString("zh-CN") : "-"),
    },
    {
      title: "操作",
      width: 340,
      render: (_, record) => (
        <Space size="small">
          <Button size="small" className="requirement-action-btn" onClick={() => openDetailModal(record)}>
            查看详情
          </Button>
          <Button
            size="small"
            className="requirement-action-btn"
            loading={generatingId === record.id}
            onClick={() => handleGenerate(record)}
          >
            生成用例
          </Button>
          <Button size="small" className="requirement-action-btn" onClick={() => openEditModal(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该需求文本吗？"
            description="删除后不可恢复，请确认。"
            okText="确认"
            cancelText="取消"
            overlayClassName="requirement-popconfirm"
            okButtonProps={{ className: "requirement-popconfirm-ok" }}
            cancelButtonProps={{ className: "requirement-popconfirm-cancel" }}
            onConfirm={() => handleDelete(record.id)}
          >
            <Button size="small" className="requirement-delete-btn">
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="requirement-page">
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card className="requirement-toolbar-card">
        <Row justify="space-between" align="middle" gutter={[16, 8]}>
          <Col>
            <Space wrap>
              <span className="requirement-project-label">项目：</span>
              <Select
                placeholder="请选择项目"
                value={selectedProjectId}
                onChange={handleProjectChange}
                options={projects.map((p) => ({ label: p.name, value: p.id }))}
                style={{ width: 200 }}
                popupClassName="requirement-select-dropdown"
              />
              <Input.Search
                placeholder="搜索标题或内容"
                allowClear
                onSearch={handleSearch}
                style={{ width: 200 }}
              />
              <Select
                placeholder="状态筛选"
                options={STATUS_OPTIONS}
                value={statusFilter}
                onChange={handleStatusChange}
                style={{ width: 130 }}
                popupClassName="requirement-select-dropdown"
              />
              <Select
                placeholder="类型筛选"
                options={TYPE_OPTIONS}
                value={typeFilter}
                onChange={handleTypeChange}
                style={{ width: 130 }}
                popupClassName="requirement-select-dropdown"
              />
            </Space>
          </Col>
          <Col>
            <Button type="primary" className="requirement-primary-btn" onClick={openCreateModal}>
              新增需求
            </Button>
          </Col>
        </Row>
      </Card>

      <div className="requirement-layout">
        <div className="requirement-module-shell">
          <ModuleTree
            projectId={selectedProjectId}
            selectedModuleId={selectedModuleId}
            onSelect={handleModuleSelect}
            onChange={handleModuleChange}
            createButtonLabel="新增模块"
            createButtonClassName="requirement-module-header-btn"
            createButtonIcon={null}
            headerExtra={
              <Button className="requirement-module-header-btn" onClick={handleUnboundModuleClick} block>
                无模块用例
              </Button>
            }
          />
          <Checkbox
            checked={includeChildren}
            onChange={(e) => setIncludeChildren(e.target.checked)}
            style={{ marginTop: 8 }}
          >
            包含子模块
          </Checkbox>
        </div>

        <div className="requirement-list-panel">
          <Card title="需求文本列表" className="requirement-list-card">
            <Table
              rowKey="id"
              columns={columns}
              dataSource={requirements}
              loading={loading}
              pagination={false}
              scroll={{ x: 1000 }}
              size="small"
            />
          </Card>
        </div>
      </div>

      <Drawer
        title={modalMode === "create" ? "新增需求文本" : "编辑需求文本"}
        placement="right"
        width="50vw"
        rootClassName="requirement-drawer"
        open={modalOpen}
        onClose={closeModal}
        destroyOnClose
        footer={
          <div className="requirement-drawer-footer">
            <Button onClick={closeModal} disabled={submitting}>
              取消
            </Button>
            <Button
              type="primary"
              className="requirement-primary-btn"
              onClick={handleSubmit}
              loading={submitting}
            >
              保存
            </Button>
          </div>
        }
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
              popupClassName="requirement-select-dropdown"
            />
          </Form.Item>

          <Form.Item name="module_id" label="归属模块">
            <InputNumber
              placeholder="模块ID（可选）"
              style={{ width: "100%" }}
            />
          </Form.Item>

          <Form.Item
            name="title"
            label="需求标题"
            rules={[{ required: true, message: "请输入需求标题" }]}
          >
            <Input placeholder="请输入需求标题" maxLength={200} />
          </Form.Item>

          <Form.Item
            name="content"
            label="需求内容"
            rules={[{ required: true, message: "请输入需求内容" }]}
          >
            <Input.TextArea rows={5} placeholder="请输入需求文本内容" />
          </Form.Item>

          <Form.Item name="requirement_type" label="需求类型">
            <Select
              placeholder="请选择需求类型"
              allowClear
              options={FORM_TYPE_OPTIONS}
              popupClassName="requirement-select-dropdown"
            />
          </Form.Item>

          <Form.Item name="status" label="状态">
            <Select options={FORM_STATUS_OPTIONS} popupClassName="requirement-select-dropdown" />
          </Form.Item>

          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} placeholder="备注（可选）" />
          </Form.Item>

          <Form.Item name="supplementary_prompt" label="补充提示词（生成用例时使用）">
            <Input.TextArea rows={3} placeholder="例如：重点覆盖登录态异常、并发场景、SQL注入测试…" />
          </Form.Item>
        </Form>
      </Drawer>

      <Modal
        title="需求详情"
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalOpen(false)}>
            关闭
          </Button>,
        ]}
        width={640}
      >
        {detailRequirement && (
          <div>
            <p><strong>标题：</strong>{detailRequirement.title}</p>
            <p><strong>类型：</strong>{detailRequirement.requirement_type || "-"}</p>
            <p><strong>状态：</strong>{detailRequirement.status}</p>
            <p><strong>模块ID：</strong>{detailRequirement.module_id ?? "-"}</p>
            <p><strong>内容：</strong></p>
            <div
              style={{
                background: "#f5f5f5",
                padding: 12,
                borderRadius: 4,
                whiteSpace: "pre-wrap",
                maxHeight: 300,
                overflow: "auto",
              }}
            >
              {detailRequirement.content}
            </div>
            {detailRequirement.remark && (
              <>
                <p style={{ marginTop: 12 }}><strong>备注：</strong></p>
                <div
                  style={{
                    background: "#f5f5f5",
                    padding: 12,
                    borderRadius: 4,
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {detailRequirement.remark}
                </div>
              </>
            )}
          </div>
        )}
      </Modal>

      <Drawer
        title="生成结果预览"
        placement="right"
        width="50vw"
        rootClassName="requirement-drawer"
        open={generateModalOpen}
        onClose={() => setGenerateModalOpen(false)}
        destroyOnClose
        footer={
          <div className="requirement-drawer-footer">
            <Button onClick={() => setGenerateModalOpen(false)}>
              关闭
            </Button>
            <Button
              className="requirement-save-cases-btn"
              disabled={selectedCaseKeys.length === 0}
              onClick={handleSaveSelected}
            >
              保存选中用例 ({selectedCaseKeys.length})
            </Button>
          </div>
        }
      >
        {generateErrors.length > 0 && (
          <div
            style={{
              background: "#fff2f0",
              border: "1px solid #ffccc7",
              borderRadius: 4,
              padding: 12,
              marginBottom: 12,
            }}
          >
            <strong>校验警告：</strong>
            {generateErrors.map((err, i) => (
              <div key={i} style={{ color: "#cf1322" }}>{err}</div>
            ))}
          </div>
        )}
        {generatedMeta?.model_name && (
          <div
            style={{
              background: "#f6ffed",
              border: "1px solid #b7eb8f",
              borderRadius: 4,
              padding: "8px 12px",
              marginBottom: 12,
            }}
          >
            本次使用模型：<Tag className="requirement-status-tag">{generatedMeta.provider_name} / {generatedMeta.model_name}</Tag>
          </div>
        )}
        <Table
          rowKey="_temp_key"
          dataSource={generatedCases}
          rowSelection={{
            selectedRowKeys: selectedCaseKeys,
            onChange: setSelectedCaseKeys,
          }}
          columns={[
            { title: "编号", dataIndex: "case_code", width: 110, ellipsis: true, render: (v) => v || "-" },
            { title: "用例名称", dataIndex: "case_name", width: 140, ellipsis: true },
            { title: "类型", dataIndex: "case_type", width: 100 },
            { title: "优先级", dataIndex: "priority", width: 70 },
            {
              title: "前置条件",
              dataIndex: "precondition",
              width: 140,
              ellipsis: true,
              render: (v) => v || "-",
            },
            {
              title: "测试步骤",
              dataIndex: "steps_json",
              width: 180,
              ellipsis: true,
              render: (v) => (v ? JSON.stringify(v) : "-"),
            },
            {
              title: "测试数据",
              dataIndex: "test_data_json",
              width: 160,
              ellipsis: true,
              render: (v) => (v ? JSON.stringify(v) : "-"),
            },
            {
              title: "预期结果",
              dataIndex: "expected_result",
              width: 160,
              ellipsis: true,
              render: (v) => v || "-",
            },
          ]}
          pagination={false}
          scroll={{ x: 1100 }}
          size="small"
        />
      </Drawer>
    </Space>
    </div>
  );
}
