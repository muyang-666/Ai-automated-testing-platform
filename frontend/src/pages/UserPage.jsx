import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  Drawer,
  Form,
  Input,
  message,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import {
  createUser,
  deleteUser,
  getRoleList,
  getUserList,
  updateUser,
  updateUserRoles,
} from "../api/user";

const { Text, Title } = Typography;

const STATUS_OPTIONS = [
  { label: "全部", value: "" },
  { label: "启用", value: "active" },
  { label: "停用", value: "disabled" },
];

const STATUS_TAG_MAP = {
  active: { color: "success", label: "启用" },
  disabled: { color: "default", label: "停用" },
};

const getErrorMessage = (error, fallback) =>
  error?.response?.data?.detail ||
  error?.response?.data?.message ||
  error.message ||
  fallback;

export default function UserPage() {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [keyword, setKeyword] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [form] = Form.useForm();

  const roleOptions = useMemo(
    () => roles.map((role) => ({ label: role.name, value: role.id })),
    [roles]
  );

  const roleCodeToId = useMemo(() => {
    const map = {};
    roles.forEach((role) => {
      map[role.code] = role.id;
    });
    return map;
  }, [roles]);

  const fetchUsers = useCallback(async (searchKeyword = "", searchStatus = "") => {
    setLoading(true);
    try {
      const params = {};
      const kw = searchKeyword;
      const st = searchStatus;
      if (kw) params.keyword = kw;
      if (st) params.status = st;
      const res = await getUserList(params);
      setUsers(res.data || []);
    } catch (error) {
      message.error(getErrorMessage(error, "获取用户列表失败"));
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchRoles = useCallback(async () => {
    try {
      const res = await getRoleList();
      setRoles(res.data || []);
    } catch (error) {
      message.error(getErrorMessage(error, "获取角色列表失败"));
    }
  }, []);

  useEffect(() => {
    fetchRoles();
    fetchUsers();
  }, [fetchRoles, fetchUsers]);

  const openCreateModal = () => {
    setEditingUser(null);
    form.resetFields();
    form.setFieldsValue({ status: "active", role_ids: [] });
    setModalOpen(true);
  };

  const openEditModal = (record) => {
    setEditingUser(record);
    form.resetFields();
    form.setFieldsValue({
      username: record.username,
      display_name: record.display_name,
      email: record.email,
      status: record.status,
      role_ids: (record.roles || []).map((code) => roleCodeToId[code]).filter(Boolean),
    });
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingUser(null);
    form.resetFields();
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      const roleIds = values.role_ids || [];

      if (editingUser) {
        const payload = {
          display_name: values.display_name,
          email: values.email,
          status: values.status,
        };
        if (values.password) {
          payload.password = values.password;
        }
        await updateUser(editingUser.id, payload);
        await updateUserRoles(editingUser.id, { role_ids: roleIds });
        message.success("用户更新成功");
      } else {
        await createUser({
          username: values.username,
          password: values.password,
          display_name: values.display_name,
          email: values.email,
          status: values.status,
          role_ids: roleIds,
        });
        message.success("用户创建成功");
      }

      closeModal();
      fetchUsers(keyword, statusFilter);
    } catch (error) {
      if (error?.response) {
        message.error(getErrorMessage(error, "保存用户失败"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (userId) => {
    try {
      await deleteUser(userId);
      message.success("用户删除成功");
      fetchUsers(keyword, statusFilter);
    } catch (error) {
      message.error(getErrorMessage(error, "用户删除失败"));
    }
  };

  const handleSearch = (value) => {
    setKeyword(value);
    fetchUsers(value, statusFilter);
  };

  const handleStatusChange = (value) => {
    setStatusFilter(value);
    fetchUsers(keyword, value);
  };

  const columns = [
    { title: "ID", dataIndex: "id", width: 70 },
    {
      title: "用户名",
      dataIndex: "username",
      width: 160,
      render: (value) => <Text strong>{value}</Text>,
    },
    { title: "显示名称", dataIndex: "display_name", width: 170, render: (value) => value || "-" },
    { title: "邮箱", dataIndex: "email", ellipsis: true },
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
      title: "角色",
      dataIndex: "roles",
      width: 240,
      render: (value = []) => (
        <Space size={[4, 4]} wrap>
          {value.length ? value.map((role) => <Tag key={role}>{role}</Tag>) : "-"}
        </Space>
      ),
    },
    {
      title: "最后登录",
      dataIndex: "last_login_at",
      width: 180,
      render: (value) => (value ? new Date(value).toLocaleString("zh-CN") : "-"),
    },
    {
      title: "操作",
      width: 180,
      render: (_, record) => (
        <Space>
          <Button size="small" className="standard-action-btn" onClick={() => openEditModal(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该用户吗？"
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

  const activeCount = users.filter((user) => user.status === "active").length;
  const disabledCount = users.filter((user) => user.status === "disabled").length;

  return (
    <div className="standard-page user-page">
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Card className="standard-toolbar-card user-toolbar-card">
          <Row justify="space-between" align="middle" gutter={[16, 16]}>
            <Col>
              <Space direction="vertical" size={2}>
                <Title level={4}>用户管理</Title>
                <Text>维护账号状态、角色授权和基础信息</Text>
              </Space>
            </Col>
            <Col>
              <Button type="primary" className="standard-primary-btn" onClick={openCreateModal}>
                新增用户
              </Button>
            </Col>
          </Row>
        </Card>

        <Row gutter={[16, 16]}>
          <Col xs={24} md={6}>
            <Card className="user-stat-card">
              <Statistic title="用户总数" value={users.length} />
            </Card>
          </Col>
          <Col xs={24} md={6}>
            <Card className="user-stat-card">
              <Statistic title="启用用户" value={activeCount} />
            </Card>
          </Col>
          <Col xs={24} md={6}>
            <Card className="user-stat-card">
              <Statistic title="停用用户" value={disabledCount} />
            </Card>
          </Col>
          <Col xs={24} md={6}>
            <Card className="user-stat-card">
              <Statistic title="角色数量" value={roles.length} />
            </Card>
          </Col>
        </Row>

        <Card title="用户列表" className="standard-list-card user-list-card">
          <Row justify="space-between" align="middle" gutter={[12, 12]} className="user-list-tools">
            <Col>
              <Space>
                <Input.Search
                  placeholder="搜索用户名、显示名称或邮箱"
                  allowClear
                  onSearch={handleSearch}
                  style={{ width: 320 }}
                />
                <Select
                  placeholder="状态筛选"
                  options={STATUS_OPTIONS}
                  value={statusFilter}
                  onChange={handleStatusChange}
                  style={{ width: 140 }}
                  popupClassName="standard-select-dropdown"
                />
              </Space>
            </Col>
            <Col>
              <Tag>当前 {users.length} 个用户</Tag>
            </Col>
          </Row>

          <Table
            rowKey="id"
            columns={columns}
            dataSource={users}
            loading={loading}
            pagination={{ pageSize: 10 }}
            scroll={{ x: 1040 }}
          />
        </Card>
      </Space>

      <Drawer
        title={editingUser ? "编辑用户" : "新增用户"}
        placement="right"
        width="50vw"
        rootClassName="standard-drawer user-drawer"
        open={modalOpen}
        onClose={closeModal}
        destroyOnClose
        footer={
          <div className="standard-drawer-footer">
            <Button onClick={closeModal} disabled={submitting}>取消</Button>
            <Button type="primary" className="standard-primary-btn" onClick={handleSubmit} loading={submitting}>
              保存
            </Button>
          </div>
        }
      >
        <Form form={form} layout="vertical" autoComplete="off">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="username"
                label="用户名"
                rules={
                  editingUser
                    ? []
                    : [{ required: true, message: "请输入用户名" }]
                }
              >
                <Input disabled={!!editingUser} placeholder="请输入用户名" maxLength={50} autoComplete="off" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="password"
                label={editingUser ? "新密码" : "密码"}
                rules={
                  editingUser
                    ? []
                    : [{ required: true, message: "请输入密码" }]
                }
              >
                <Input.Password
                  placeholder={editingUser ? "不填写则不修改密码" : "请输入密码"}
                  autoComplete="new-password"
                />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="display_name" label="显示名称">
                <Input placeholder="请输入显示名称" maxLength={100} autoComplete="off" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="email" label="邮箱">
                <Input placeholder="请输入邮箱" maxLength={100} autoComplete="off" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="status" label="状态">
                <Select
                  popupClassName="standard-select-dropdown"
                  options={[
                    { label: "启用", value: "active" },
                    { label: "停用", value: "disabled" },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="role_ids" label="角色">
                <Select
                  mode="multiple"
                  allowClear
                  placeholder="请选择角色"
                  options={roleOptions}
                  popupClassName="standard-select-dropdown"
                />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Drawer>
    </div>
  );
}
