// 测试用例模块的前端控制台。定义测试内容

// useEffect, useState 这是 React 的两个最常用 Hook：
import { useEffect, useState } from "react";
// 从 antd 导入 UI 组件。 AntD 提供现成的后台管理页面积木
import { Button, Card, Form, Input, message, Space, Table } from "antd";
// 这个 api 是封装好的 Axios 实例，作用是：前端向后端发 HTTP 请求（如 api.post("/cases", values)），是前后端通信的桥梁。
import api from "../services/api";

// 这表示定义了一个 React 函数组件。可以理解成：这整个页面，就是这个函数返回出来的 UI。
function CasePage() {
  const [cases, setCases] = useState([]);  // cases = 当前页面展示的测试用例列表；setCases = 更新列表的方法
  const [loading, setLoading] = useState(false); // loading：当前是否正在加载数据
  const [form] = Form.useForm();  // form：是 AntD 表单实例，作用：操作表单（读取 / 重置值）

  // 这个函数负责：从后端获取测试用例列表。去后端拿最新的测试用例列表，然后同步到页面状态里
  const fetchCases = async () => {
    setLoading(true);  // 标记开始加载
    try {
      const res = await api.get("/cases");  // 向后端发 GET /cases 请求（对应后端 @router.get("", summary="查询测试用例列表") 接口）
      setCases(res.data);  // 把后端返回的列表数据存入状态，页面自动刷新
    } catch (error) {
      message.error("获取用例列表失败");  // 请求失败时弹错误提示
    } finally {
      setLoading(false);  // 无论成功 / 失败，最终关闭加载状态
    }
  };

  // 这个函数负责：提交表单，创建测试用例。 “创建 case”的前端入口
  const handleCreateCase = async (values) => { // values 参数：来自 AntD 表单的 onFinish，是表单校验通过后自动收集的用户输入
    try {
      await api.post("/cases", values);  // 调用后端 POST /cases 接口创建用例
      message.success("测试用例创建成功");  // 创建成功提示
      form.resetFields();  // 清空表单
      fetchCases();  // 重新拉取列表，页面展示最新数据
    } catch (error) {
      message.error("创建测试用例失败");
    }
  };

  // 这个函数负责：让 AI 为某条测试用例生成 pytest 代码。 “AI 生成测试代码”的入口
  const handleGenerateCase = async (caseId) => {  // caseId 参数：当前测试用例的 id（如 1、2）
    try {
      await api.post(`/ai/generate-case/${caseId}`);  // 请求地址：api.post(/ai/generate-case/${caseId})，对应后端 “根据用例生成测试代码” 接口
      message.success(`AI 已生成 case ${caseId} 的测试代码`);
      fetchCases();  // 生成成功后刷新列表，让表格 “是否已生成代码” 列更新
    } catch (error) {
      message.error("AI 生成测试代码失败");
    }
  };
  // 页面一打开就自动查询列表
  useEffect(() => {
    fetchCases();
  }, []);

  // 表格列定义 columns。 CasePage 这个页面要把 case 的哪些信息展示给用户
  const columns = [
    { title: "ID", dataIndex: "id" },
    { title: "名称", dataIndex: "name" },
    { title: "方法", dataIndex: "method" },
    { title: "URL", dataIndex: "url" },
    {
      title: "是否已生成代码",
      dataIndex: "generated_test_code",
      render: (value) => (value ? "是" : "否"),
    },
    {
      title: "操作",
      render: (_, record) => (
        <Button type="primary" onClick={() => handleGenerateCase(record.id)}>
          AI生成代码
        </Button>
      ),
    },
  ];

  return (
      // Space 表示竖向排列页面内容，整个页面分为上下两块：新建测试用例（表单），测试用例列表（表格）
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card title="新建测试用例">
        <Form form={form} layout="vertical" onFinish={handleCreateCase}>
          <Form.Item name="name" label="用例名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>

          <Form.Item name="description" label="用例描述">
            <Input />
          </Form.Item>

          <Form.Item name="method" label="请求方法" rules={[{ required: true }]}>
            <Input placeholder="POST" />
          </Form.Item>

          <Form.Item name="url" label="请求地址" rules={[{ required: true }]}>
            <Input placeholder="http://example.com/api/login" />
          </Form.Item>

          <Form.Item name="headers" label="请求头">
            <Input.TextArea placeholder='{"Content-Type": "application/json"}' />
          </Form.Item>

          <Form.Item name="body" label="请求体">
            <Input.TextArea placeholder='{"username": "test", "password": "123456"}' />
          </Form.Item>

          <Form.Item name="expected_result" label="预期结果">
            <Input.TextArea placeholder='{"code": 200, "message": "success"}' />
          </Form.Item>

          <Button type="primary" htmlType="submit">
            创建用例
          </Button>
        </Form>
      </Card>

      <Card title="测试用例列表">
        <Table
          rowKey="id"
          columns={columns}
          dataSource={cases}
          loading={loading}
          pagination={false}
        />
      </Card>
    </Space>
  );
}

export default CasePage;