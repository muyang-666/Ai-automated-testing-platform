import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Collapse,
  Drawer,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import {
  createSceneStep,
  deleteSceneStep,
  getCaseList,
  getSceneSteps,
  reorderSceneSteps,
  runSceneChain,
  updateSceneStep,
} from "../api/scene";
import { canOperateProject } from "../utils/authPermissions";

const { Title } = Typography;

function getErrorMessage(error) {
  return (
    error?.response?.data?.detail ||
    error?.response?.data?.message ||
    error?.message ||
    "操作失败"
  );
}

function parseJsonField(value, fieldName, expectedType) {
  if (!value || !value.trim()) return null;
  try {
    const parsed = JSON.parse(value);
    if (expectedType === "object" && (typeof parsed !== "object" || Array.isArray(parsed))) {
      message.error(`${fieldName} 必须是 JSON 对象`);
      throw new Error();
    }
    if (expectedType === "array" && !Array.isArray(parsed)) {
      message.error(`${fieldName} 必须是 JSON 数组`);
      throw new Error();
    }
    return parsed;
  } catch (e) {
    if (e instanceof SyntaxError || e.message?.includes("JSON")) {
      message.error(`${fieldName} 不是合法 JSON`);
    }
    throw e;
  }
}

function formatJson(v) {
  if (v == null) return "";
  return JSON.stringify(v, null, 2);
}

const JSON_PLACEHOLDERS = {
  extract_rules: '{\n  "token": "$.data.token",\n  "user_id": "$.data.user_id"\n}',
  request_override:
    '{\n  "headers": {\n    "Authorization": "Bearer ${token}"\n  }\n}',
  assertions:
    '[\n  {\n    "type": "status_code",\n    "operator": "eq",\n    "expected": 200\n  }\n]',
};

