import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
} from "antd";
import {
  createProject,
  deleteProject,
  getProjectList,
  updateProject,
} from "../api/project";

const STATUS_OPTIONS = [
  { label: "全部", value: "" },
  { label: "启用", value: "active" },
  { label: "归档", value: "archived" },
  { label: "停用", value: "disabled" },
];

const STATUS_TAG_MAP = {
  active: { color: "success", label: "启用" },
  archived: { color: "warning", label: "归档" },
  disabled: { color: "default", label: "停用" },
};

export default function ProjectPage() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingProject, setEditingProject] = useState(null);
  const [keyword, setKeyword] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [form] = Form.useForm();

  const fetchProjects = async (searchKeyword, searchStatus) => {
    setLoading(true);
    try {
      const params = {};
      const kw = searchKeyword !== undefined ? searchKeyword : keyword;
      const st = searchStatus !== undefined ? searchStatus : statusFilter;
      if (kw) params.keyword = kw;
      if (st) params.status = st;
      const res = await getProjectList(params);
      setProjects(res.data || []);
    } catch (error) {
      message.error("获取项目列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const openCreateModal = () => {
    setEditingProject(null);
    form.resetFields();
    form.setFieldsValue({ status: "active" });
    setModalOpen(true);
  };

  const openEditModal = (record) => {
    setEditingProject(record);
    form.setFieldsValue({
      name: record.name,
      description: record.description,
      status: record.status,
    });
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingProject(null);
    form.resetFields();
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      if (editingProject) {
        await updateProject(editingProject.id, values);
        message.success("项目更新成功");
      } else {
        await createProject(values);
        message.success("项目创建成功");
      }

      closeModal();
      fetchProjects();
    } catch (error) {
      if (error?.response) {
        message.error(error?.response?.data?.detail || "保存失败");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (projectId) => {
    try {
      await deleteProject(projectId);
      message.success("项目删除成功");
      fetchProjects();
    } catch (error) {
      message.error("项目删除失败");
    }
  };

  const handleSearch = (value) => {
    setKeyword(value);
    fetchProjects(value, statusFilter);
  };

  const handleStatusChange = (value) => {
    setStatusFilter(value);
    fetchProjects(keyword, value);
  };

  const columns = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "项目名称", dataIndex: "name" },
    { title: "项目描述", dataIndex: "description", ellipsis: true },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value) => {
        const tag = STATUS_TAG_MAP[value] || { color: "default", label: value };
        return <Tag color={tag.color}>{tag.label}</Tag>;
      },
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 180,
      render: (value) => (value ? new Date(value).toLocaleString("zh-CN") : "-"),
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      width: 180,
      render: (value) => (value ? new Date(value).toLocaleString("zh-CN") : "-"),
    },
    {
      title: "操作",
      width: 200,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => openEditModal(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该项目吗？"
            okText="确认"
            cancelText="取消"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button danger size="small">
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card
        title="项目管理"
        extra={
          <Button type="primary" onClick={openCreateModal}>
            新增项目
          </Button>
        }
      >
        <Space style={{ marginBottom: 16 }}>
          <Input.Search
            placeholder="搜索项目名称"
            allowClear
            onSearch={handleSearch}
            style={{ width: 240 }}
          />
          <Select
            placeholder="状态筛选"
            options={STATUS_OPTIONS}
            value={statusFilter}
            onChange={handleStatusChange}
            style={{ width: 120 }}
          />
        </Space>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={projects}
          loading={loading}
          pagination={false}
        />
      </Card>

      <Modal
        title={editingProject ? "编辑项目" : "新增项目"}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={closeModal}
        confirmLoading={submitting}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="项目名称"
            rules={[{ required: true, message: "请输入项目名称" }]}
          >
            <Input placeholder="请输入项目名称" maxLength={100} />
          </Form.Item>

          <Form.Item name="description" label="项目描述">
            <Input.TextArea rows={3} placeholder="请输入项目描述" />
          </Form.Item>

          <Form.Item name="status" label="项目状态">
            <Select
              options={[
                { label: "启用", value: "active" },
                { label: "归档", value: "archived" },
                { label: "停用", value: "disabled" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
