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
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { getProjectList } from "../api/project";
import {
  createScene,
  deleteScene,
  executeScene,
  getSceneList,
  updateScene,
} from "../api/scene";
import ModuleTree from "../components/ModuleTree";
import {
  getStoredProjectId,
  resolveProjectId,
  storeProjectId,
} from "../utils/projectSelection";
import SceneStepPage from "./SceneStepPage";

const { Title, Text } = Typography;

export default function ScenePage() {
  const [scenes, setScenes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(getStoredProjectId);
  const [selectedModuleId, setSelectedModuleId] = useState(null);
  const [unboundModuleOnly, setUnboundModuleOnly] = useState(false);
  const [includeChildren, setIncludeChildren] = useState(false);

  const [form] = Form.useForm();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingScene, setEditingScene] = useState(null);

  const [currentScene, setCurrentScene] = useState(null);

  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [executeResult, setExecuteResult] = useState(null);

  const loadProjects = async () => {
    try {
      const res = await getProjectList();
      setProjects(res.data || []);
    } catch {
      message.error("获取项目列表失败");
    }
  };

  const loadScenes = async () => {
    try {
      setLoading(true);
      const params = {};
      if (selectedProjectId) params.project_id = selectedProjectId;
      if (unboundModuleOnly) {
        params.unbound_module = true;
      } else if (selectedModuleId != null) {
        params.module_id = selectedModuleId;
        if (includeChildren) params.include_children = true;
      }
      const res = await getSceneList(params);
      setScenes(res.data || []);
    } catch {
      message.error("读取场景列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  useEffect(() => {
    if (projects.length > 0) {
      const nextProjectId = resolveProjectId(projects, selectedProjectId);
      if (nextProjectId !== selectedProjectId) {
        setSelectedProjectId(nextProjectId);
        storeProjectId(nextProjectId);
      }
    }
  }, [projects, selectedProjectId]);

  useEffect(() => {
    loadScenes();
  }, [selectedProjectId, selectedModuleId, unboundModuleOnly, includeChildren]);

  const handleProjectChange = (value) => {
    setSelectedProjectId(value);
    storeProjectId(value);
    setSelectedModuleId(null);
    setUnboundModuleOnly(false);
  };

  const handleModuleSelect = (moduleId) => {
    setSelectedModuleId(moduleId);
    setUnboundModuleOnly(false);
  };

  const handleModuleChange = () => {
    loadScenes();
  };

  const handleUnboundModuleClick = () => {
    setSelectedModuleId(null);
    setIncludeChildren(false);
    setUnboundModuleOnly(true);
  };

  const openCreateModal = () => {
    setEditingScene(null);
    form.resetFields();
    form.setFieldsValue({
      project_id: selectedProjectId || undefined,
      module_id: selectedModuleId || undefined,
      status: "active",
    });
    setModalOpen(true);
  };

  const openEditModal = (record) => {
    setEditingScene(record);
    form.setFieldsValue({
      name: record.name,
      description: record.description,
      project_id: record.project_id,
      module_id: record.module_id,
      status: record.status,
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
      width: 180,
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
            onClick={() => setCurrentScene(record)}
          >
            选择用例串联执行
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
    <div className="standard-page scene-page">
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Card className="standard-toolbar-card">
          <Row justify="space-between" align="middle">
            <Col>
              <Space>
                <span className="standard-project-label">项目：</span>
                <Select
                  placeholder="请选择项目"
                  value={selectedProjectId}
                  onChange={handleProjectChange}
                  options={projects.map((p) => ({ label: p.name, value: p.id }))}
                  style={{ width: 220 }}
                  popupClassName="standard-select-dropdown"
                />
              </Space>
            </Col>
            <Col>
              <Button type="primary" className="standard-primary-btn" onClick={openCreateModal}>
                新增场景
              </Button>
            </Col>
          </Row>
        </Card>

        <div className="standard-layout">
          <div className="standard-module-shell">
            <ModuleTree
              projectId={selectedProjectId}
              selectedModuleId={selectedModuleId}
              onSelect={handleModuleSelect}
              onChange={handleModuleChange}
              createButtonLabel="新增模块"
              createButtonClassName="requirement-module-header-btn"
              createButtonIcon={null}
              headerExtra={
                <Button
                  className="requirement-module-header-btn"
                  block
                  onClick={handleUnboundModuleClick}
                >
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

          <div className="standard-list-panel">
            <Card title="场景列表" className="standard-list-card">
              <Table
                rowKey="id"
                loading={loading}
                dataSource={scenes}
                columns={columns}
                scroll={{ x: 1000 }}
              />
            </Card>
          </div>
        </div>
      </Space>

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
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="归属项目" name="project_id">
                <Select
                  placeholder="请选择项目"
                  allowClear
                  options={projects.map((p) => ({ label: p.name, value: p.id }))}
                  popupClassName="standard-select-dropdown"
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="归属模块" name="module_id">
                <InputNumber placeholder="模块ID（可选）" style={{ width: "100%" }} />
              </Form.Item>
            </Col>
          </Row>

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

      <Drawer
        title={executeResult ? `场景执行结果：${executeResult.scene_name}` : "场景执行结果"}
        placement="right"
        width="50vw"
        rootClassName="standard-drawer scene-result-drawer"
        open={executeModalOpen}
        onClose={() => {
          setExecuteModalOpen(false);
          setExecuteResult(null);
        }}
        footer={null}
        destroyOnClose
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
      </Drawer>
    </div>
  );
}