export default function SceneStepPage({ scene, onBack }) {
  const canOperateScene = canOperateProject(scene?.project_id);
  const [steps, setSteps] = useState([]);
  const [caseOptions, setCaseOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedStepIds, setSelectedStepIds] = useState([]);
  const [chainRunning, setChainRunning] = useState(false);
  const [chainResultOpen, setChainResultOpen] = useState(false);
  const [chainResult, setChainResult] = useState(null);

  // Add form state
  const [selectedCaseId, setSelectedCaseId] = useState(undefined);
  const [stepOrder, setStepOrder] = useState(1);
  const [stepName, setStepName] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [extractRules, setExtractRules] = useState("");
  const [requestOverride, setRequestOverride] = useState("");
  const [assertions, setAssertions] = useState("");
  const [adding, setAdding] = useState(false);

  // Edit modal state
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingStep, setEditingStep] = useState(null);
  const [editForm] = Form.useForm();

  const loadSteps = async () => {
    setLoading(true);
    try {
      const res = await getSceneSteps(scene.id);
      setSteps(res.data || []);
      setSelectedStepIds((prev) =>
        prev.filter((id) => (res.data || []).some((step) => step.id === id))
      );
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const loadCases = async () => {
    try {
      const params = {};
      if (scene.project_id) params.project_id = scene.project_id;
      if (scene.module_id) params.module_id = scene.module_id;
      const res = await getCaseList(params);
      setCaseOptions(res.data || []);
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  useEffect(() => {
    if (scene?.id) {
      loadSteps();
      loadCases();
    }
  }, [scene?.id]);

  const resetAddForm = () => {
    setSelectedCaseId(undefined);
    setStepOrder(1);
    setStepName("");
    setEnabled(true);
    setExtractRules("");
    setRequestOverride("");
    setAssertions("");
  };

  const handleAddStep = async () => {
    if (!selectedCaseId) {
      message.warning("请先选择测试用例");
      return;
    }
    if (!stepOrder || stepOrder < 1) {
      message.warning("步骤顺序必须大于 0");
      return;
    }

    try {
      const data = {
        step_order: stepOrder,
        case_id: selectedCaseId,
        step_name: stepName || null,
        enabled,
        extract_rules_json: parseJsonField(extractRules, "变量提取规则", "object"),
        request_override_json: parseJsonField(requestOverride, "请求覆盖配置", "object"),
        assertions_json: parseJsonField(assertions, "断言规则", "array"),
      };

      setAdding(true);
      await createSceneStep(scene.id, data);
      message.success("新增场景步骤成功");
      resetAddForm();
      loadSteps();
    } catch (error) {
      if (error?.response) {
        message.error(getErrorMessage(error));
      }
    } finally {
      setAdding(false);
    }
  };

  const handleDeleteStep = async (stepId) => {
    try {
      await deleteSceneStep(stepId);
      message.success("删除步骤成功");
      loadSteps();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const openEditModal = (record) => {
    setEditingStep(record);
    editForm.setFieldsValue({
      step_order: record.step_order,
      case_id: record.case_id,
      step_name: record.step_name || "",
      enabled: record.enabled,
      extract_rules_json: formatJson(record.extract_rules_json),
      request_override_json: formatJson(record.request_override_json),
      assertions_json: formatJson(record.assertions_json),
    });
    setEditModalOpen(true);
  };

  const handleSaveEdit = async () => {
    try {
      const values = await editForm.validateFields();
      const data = {
        step_order: values.step_order,
        case_id: values.case_id,
        step_name: values.step_name || null,
        enabled: values.enabled,
        extract_rules_json: parseJsonField(
          values.extract_rules_json,
          "变量提取规则",
          "object"
        ),
        request_override_json: parseJsonField(
          values.request_override_json,
          "请求覆盖配置",
          "object"
        ),
        assertions_json: parseJsonField(values.assertions_json, "断言规则", "array"),
      };

      await updateSceneStep(editingStep.id, data);
      message.success("步骤更新成功");
      setEditModalOpen(false);
      setEditingStep(null);
      loadSteps();
    } catch (error) {
      if (error?.response) {
        message.error(getErrorMessage(error));
      }
    }
  };

  const handleMove = async (stepId, direction) => {
    const idx = steps.findIndex((s) => s.id === stepId);
    if (idx === -1) return;
    const newIdx = idx + (direction === "up" ? -1 : 1);
    if (newIdx < 0 || newIdx >= steps.length) return;

    const reordered = [...steps];
    [reordered[idx], reordered[newIdx]] = [reordered[newIdx], reordered[idx]];

    try {
      await reorderSceneSteps(scene.id, {
        ordered_step_ids: reordered.map((s) => s.id),
      });
      message.success("排序调整成功");
      loadSteps();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const handleRunSelectedChain = async () => {
    if (selectedStepIds.length === 0) {
      message.warning("请先选择要串联执行的用例");
      return;
    }
    setChainRunning(true);
    try {
      const res = await runSceneChain(scene.id, {
        selected_step_ids: selectedStepIds,
      });
      setChainResult(res.data);
      setChainResultOpen(true);
      message.success("串联执行完成");
    } catch (error) {
      message.error(
        error?.response?.data?.detail ||
          error?.response?.data?.message ||
          error?.message ||
          "串联执行失败"
      );
    } finally {
      setChainRunning(false);
    }
  };

  const chainColumns = [
    { title: "步骤", dataIndex: "step_order", width: 70 },
    { title: "名称", dataIndex: "step_name", ellipsis: true },
    { title: "用例ID", dataIndex: "case_id", width: 90 },
    {
      title: "状态",
      dataIndex: "status",
      width: 90,
      render: (v) => {
        const map = { passed: "success", failed: "error", error: "error", skipped: "warning" };
        return <Tag color={map[v] || "default"}>{v}</Tag>;
      },
    },
    {
      title: "响应码",
      dataIndex: "response_status_code",
      width: 90,
      render: (v) => v ?? "-",
    },
    {
      title: "提取变量",
      dataIndex: "extracted_variables",
      width: 170,
      ellipsis: true,
      render: (v) => (v && Object.keys(v).length > 0 ? JSON.stringify(v) : "-"),
    },
    {
      title: "耗时",
      dataIndex: "duration_ms",
      width: 90,
      render: (v) => (v != null ? `${v}ms` : "-"),
    },
    {
      title: "错误",
      dataIndex: "error_message",
      width: 170,
      ellipsis: true,
      render: (v) => (v ? <span style={{ color: "#b00020" }}>{v}</span> : "-"),
    },
  ];

  const columns = [
    { title: "步骤", dataIndex: "step_order", width: 60 },
    { title: "名称", dataIndex: "step_name", width: 120, ellipsis: true, render: (v) => v || "-" },
    { title: "用例ID", dataIndex: "case_id", width: 70 },
    { title: "用例名称", dataIndex: "case_name", ellipsis: true },
    {
      title: "URL",
      dataIndex: "case_url",
      width: 180,
      ellipsis: true,
    },
    {
      title: "启用",
      dataIndex: "enabled",
      width: 60,
      render: (v) => (v ? <Tag color="green">是</Tag> : <Tag color="default">否</Tag>),
    },
    {
      title: "提取",
      dataIndex: "extract_rules_json",
      width: 65,
      render: (v) =>
        v && Object.keys(v).length > 0 ? (
          <Tag color="blue">已配置</Tag>
        ) : (
          <Tag color="default">未配置</Tag>
        ),
    },
    {
      title: "覆盖",
      dataIndex: "request_override_json",
      width: 65,
      render: (v) =>
        v && Object.keys(v).length > 0 ? (
          <Tag color="blue">已配置</Tag>
        ) : (
          <Tag color="default">未配置</Tag>
        ),
    },
    {
      title: "断言",
      dataIndex: "assertions_json",
      width: 65,
      render: (v) =>
        v && v.length > 0 ? (
          <Tag color="blue">已配置</Tag>
        ) : (
          <Tag color="default">未配置</Tag>
        ),
    },
    {
      title: "操作",
      width: 290,
      render: (_, record, index) =>
        canOperateScene ? (
          <Space size="small">
            <Button size="small" onClick={() => openEditModal(record)}>
              编辑
            </Button>
            <Popconfirm
              title="确定删除这个步骤吗？"
              onConfirm={() => handleDeleteStep(record.id)}
            >
              <Button danger size="small">
                删除
              </Button>
            </Popconfirm>
            <Button
              size="small"
              disabled={index === 0}
              onClick={() => handleMove(record.id, "up")}
            >
              上移
            </Button>
            <Button
              size="small"
              disabled={index === steps.length - 1}
              onClick={() => handleMove(record.id, "down")}
            >
              下移
            </Button>
          </Space>
        ) : (
          <Tag>只读</Tag>
        ),
    },
  ];

  return (
    <Card className="scene-page scene-step-page">
      <Space direction="vertical" style={{ width: "100%" }} size={16}>
        <Space style={{ justifyContent: "space-between", width: "100%" }}>
          <Title level={4} style={{ margin: 0 }}>
            管理场景用例：{scene.name}
          </Title>
          <Space>
            {canOperateScene && (
              <Button
                type="primary"
                className="standard-primary-btn"
                loading={chainRunning}
                onClick={handleRunSelectedChain}
              >
                串联执行选中用例
              </Button>
            )}
            <Button onClick={onBack}>返回场景列表</Button>
          </Space>
        </Space>

        {/* 新增步骤区域 */}
        {canOperateScene && (
        <Card size="small" title="新增步骤">
          <Space wrap style={{ marginBottom: 8 }}>
            <InputNumber
              min={1}
              value={stepOrder}
              onChange={setStepOrder}
              placeholder="步骤顺序"
              style={{ width: 100 }}
            />
            <Select
              style={{ width: 320 }}
              placeholder="请选择已有测试用例"
              value={selectedCaseId}
              onChange={setSelectedCaseId}
              options={caseOptions.map((item) => ({
                label: `${item.id} - ${item.name}`,
                value: item.id,
              }))}
              showSearch
              optionFilterProp="label"
            />
            <Input
              placeholder="步骤名称（可选）"
              value={stepName}
              onChange={(e) => setStepName(e.target.value)}
              style={{ width: 180 }}
            />
            <Space>
              <span>启用：</span>
              <Switch className="scene-enable-switch" checked={enabled} onChange={setEnabled} />
            </Space>
            <Button
              type="primary"
              className="scene-add-step-btn"
              loading={adding}
              onClick={handleAddStep}
            >
              添加到场景
            </Button>
          </Space>

          <Collapse
            ghost
            size="small"
            items={[
              {
                key: "json-config",
                label: "JSON 配置（变量提取 / 请求覆盖 / 断言规则）",
                children: (
                  <Space direction="vertical" style={{ width: "100%" }}>
                    <div>
                      <div style={{ marginBottom: 4 }}>变量提取规则（extract_rules_json）：</div>
                      <Input.TextArea
                        rows={3}
                        value={extractRules}
                        onChange={(e) => setExtractRules(e.target.value)}
                        placeholder={JSON_PLACEHOLDERS.extract_rules}
                      />
                    </div>
                    <div>
                      <div style={{ marginBottom: 4 }}>请求覆盖配置（request_override_json）：</div>
                      <Input.TextArea
                        rows={3}
                        value={requestOverride}
                        onChange={(e) => setRequestOverride(e.target.value)}
                        placeholder={JSON_PLACEHOLDERS.request_override}
                      />
                    </div>
                    <div>
                      <div style={{ marginBottom: 4 }}>断言规则（assertions_json）：</div>
                      <Input.TextArea
                        rows={4}
                        value={assertions}
                        onChange={(e) => setAssertions(e.target.value)}
                        placeholder={JSON_PLACEHOLDERS.assertions}
                      />
                    </div>
                  </Space>
                ),
              },
            ]}
          />
        </Card>
        )}

        {/* 步骤列表 */}
        <Table
          rowKey="id"
          loading={loading}
          dataSource={steps}
          columns={columns}
          rowSelection={{
            selectedRowKeys: selectedStepIds,
            onChange: setSelectedStepIds,
          }}
          pagination={false}
          scroll={{ x: 1200 }}
          size="small"
        />
      </Space>

      {/* 编辑步骤 Modal */}
      <Modal
        title="编辑步骤"
        open={editModalOpen}
        onOk={handleSaveEdit}
        onCancel={() => {
          setEditModalOpen(false);
          setEditingStep(null);
        }}
        destroyOnClose
        width={640}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="step_order"
            label="步骤顺序"
            rules={[{ required: true, message: "请输入步骤顺序" }]}
          >
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>

          <Form.Item
            name="case_id"
            label="关联用例"
            rules={[{ required: true, message: "请选择用例" }]}
          >
            <Select
              placeholder="请选择测试用例"
              options={caseOptions.map((item) => ({
                label: `${item.id} - ${item.name}`,
                value: item.id,
              }))}
              showSearch
              optionFilterProp="label"
            />
          </Form.Item>

          <Form.Item name="step_name" label="步骤名称">
            <Input placeholder="步骤名称（可选）" />
          </Form.Item>

          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch className="scene-enable-switch" />
          </Form.Item>

          <Form.Item name="extract_rules_json" label="变量提取规则（extract_rules_json）">
            <Input.TextArea
              rows={3}
              placeholder={JSON_PLACEHOLDERS.extract_rules}
            />
          </Form.Item>

          <Form.Item name="request_override_json" label="请求覆盖配置（request_override_json）">
            <Input.TextArea
              rows={3}
              placeholder={JSON_PLACEHOLDERS.request_override}
            />
          </Form.Item>

          <Form.Item name="assertions_json" label="断言规则（assertions_json）">
            <Input.TextArea
              rows={4}
              placeholder={JSON_PLACEHOLDERS.assertions}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={chainResult ? `串联执行结果：${chainResult.scene_name}` : "串联执行结果"}
        placement="right"
        width="50vw"
        rootClassName="standard-drawer scene-result-drawer"
        open={chainResultOpen}
        onClose={() => {
          setChainResultOpen(false);
          setChainResult(null);
        }}
        footer={null}
        destroyOnClose
      >
        {chainResult && (
          <Space direction="vertical" style={{ width: "100%" }} size={16}>
            <Space wrap>
              <Tag color={chainResult.status === "passed" ? "success" : "error"}>
                {chainResult.status}
              </Tag>
              <span>Run ID：{chainResult.scene_run_id}</span>
              <span>总步骤：{chainResult.total_steps}</span>
              <span>通过：{chainResult.passed_steps}</span>
              <span>失败：{chainResult.failed_steps}</span>
              <span>跳过：{chainResult.skipped_steps}</span>
            </Space>

            {chainResult.context && Object.keys(chainResult.context).length > 0 && (
              <div>
                <strong>运行时上下文：</strong>
                <pre className="scene-result-pre">
                  {JSON.stringify(chainResult.context, null, 2)}
                </pre>
              </div>
            )}

            <Table
              rowKey="step_order"
              dataSource={chainResult.steps || []}
              columns={chainColumns}
              pagination={false}
              size="small"
              scroll={{ x: 900 }}
            />
          </Space>
        )}
      </Drawer>
    </Card>
  );
}
