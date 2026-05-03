import { useEffect, useState } from "react";
import {
  Button,
  Card,
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
  Tabs,
} from "antd";
import {
  createProvider,
  deleteProvider,
  getProviderList,
  updateProvider,
  createModel,
  deleteModel,
  getModelList,
  updateModel,
  testModel,
  getSceneConfigList,
  updateSceneConfig,
} from "../api/llmConfig";

const PROVIDER_TYPE_OPTIONS = [
  { label: "openai_compatible", value: "openai_compatible" },
  { label: "deepseek", value: "deepseek" },
  { label: "openai", value: "openai" },
  { label: "qwen", value: "qwen" },
  { label: "custom", value: "custom" },
];

const STATUS_OPTIONS = [
  { label: "active", value: "active" },
  { label: "disabled", value: "disabled" },
];

const SCENE_NAME_MAP = {
  requirement_to_function_case: "需求生成功能测试用例",
  api_doc_to_api_case: "接口文档生成接口测试用例",
  failure_analysis: "AI 失败分析",
  report_summary: "报告 AI 总结",
};

function ModelConfigPage() {
  // ── Provider state ──
  const [providers, setProviders] = useState([]);
  const [providerLoading, setProviderLoading] = useState(false);
  const [providerCreateModalOpen, setProviderCreateModalOpen] = useState(false);
  const [providerEditDrawerOpen, setProviderEditDrawerOpen] = useState(false);
  const [currentProvider, setCurrentProvider] = useState(null);
  const [providerSubmitting, setProviderSubmitting] = useState(false);
  const [providerForm] = Form.useForm();

  // ── Model state ──
  const [models, setModels] = useState([]);
  const [modelLoading, setModelLoading] = useState(false);
  const [modelCreateModalOpen, setModelCreateModalOpen] = useState(false);
  const [modelEditDrawerOpen, setModelEditDrawerOpen] = useState(false);
  const [currentModel, setCurrentModel] = useState(null);
  const [modelSubmitting, setModelSubmitting] = useState(false);
  const [modelForm] = Form.useForm();
  const [testing, setTesting] = useState(null);
  const [testResultModalOpen, setTestResultModalOpen] = useState(false);
  const [testResult, setTestResult] = useState(null);

  // ── Scene state ──
  const [sceneConfigs, setSceneConfigs] = useState([]);
  const [sceneLoading, setSceneLoading] = useState(false);
  const [sceneEditDrawerOpen, setSceneEditDrawerOpen] = useState(false);
  const [currentScene, setCurrentScene] = useState(null);
  const [sceneSubmitting, setSceneSubmitting] = useState(false);
  const [sceneForm] = Form.useForm();

  // ═══════════ Provider ═══════════

  const fetchProviders = async () => {
    setProviderLoading(true);
    try {
      const res = await getProviderList();
      setProviders(res.data || []);
    } catch {
      message.error("获取供应商列表失败");
    } finally {
      setProviderLoading(false);
    }
  };

  useEffect(() => {
    fetchProviders();
  }, []);

  const openProviderCreate = () => {
    setCurrentProvider(null);
    providerForm.resetFields();
    providerForm.setFieldsValue({ provider_type: "openai_compatible", status: "active" });
    setProviderCreateModalOpen(true);
  };

  const openProviderEdit = (record) => {
    setCurrentProvider(record);
    providerForm.setFieldsValue({
      name: record.name,
      provider_type: record.provider_type,
      base_url: record.base_url,
      api_key: "",
      status: record.status,
      remark: record.remark || "",
    });
    setProviderEditDrawerOpen(true);
  };

  const closeProviderCreateModal = () => {
    setProviderCreateModalOpen(false);
    setCurrentProvider(null);
    providerForm.resetFields();
  };

  const closeProviderEditDrawer = () => {
    setProviderEditDrawerOpen(false);
    setCurrentProvider(null);
    providerForm.resetFields();
  };

  const handleProviderSubmit = async (values) => {
    setProviderSubmitting(true);
    try {
      if (!currentProvider) {
        await createProvider(values);
        message.success("供应商创建成功");
        closeProviderCreateModal();
      } else {
        const payload = { ...values };
        if (!payload.api_key) delete payload.api_key;
        await updateProvider(currentProvider.id, payload);
        message.success("供应商更新成功");
        closeProviderEditDrawer();
      }
      fetchProviders();
    } catch (error) {
      const detail = error?.response?.data?.detail || error?.message || "操作失败";
      message.error(detail);
    } finally {
      setProviderSubmitting(false);
    }
  };

  const handleDeleteProvider = async (id) => {
    try {
      await deleteProvider(id);
      message.success("供应商删除成功");
      fetchProviders();
    } catch (error) {
      const detail = error?.response?.data?.detail || error?.message || "操作失败";
      message.error(detail);
    }
  };

  const providerColumns = [
    { title: "ID", dataIndex: "id", width: 30 },
    { title: "名称", dataIndex: "name", width: 120 },
    {
      title: "类型",
      dataIndex: "provider_type",
      width: 140,
      render: (v) => <Tag>{v}</Tag>,
    },
    { title: "Base URL", dataIndex: "base_url", width: 220, ellipsis: true },
    { title: "API Key", dataIndex: "masked_api_key", width: 160 },
    {
      title: "状态",
      dataIndex: "status",
      width: 80,
      render: (v) => <Tag>{v}</Tag>,
    },
    {
      title: "操作",
      width: 160,
      render: (_, record) => (
        <Space size="small">
          <Button size="small" onClick={() => openProviderEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该供应商？"
            description="删除后不可恢复，请确认。"
            okText="确认删除"
            cancelText="取消"
            overlayClassName="model-config-popconfirm"
            okButtonProps={{ className: "model-config-popconfirm-ok" }}
            cancelButtonProps={{ className: "model-config-popconfirm-cancel" }}
            onConfirm={() => handleDeleteProvider(record.id)}
          >
            <Button size="small" className="model-config-delete-btn">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // ═══════════ Model ═══════════

  const fetchModels = async () => {
    setModelLoading(true);
    try {
      const res = await getModelList();
      setModels(res.data || []);
    } catch {
      message.error("获取模型列表失败");
    } finally {
      setModelLoading(false);
    }
  };

  useEffect(() => {
    fetchModels();
  }, []);

  const openModelCreate = () => {
    setCurrentModel(null);
    modelForm.resetFields();
    modelForm.setFieldsValue({ temperature: 0.7, max_tokens: 2048, timeout_seconds: 60, status: "active" });
    setModelCreateModalOpen(true);
  };

  const openModelEdit = (record) => {
    setCurrentModel(record);
    modelForm.setFieldsValue({
      provider_id: record.provider_id,
      model_name: record.model_name,
      display_name: record.display_name || "",
      temperature: record.temperature,
      max_tokens: record.max_tokens,
      timeout_seconds: record.timeout_seconds,
      status: record.status,
      remark: record.remark || "",
    });
    setModelEditDrawerOpen(true);
  };

  const closeModelCreateModal = () => {
    setModelCreateModalOpen(false);
    setCurrentModel(null);
    modelForm.resetFields();
  };

  const closeModelEditDrawer = () => {
    setModelEditDrawerOpen(false);
    setCurrentModel(null);
    modelForm.resetFields();
  };

  const handleModelSubmit = async (values) => {
    setModelSubmitting(true);
    try {
      if (!currentModel) {
        await createModel(values);
        message.success("模型创建成功");
        closeModelCreateModal();
      } else {
        await updateModel(currentModel.id, values);
        message.success("模型更新成功");
        closeModelEditDrawer();
      }
      fetchModels();
    } catch (error) {
      const detail = error?.response?.data?.detail || error?.message || "操作失败";
      message.error(detail);
    } finally {
      setModelSubmitting(false);
    }
  };

  const handleDeleteModel = async (id) => {
    try {
      await deleteModel(id);
      message.success("模型删除成功");
      fetchModels();
    } catch (error) {
      const detail = error?.response?.data?.detail || error?.message || "操作失败";
      message.error(detail);
    }
  };

  const handleTestModel = async (id) => {
    setTesting(id);
    try {
      const res = await testModel(id);
      setTestResult(res.data);
      setTestResultModalOpen(true);
    } catch {
      message.error("测试请求失败");
    } finally {
      setTesting(null);
    }
  };

  const modelColumns = [
    { title: "ID", dataIndex: "id", width: 30 },
    { title: "模型名称", dataIndex: "model_name", width: 140 },
    { title: "展示名称", dataIndex: "display_name", width: 120, render: (v) => v || "-" },
    { title: "供应商", dataIndex: "provider_name", width: 100, render: (v) => v || "-" },
    { title: "Temperature", dataIndex: "temperature", width: 100 },
    { title: "Max Tokens", dataIndex: "max_tokens", width: 90 },
    { title: "超时(s)", dataIndex: "timeout_seconds", width: 70 },
    {
      title: "状态",
      dataIndex: "status",
      width: 80,
      render: (v) => <Tag>{v}</Tag>,
    },
    {
      title: "操作",
      width: 220,
      render: (_, record) => (
        <Space size="small">
          <Button size="small" onClick={() => openModelEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该模型？"
            description="删除后不可恢复，请确认。"
            okText="确认删除"
            cancelText="取消"
            overlayClassName="model-config-popconfirm"
            okButtonProps={{ className: "model-config-popconfirm-ok" }}
            cancelButtonProps={{ className: "model-config-popconfirm-cancel" }}
            onConfirm={() => handleDeleteModel(record.id)}
          >
            <Button size="small" className="model-config-delete-btn">删除</Button>
          </Popconfirm>
          <Button
            size="small"
            loading={testing === record.id}
            onClick={() => handleTestModel(record.id)}
          >
            测试
          </Button>
        </Space>
      ),
    },
  ];

  // ═══════════ Scene Config ═══════════

  const fetchSceneConfigs = async () => {
    setSceneLoading(true);
    try {
      const res = await getSceneConfigList();
      setSceneConfigs(res.data || []);
    } catch {
      message.error("获取业务场景配置失败");
    } finally {
      setSceneLoading(false);
    }
  };

  useEffect(() => {
    fetchSceneConfigs();
  }, []);

  const openSceneEdit = (record) => {
    setCurrentScene(record);
    sceneForm.setFieldsValue({
      model_id: record.model_id,
      enabled: record.enabled,
      prompt_template: record.prompt_template || "",
      remark: record.remark || "",
    });
    setSceneEditDrawerOpen(true);
  };

  const closeSceneEditDrawer = () => {
    setSceneEditDrawerOpen(false);
    setCurrentScene(null);
    sceneForm.resetFields();
  };

  const handleSceneSubmit = async (values) => {
    setSceneSubmitting(true);
    try {
      await updateSceneConfig(currentScene.id, values);
      message.success("业务场景配置更新成功");
      closeSceneEditDrawer();
      fetchSceneConfigs();
    } catch (error) {
      const detail = error?.response?.data?.detail || error?.message || "操作失败";
      message.error(detail);
    } finally {
      setSceneSubmitting(false);
    }
  };

  const sceneColumns = [
    { title: "ID", dataIndex: "id", width: 30 },
    {
      title: "场景编码",
      dataIndex: "scene_code",
      width: 200,
    },
    {
      title: "场景名称",
      dataIndex: "scene_name",
      width: 160,
      render: (v) => SCENE_NAME_MAP[v] || v,
    },
    {
      title: "绑定模型",
      dataIndex: "model_name",
      width: 140,
      render: (v) => v || <Tag>未绑定</Tag>,
    },
    {
      title: "供应商",
      dataIndex: "provider_name",
      width: 100,
      render: (v) => v || "-",
    },
    {
      title: "启用",
      dataIndex: "enabled",
      width: 60,
      render: (v) => <Tag>{v ? "是" : "否"}</Tag>,
    },
    {
      title: "操作",
      width: 80,
      render: (_, record) => (
        <Button size="small" onClick={() => openSceneEdit(record)}>
          编辑
        </Button>
      ),
    },
  ];

  // ═══════════ Tabs ═══════════

  const tabItems = [
    {
      key: "providers",
      label: "供应商配置",
      children: (
        <Card className="model-config-card">
          <Space direction="vertical" style={{ width: "100%" }} size={16}>
            <Button type="primary" className="model-config-primary-btn" onClick={openProviderCreate}>
              新增供应商
            </Button>
            <Table
              rowKey="id"
              columns={providerColumns}
              dataSource={providers}
              loading={providerLoading}
              pagination={false}
              scroll={{ x: 1000 }}
              size="small"
            />
          </Space>
        </Card>
      ),
    },
    {
      key: "models",
      label: "模型配置",
      children: (
        <Card className="model-config-card">
          <Space direction="vertical" style={{ width: "100%" }} size={16}>
            <Button type="primary" className="model-config-primary-btn" onClick={openModelCreate}>
              新增模型
            </Button>
            <Table
              rowKey="id"
              columns={modelColumns}
              dataSource={models}
              loading={modelLoading}
              pagination={false}
              scroll={{ x: 1000 }}
              size="small"
            />
          </Space>
        </Card>
      ),
    },
    {
      key: "scenes",
      label: "业务场景配置",
      children: (
        <Card className="model-config-card">
          <Table
            rowKey="id"
            columns={sceneColumns}
            dataSource={sceneConfigs}
            loading={sceneLoading}
            pagination={false}
            scroll={{ x: 800 }}
            size="small"
          />
        </Card>
      ),
    },
  ];

  return (
    <div className="model-config-page">
      <Tabs defaultActiveKey="providers" items={tabItems} className="model-config-tabs" />

      {/* Provider Create Drawer */}
      <Drawer
        title="新增供应商"
        placement="right"
        width="50vw"
        rootClassName="model-config-drawer"
        open={providerCreateModalOpen}
        onClose={closeProviderCreateModal}
        destroyOnClose
        footer={
          <div className="model-config-drawer-footer">
            <Button onClick={closeProviderCreateModal} disabled={providerSubmitting}>
              取消
            </Button>
            <Button
              type="primary"
              className="model-config-primary-btn"
              onClick={() => providerForm.submit()}
              loading={providerSubmitting}
            >
              保存
            </Button>
          </div>
        }
      >
        <Form form={providerForm} layout="vertical" onFinish={handleProviderSubmit}>
          <Form.Item
            name="name"
            label="供应商名称"
            rules={[{ required: true, message: "请输入供应商名称" }]}
          >
            <Input placeholder="如 DeepSeek" />
          </Form.Item>
          <Form.Item name="provider_type" label="供应商类型" rules={[{ required: true }]}>
            <Select options={PROVIDER_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="API Base URL"
            rules={[{ required: true, message: "请输入 API Base URL" }]}
          >
            <Input placeholder="https://api.deepseek.com/v1" />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            rules={[{ required: true, message: "请输入 API Key" }]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={STATUS_OPTIONS} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Drawer>

      {/* Provider Edit Drawer */}
      <Drawer
        title="编辑供应商"
        placement="right"
        width="50vw"
        rootClassName="model-config-drawer"
        open={providerEditDrawerOpen}
        onClose={closeProviderEditDrawer}
        destroyOnClose
        footer={
          <div className="model-config-drawer-footer">
            <Button onClick={closeProviderEditDrawer} disabled={providerSubmitting}>
              取消
            </Button>
            <Button
              type="primary"
              className="model-config-primary-btn"
              onClick={() => providerForm.submit()}
              loading={providerSubmitting}
            >
              保存
            </Button>
          </div>
        }
      >
        <Form form={providerForm} layout="vertical" onFinish={handleProviderSubmit}>
          <Form.Item
            name="name"
            label="供应商名称"
            rules={[{ required: true, message: "请输入供应商名称" }]}
          >
            <Input placeholder="如 DeepSeek" />
          </Form.Item>
          <Form.Item name="provider_type" label="供应商类型" rules={[{ required: true }]}>
            <Select options={PROVIDER_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="API Base URL"
            rules={[{ required: true, message: "请输入 API Base URL" }]}
          >
            <Input placeholder="https://api.deepseek.com/v1" />
          </Form.Item>
          <Form.Item name="api_key" label="API Key">
            <Input.Password placeholder="留空则不修改" />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={STATUS_OPTIONS} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Drawer>

      {/* Model Create Drawer */}
      <Drawer
        title="新增模型"
        placement="right"
        width="50vw"
        rootClassName="model-config-drawer"
        open={modelCreateModalOpen}
        onClose={closeModelCreateModal}
        destroyOnClose
        footer={
          <div className="model-config-drawer-footer">
            <Button onClick={closeModelCreateModal} disabled={modelSubmitting}>
              取消
            </Button>
            <Button
              type="primary"
              className="model-config-primary-btn"
              onClick={() => modelForm.submit()}
              loading={modelSubmitting}
            >
              保存
            </Button>
          </div>
        }
      >
        <Form form={modelForm} layout="vertical" onFinish={handleModelSubmit}>
          <Form.Item
            name="provider_id"
            label="供应商"
            rules={[{ required: true, message: "请选择供应商" }]}
          >
            <Select
              placeholder="请选择供应商"
              options={providers
                .filter((p) => p.status === "active")
                .map((p) => ({ label: p.name, value: p.id }))}
            />
          </Form.Item>
          <Form.Item
            name="model_name"
            label="模型名称"
            rules={[{ required: true, message: "请输入模型名称" }]}
          >
            <Input placeholder="如 deepseek-chat" />
          </Form.Item>
          <Form.Item name="display_name" label="展示名称">
            <Input placeholder="可选，如 DeepSeek Chat V3" />
          </Form.Item>
          <Form.Item name="temperature" label="Temperature">
            <InputNumber min={0} max={2} step={0.1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="max_tokens" label="Max Tokens">
            <InputNumber min={1} max={128000} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="timeout_seconds" label="超时时间(秒)">
            <InputNumber min={1} max={600} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={STATUS_OPTIONS} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Drawer>

      {/* Model Edit Drawer */}
      <Drawer
        title="编辑模型"
        placement="right"
        width="50vw"
        rootClassName="model-config-drawer"
        open={modelEditDrawerOpen}
        onClose={closeModelEditDrawer}
        destroyOnClose
        footer={
          <div className="model-config-drawer-footer">
            <Button onClick={closeModelEditDrawer} disabled={modelSubmitting}>
              取消
            </Button>
            <Button
              type="primary"
              className="model-config-primary-btn"
              onClick={() => modelForm.submit()}
              loading={modelSubmitting}
            >
              保存
            </Button>
          </div>
        }
      >
        <Form form={modelForm} layout="vertical" onFinish={handleModelSubmit}>
          <Form.Item
            name="provider_id"
            label="供应商"
            rules={[{ required: true, message: "请选择供应商" }]}
          >
            <Select
              placeholder="请选择供应商"
              options={providers
                .filter((p) => p.status === "active")
                .map((p) => ({ label: p.name, value: p.id }))}
            />
          </Form.Item>
          <Form.Item
            name="model_name"
            label="模型名称"
            rules={[{ required: true, message: "请输入模型名称" }]}
          >
            <Input placeholder="如 deepseek-chat" />
          </Form.Item>
          <Form.Item name="display_name" label="展示名称">
            <Input placeholder="可选，如 DeepSeek Chat V3" />
          </Form.Item>
          <Form.Item name="temperature" label="Temperature">
            <InputNumber min={0} max={2} step={0.1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="max_tokens" label="Max Tokens">
            <InputNumber min={1} max={128000} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="timeout_seconds" label="超时时间(秒)">
            <InputNumber min={1} max={600} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={STATUS_OPTIONS} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Drawer>

      {/* Test Result Modal */}
      <Modal
        title="模型测试结果"
        open={testResultModalOpen}
        onCancel={() => setTestResultModalOpen(false)}
        footer={null}
        width={700}
      >
        {testResult ? (
          <Space direction="vertical" style={{ width: "100%" }} size={12}>
            <p>
              结果：{" "}
              <Tag>
                {testResult.success ? "成功" : "失败"}
              </Tag>
            </p>
            {testResult.error && (
              <p>
                <b>错误信息：</b>
                <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", marginTop: 8 }}>
                  {testResult.error}
                </pre>
              </p>
            )}
            {testResult.output && (
              <>
                <p><b>输出内容：</b></p>
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
                  {testResult.output}
                </pre>
              </>
            )}
          </Space>
        ) : (
          <p>无测试结果</p>
        )}
      </Modal>

      {/* Scene Edit Drawer */}
      <Drawer
        title="编辑业务场景配置"
        placement="right"
        width="50vw"
        rootClassName="model-config-drawer"
        open={sceneEditDrawerOpen}
        onClose={closeSceneEditDrawer}
        destroyOnClose
        footer={
          <div className="model-config-drawer-footer">
            <Button onClick={closeSceneEditDrawer} disabled={sceneSubmitting}>
              取消
            </Button>
            <Button
              type="primary"
              className="model-config-primary-btn"
              onClick={() => sceneForm.submit()}
              loading={sceneSubmitting}
            >
              保存
            </Button>
          </div>
        }
      >
        <Form form={sceneForm} layout="vertical" onFinish={handleSceneSubmit}>
          {currentScene && (
            <p style={{ marginBottom: 16 }}>
              场景：<b>{SCENE_NAME_MAP[currentScene.scene_code] || currentScene.scene_code}</b>
            </p>
          )}
          <Form.Item name="model_id" label="绑定模型">
            <Select
              allowClear
              placeholder="不绑定模型"
              options={models
                .filter((m) => m.status === "active")
                .map((m) => ({
                  label: `${m.model_name} (${m.provider_name || "未知供应商"})`,
                  value: m.id,
                }))}
            />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="prompt_template" label="Prompt 模板">
            <Input.TextArea
              rows={4}
              placeholder="可选，支持 {input} 占位符"
            />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}

export default ModelConfigPage;
