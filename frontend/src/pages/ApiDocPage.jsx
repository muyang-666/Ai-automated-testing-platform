import { Card, Typography } from "antd";

const { Title, Paragraph } = Typography;

function ApiDocPage() {
  return (
    <Card title="接口文档">
      <Title level={4}>接口文档管理</Title>
      <Paragraph>后续规划功能：</Paragraph>
      <ul>
        <li>支持维护接口文档</li>
        <li>支持接口名称、请求方法、URL、请求头、请求体、响应示例</li>
        <li>后续支持根据接口文档生成接口测试用例</li>
      </ul>
    </Card>
  );
}

export default ApiDocPage;
