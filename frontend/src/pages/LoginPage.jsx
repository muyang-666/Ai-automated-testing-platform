import { useState } from "react";
import { Button, Card, Form, Input, message, Typography } from "antd";
import { login } from "../api/auth";

const { Title } = Typography;

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
        background: "#f5f5f5",
        padding: 24,
      }}
    >
      <Card
        style={{ width: 780 }}
        styles={{ body: { padding: 48 } }}
      >
        <div style={{ marginBottom: 40 }}>
          <Title
            level={3}
            style={{
              marginBottom: 0,
              fontSize: 28,
              fontWeight: 700,
              textAlign: "center",
              color: "#000",
            }}
          >
            基于大语言模型的测试管理平台
          </Title>
        </div>

        <Form
          layout="vertical"
          size="large"
          initialValues={{ username: "admin", password: "123456" }}
          onFinish={handleSubmit}
        >
          <Form.Item
            name="username"
            label={<span style={{ fontWeight: 600, fontSize: 15 }}>用户名</span>}
            rules={[{ required: true, message: "请输入用户名" }]}
          >
            <Input
              placeholder="请输入用户名"
              autoComplete="username"
              style={{ background: "#f2f2f2", height: 48 }}
            />
          </Form.Item>

          <Form.Item
            name="password"
            label={<span style={{ fontWeight: 600, fontSize: 15 }}>密码</span>}
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password
              placeholder="请输入密码"
              autoComplete="current-password"
              style={{ background: "#f2f2f2", height: 48 }}
            />
          </Form.Item>

          <Form.Item style={{ marginTop: 32 }}>
            <Button
              htmlType="submit"
              loading={loading}
              block
              size="large"
              style={{
                height: 48,
                background: "#000",
                borderColor: "#000",
                color: "#fff",
                fontWeight: 600,
                fontSize: 16,
              }}
            >
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
