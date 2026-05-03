import { useCallback, useEffect, useMemo, useState } from "react";
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
  createUser,
  deleteUser,
  getRoleList,
  getUserList,
  updateUser,
  updateUserRoles,
} from "../api/user";

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
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "用户名", dataIndex: "username", width: 140 },
    { title: "显示名称", dataIndex: "display_name", width: 160 },
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
      width: 220,
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
          <Button size="small" onClick={() => openEditModal(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该用户吗？"
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
        title="用户管理"
        extra={
          <Button type="primary" onClick={openCreateModal}>
            新增用户
          </Button>
        }
      >
        <Space style={{ marginBottom: 16 }}>
          <Input.Search
            placeholder="搜索用户名、显示名称或邮箱"
            allowClear
            onSearch={handleSearch}
            style={{ width: 260 }}
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
          dataSource={users}
          loading={loading}
          pagination={{ pageSize: 10 }}
          scroll={{ x: 980 }}
        />
      </Card>

      <Modal
        title={editingUser ? "编辑用户" : "新增用户"}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={closeModal}
        confirmLoading={submitting}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="username"
            label="用户名"
            rules={
              editingUser
                ? []
                : [{ required: true, message: "请输入用户名" }]
            }
          >
            <Input disabled={!!editingUser} placeholder="请输入用户名" maxLength={50} />
          </Form.Item>

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

          <Form.Item name="display_name" label="显示名称">
            <Input placeholder="请输入显示名称" maxLength={100} />
          </Form.Item>

          <Form.Item name="email" label="邮箱">
            <Input placeholder="请输入邮箱" maxLength={100} />
          </Form.Item>

          <Form.Item name="status" label="状态">
            <Select
              options={[
                { label: "启用", value: "active" },
                { label: "停用", value: "disabled" },
              ]}
            />
          </Form.Item>

          <Form.Item name="role_ids" label="角色">
            <Select
              mode="multiple"
              allowClear
              placeholder="请选择角色"
              options={roleOptions}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
