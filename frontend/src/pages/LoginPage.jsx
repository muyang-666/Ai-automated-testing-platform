import { useState } from "react";
import { Button, Card, Form, Input, message, Space, Typography } from "antd";
import { login } from "../api/auth";

const { Paragraph, Title, Text } = Typography;

export default function LoginPage({ onLogin }) {
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (values) => {
    setLoading(true);
    try {
      const res = await login(values);
      const data = res.data;
      localStorage.setItem("auth_token", data.token);
      localStorage.setItem("auth_user", JSON.stringify(data.user));
      message.success("登录成功");
      onLogin(data.user);
    } catch (error) {
      message.error(
        error?.response?.data?.detail ||
          error?.response?.data?.message ||
          error.message ||
          "登录失败"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#f5f7fb",
        padding: 24,
      }}
    >
      <Card style={{ width: 420 }}>
        <Space direction="vertical" size={20} style={{ width: "100%" }}>
          <div>
            <Title level={3} style={{ marginBottom: 8 }}>
              AI 测试管理平台
            </Title>
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              请登录后继续使用系统
            </Paragraph>
          </div>

          <Form
            layout="vertical"
            initialValues={{ username: "admin", password: "123456" }}
            onFinish={handleSubmit}
          >
            <Form.Item
              name="username"
              label="用户名"
              rules={[{ required: true, message: "请输入用户名" }]}
            >
              <Input placeholder="请输入用户名" autoComplete="username" />
            </Form.Item>

            <Form.Item
              name="password"
              label="密码"
              rules={[{ required: true, message: "请输入密码" }]}
            >
              <Input.Password placeholder="请输入密码" autoComplete="current-password" />
            </Form.Item>

            <Button type="primary" htmlType="submit" loading={loading} block>
              登录
            </Button>
          </Form>

          <Text type="secondary">默认账号：admin / 123456</Text>
        </Space>
      </Card>
    </div>
  );
}
