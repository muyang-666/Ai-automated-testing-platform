import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Drawer,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import {
  createScene,
  deleteScene,
  executeScene,
  getSceneList,
  runSceneChain,
  updateScene,
} from "../api/scene";
import SceneStepPage from "./SceneStepPage";

const { Title, Text } = Typography;

export default function ScenePage() {
  const [scenes, setScenes] = useState([]);
  const [loading, setLoading] = useState(false);

  const [form] = Form.useForm();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingScene, setEditingScene] = useState(null);

  const [currentScene, setCurrentScene] = useState(null);

  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [executeResult, setExecuteResult] = useState(null);

  const [chainRunning, setChainRunning] = useState(false);
  const [chainResultModalOpen, setChainResultModalOpen] = useState(false);
  const [chainResult, setChainResult] = useState(null);

  const loadScenes = async () => {
    try {
      setLoading(true);
      const res = await getSceneList();
      setScenes(res.data || []);
    } catch {
      message.error("读取场景列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadScenes();
  }, []);

  const openCreateModal = () => {
    setEditingScene(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEditModal = (record) => {
    setEditingScene(record);
    form.setFieldsValue({
      name: record.name,
      description: record.description,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();

      if (editingScene) {
        await updateScene(editingScene.id, values);
        message.success("场景更新成功");
      } else {
        await createScene(values);
        message.success("场景创建成功");
      }

      setModalOpen(false);
      form.resetFields();
      setEditingScene(null);
      loadScenes();
    } catch (error) {
      if (error?.response) {
        message.error(error?.response?.data?.detail || "保存失败");
      }
    }
  };

  const handleDelete = async (sceneId) => {
    try {
      await deleteScene(sceneId);
      message.success("场景删除成功");
      loadScenes();
    } catch {
      message.error("场景删除失败");
    }
  };

  const handleRunChain = async (sceneId) => {
    setChainRunning(true);
    try {
      const res = await runSceneChain(sceneId);
      setChainResult(res.data);
      setChainResultModalOpen(true);
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

  const handleExecute = async (sceneId) => {
    try {
      const res = await executeScene(sceneId);
      setExecuteResult(res.data);
      setExecuteModalOpen(true);
      message.success("场景执行完成");
    } catch (error) {
      message.error(error?.response?.data?.detail || "场景执行失败");
    }
  };

  if (currentScene) {
    return (
      <SceneStepPage
        scene={currentScene}
        onBack={() => setCurrentScene(null)}
      />
    );
  }

  const columns = [
    {
      title: "场景ID",
      dataIndex: "id",
      key: "id",
      width: 90,
    },
    {
      title: "场景名称",
      dataIndex: "name",
      key: "name",
    },
    {
      title: "执行",
      key: "result",
      width: 260,
      render: (_, record) => (
        <Space>
          <Button size="small" className="standard-action-btn" onClick={() => handleExecute(record.id)}>
            一键执行
          </Button>
          <Button
            size="small"
            className="standard-action-btn"
            loading={chainRunning}
            onClick={() => handleRunChain(record.id)}
          >
            串联执行
          </Button>
        </Space>
      ),
    },
    {
      title: "管理用例",
      key: "manage",
      width: 120,
      render: (_, record) => (
        <Button size="small" className="standard-action-btn" onClick={() => setCurrentScene(record)}>
          管理用例
        </Button>
      ),
    },
    {
      title: "操作",
      key: "action",
      width: 180,
      render: (_, record) => (
        <Space>
          <Button size="small" className="standard-action-btn" onClick={() => openEditModal(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确定删除这个场景吗？"
            description="删除后不可恢复，请确认。"
            okText="确认"
            cancelText="取消"
            overlayClassName="standard-popconfirm"
            okButtonProps={{ className: "standard-popconfirm-ok" }}
            cancelButtonProps={{ className: "standard-popconfirm-cancel" }}
            onConfirm={() => handleDelete(record.id)}
          >
            <Button className="standard-delete-btn" size="small">
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const stepColumns = [
    {
      title: "步骤ID",
      dataIndex: "step_order",
      key: "step_order",
      width: 100,
    },
    {
      title: "用例ID",
      dataIndex: "case_id",
      key: "case_id",
      width: 100,
    },
    {
      title: "名称",
      dataIndex: "case_name",
      key: "case_name",
    },
    {
      title: "执行状态",
      key: "status",
      width: 120,
      render: (_, record) => {
        if (record.result === "passed") {
          return <Tag color="success">passed</Tag>;
        }
        return <Tag color="error">failed</Tag>;
      },
    },
    {
      title: "响应状态码",
      dataIndex: "response_status_code",
      key: "response_status_code",
      render: (value) => value ?? "-",
    }
  ];

  return (
    <div className="standard-page">
      <Card className="standard-list-card">
        <Space
          style={{ width: "100%", justifyContent: "space-between", marginBottom: 16 }}
        >
          <Title level={4} style={{ margin: 0 }}>
            场景管理
          </Title>
          <Button type="primary" className="standard-primary-btn" onClick={openCreateModal}>
            新增场景
          </Button>
        </Space>

        <Table
          rowKey="id"
          loading={loading}
          dataSource={scenes}
          columns={columns}
        />
      </Card>

      <Drawer
        title={editingScene ? "编辑场景" : "新增场景"}
        placement="right"
        width="50vw"
        rootClassName="standard-drawer"
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditingScene(null);
          form.resetFields();
        }}
        destroyOnClose
        footer={
          <div className="standard-drawer-footer">
            <Button
              onClick={() => {
                setModalOpen(false);
                setEditingScene(null);
                form.resetFields();
              }}
            >
              取消
            </Button>
            <Button type="primary" className="standard-primary-btn" onClick={handleSave}>
              保存
            </Button>
          </div>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="场景名称"
            name="name"
            rules={[{ required: true, message: "请输入场景名称" }]}
          >
            <Input placeholder="请输入场景名称" />
          </Form.Item>

          <Form.Item label="场景描述" name="description">
            <Input.TextArea rows={3} placeholder="请输入场景描述" />
          </Form.Item>
        </Form>
      </Drawer>

      <Modal
        title={executeResult ? `场景执行结果：${executeResult.scene_name}` : "场景执行结果"}
        open={executeModalOpen}
        onCancel={() => {
          setExecuteModalOpen(false);
          setExecuteResult(null);
        }}
        footer={[
          <Button
            key="close"
            onClick={() => {
              setExecuteModalOpen(false);
              setExecuteResult(null);
            }}
          >
            关闭
          </Button>,
        ]}
        width={900}
      >
        {executeResult && (
          <Space direction="vertical" style={{ width: "100%" }} size={16}>
            <Space>
              <Text>总步骤数：{executeResult.total_steps}</Text>
              <Text>通过：{executeResult.passed_steps}</Text>
              <Text>失败：{executeResult.failed_steps}</Text>
              {executeResult.final_result === "passed" ? (
                <Tag color="success">passed</Tag>
              ) : (
                <Tag color="error">failed</Tag>
              )}
            </Space>

            <Table
              rowKey={(record) => `${record.step_order}-${record.case_id}`}
              dataSource={executeResult.steps || []}
              columns={stepColumns}
              pagination={false}
              size="small"
            />
          </Space>
        )}
      </Modal>

      <Modal
        title={chainResult ? `串联执行结果：${chainResult.scene_name}` : "串联执行结果"}
        open={chainResultModalOpen}
        onCancel={() => {
          setChainResultModalOpen(false);
          setChainResult(null);
        }}
        footer={[
          <Button
            key="close"
            onClick={() => {
              setChainResultModalOpen(false);
              setChainResult(null);
            }}
          >
            关闭
          </Button>,
        ]}
        width={900}
      >
        {chainResult && (
          <Space direction="vertical" style={{ width: "100%" }} size={16}>
            <Space>
              <Tag
                color={
                  chainResult.status === "passed" ? "success" : "error"
                }
              >
                {chainResult.status}
              </Tag>
              <Text>Run ID：{chainResult.scene_run_id}</Text>
              <Text>总步骤：{chainResult.total_steps}</Text>
              <Text>通过：{chainResult.passed_steps}</Text>
              <Text>失败：{chainResult.failed_steps}</Text>
              <Text>跳过：{chainResult.skipped_steps}</Text>
            </Space>

            {chainResult.context && Object.keys(chainResult.context).length > 0 && (
              <div>
                <Text strong>运行时上下文：</Text>
                <pre
                  style={{
                    background: "#f5f5f5",
                    padding: 12,
                    borderRadius: 4,
                    maxHeight: 200,
                    overflow: "auto",
                    fontSize: 12,
                  }}
                >
                  {JSON.stringify(chainResult.context, null, 2)}
                </pre>
              </div>
            )}

            <Table
              rowKey="step_order"
              dataSource={chainResult.steps || []}
              columns={[
                { title: "步骤", dataIndex: "step_order", width: 60 },
                { title: "名称", dataIndex: "step_name", ellipsis: true },
                { title: "用例ID", dataIndex: "case_id", width: 80 },
                {
                  title: "状态",
                  dataIndex: "status",
                  width: 80,
                  render: (v) => {
                    const map = { passed: "success", failed: "error", error: "error", skipped: "warning" };
                    return <Tag color={map[v] || "default"}>{v}</Tag>;
                  },
                },
                {
                  title: "响应码",
                  dataIndex: "response_status_code",
                  width: 80,
                  render: (v) => v ?? "-",
                },
                {
                  title: "提取变量",
                  dataIndex: "extracted_variables",
                  width: 160,
                  ellipsis: true,
                  render: (v) =>
                    v && Object.keys(v).length > 0 ? JSON.stringify(v) : "-",
                },
                {
                  title: "耗时",
                  dataIndex: "duration_ms",
                  width: 80,
                  render: (v) => (v != null ? `${v}ms` : "-"),
                },
                {
                  title: "错误",
                  dataIndex: "error_message",
                  width: 160,
                  ellipsis: true,
                  render: (v) =>
                    v ? <span style={{ color: "red" }}>{v}</span> : "-",
                },
              ]}
              pagination={false}
              size="small"
              scroll={{ x: 900 }}
            />
          </Space>
        )}
      </Modal>
    </div>
  );
}
