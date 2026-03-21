// 测试用例模块的前端控制台。定义测试内容

// useEffect, useState 这是 React 的两个最常用 Hook：
import { useEffect, useState } from "react";
// 从 antd 导入 UI 组件。 AntD 提供现成的后台管理页面积木
import {
  Button,
  Card,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Space,
  Table,
} from "antd";
// 这个 api 是封装好的 Axios 实例，作用是：前端向后端发 HTTP 请求（如 api.post("/cases", values)），是前后端通信的桥梁。
import api from "../services/api";

// 这表示定义了一个 React 函数组件。可以理解成：这整个页面，就是这个函数返回出来的 UI。
function CasePage() {
  const [cases, setCases] = useState([]); // cases = 当前页面展示的测试用例列表；setCases = 更新列表的方法
  const [loading, setLoading] = useState(false); // loading：当前是否正在加载数据
  const [submitting, setSubmitting] = useState(false); // submitting：当前是否正在提交表单（创建 / 编辑）
  const [modalOpen, setModalOpen] = useState(false); // modalOpen：弹窗是否打开
  const [modalMode, setModalMode] = useState("create"); // modalMode：当前弹窗模式，create=创建，edit=编辑
  const [currentCase, setCurrentCase] = useState(null); // currentCase：当前正在编辑的测试用例
  const [form] = Form.useForm(); // form：是 AntD 表单实例，作用：操作表单（读取 / 重置值）

  // 这个函数负责：从后端获取测试用例列表。去后端拿最新的测试用例列表，然后同步到页面状态里
  const fetchCases = async () => {
    setLoading(true); // 标记开始加载
    try {
      const res = await api.get("/cases"); // 向后端发 GET /cases 请求（对应后端 @router.get("", summary="查询测试用例列表") 接口）
      setCases(res.data); // 把后端返回的列表数据存入状态，页面自动刷新
    } catch (error) {
      message.error("获取用例列表失败"); // 请求失败时弹错误提示
    } finally {
      setLoading(false); // 无论成功 / 失败，最终关闭加载状态
    }
  };

  // 这个函数负责：打开“新建测试用例”弹窗。它不直接创建，只是把弹窗切换到 create 模式
  const openCreateModal = () => {
    setModalMode("create");
    setCurrentCase(null);
    form.resetFields(); // 清空表单，避免复用上一次编辑数据
    setModalOpen(true);
  };

  // 这个函数负责：打开“编辑测试用例”弹窗，并把当前行数据回填到表单里
  const openEditModal = (record) => {
    setModalMode("edit");
    setCurrentCase(record);

    // 回填表单数据。这样弹窗打开后，用户看到的是当前用例原来的内容
    form.setFieldsValue({
      name: record.name,
      description: record.description,
      method: record.method,
      url: record.url,
      headers: record.headers,
      body: record.body,
      expected_result: record.expected_result,
    });

    setModalOpen(true);
  };

  // 这个函数负责：关闭弹窗并清空当前编辑状态
  const handleCancelModal = () => {
    setModalOpen(false);
    setCurrentCase(null);
    form.resetFields();
  };

  // 这个函数负责：提交弹窗表单。它同时兼容“创建”和“编辑”
  // values 参数：来自 AntD 表单的 onFinish，是表单校验通过后自动收集的用户输入
  const handleSubmitCase = async (values) => {
    setSubmitting(true);
    try {
      if (modalMode === "create") {
        // create 模式：调用后端 POST /cases 接口创建用例
        await api.post("/cases", values);
        message.success("测试用例创建成功");
      } else {
        // edit 模式：调用后端 PUT /cases/{id} 接口更新用例
        await api.put(`/cases/${currentCase.id}`, values);
        message.success("测试用例更新成功");
      }

      handleCancelModal(); // 成功后关闭弹窗
      fetchCases(); // 重新拉取列表，页面展示最新数据
    } catch (error) {
      message.error(modalMode === "create" ? "创建测试用例失败" : "更新测试用例失败");
    } finally {
      setSubmitting(false);
    }
  };

  // 这个函数负责：删除某条测试用例
  const handleDeleteCase = async (caseId) => {
    try {
      await api.delete(`/cases/${caseId}`); // 调用后端 DELETE /cases/{id} 接口删除用例
      message.success("测试用例删除成功");
      fetchCases(); // 删除成功后重新拉取列表
    } catch (error) {
      message.error("删除测试用例失败");
    }
  };

  // 这个函数负责：让 AI 为某条测试用例生成 pytest 代码。 “AI 生成测试代码”的入口
    const handleGenerateCode = async (caseId) => {
      try {
        const res = await api.post(`/ai/generate-case/${caseId}`);
        message.success("AI代码生成成功");

        // 主动作成功后，再尝试刷新；刷新失败不要覆盖主成功提示
        try {
          await fetchCases();
        } catch (refreshError) {
          message.warning("代码已生成成功，但列表刷新失败，请手动刷新页面");
        }
      } catch (error) {
        const detail = error?.response?.data?.detail || "AI代码生成失败";
        message.error(detail);
      }
    };

  // 页面一打开就自动查询列表
  useEffect(() => {
    fetchCases();
  }, []);

  // 表格列定义 columns。 CasePage 这个页面要把 case 的哪些信息展示给用户
  const columns = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "名称", dataIndex: "name" },
    { title: "方法", dataIndex: "method", width: 100 },
    { title: "URL", dataIndex: "url", ellipsis: true },
    {
      title: "是否已生成代码",
      dataIndex: "generated_test_code",
      width: 140,
      render: (value) => (value ? "是" : "否"),
    },
    {
      title: "操作",
      width: 260,
      render: (_, record) => (
        <Space>
          <Button onClick={() => openEditModal(record)}>编辑</Button>

          <Popconfirm
            title="确认删除这条测试用例吗？"
            okText="确认"
            cancelText="取消"
            onConfirm={() => handleDeleteCase(record.id)}
          >
            <Button danger>删除</Button>
          </Popconfirm>

          <Button type="primary" onClick={() => handleGenerateCase(record.id)}>
            AI生成代码
          </Button>
        </Space>
      ),
    },
  ];

  return (
    // Space 表示竖向排列页面内容。 这次优化后，页面主结构改成：顶部操作区 + 列表区
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card
        title="测试用例列表"
        extra={
          <Button type="primary" onClick={openCreateModal}>
            新建测试用例
          </Button>
        }
      >
        <Table
          rowKey="id"
          columns={columns}
          dataSource={cases}
          loading={loading}
          pagination={false}
        />
      </Card>

      {/* Modal：这里复用同一套表单来做“创建”和“编辑” */}
      <Modal
        title={modalMode === "create" ? "新建测试用例" : "编辑测试用例"}
        open={modalOpen}
        onCancel={handleCancelModal}
        onOk={() => form.submit()} // 点击确定按钮时，主动触发表单提交
        confirmLoading={submitting}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleSubmitCase}>
          <Form.Item name="name" label="用例名称" rules={[{ required: true, message: "请输入用例名称" }]}>
            <Input />
          </Form.Item>

          <Form.Item name="description" label="用例描述">
            <Input />
          </Form.Item>

          <Form.Item name="method" label="请求方法" rules={[{ required: true, message: "请输入请求方法" }]}>
            <Input placeholder="POST" />
          </Form.Item>

          <Form.Item name="url" label="请求地址" rules={[{ required: true, message: "请输入请求地址" }]}>
            <Input placeholder="http://example.com/api/login" />
          </Form.Item>

          <Form.Item name="headers" label="请求头">
            <Input.TextArea
              rows={3}
              placeholder='{"Content-Type": "application/json"}'
            />
          </Form.Item>

          <Form.Item name="body" label="请求体">
            <Input.TextArea
              rows={4}
              placeholder='{"username": "test", "password": "123456"}'
            />
          </Form.Item>

          <Form.Item name="expected_result" label="预期结果">
            <Input.TextArea
              rows={4}
              placeholder='{"code": 200, "message": "success"}'
            />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

export default CasePage;