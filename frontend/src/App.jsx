import { Layout, Menu } from "antd";
import { useState } from "react";
import CasePage from "./pages/CasePage";
import RunPage from "./pages/RunPage";
import ReportPage from "./pages/ReportPage";

const { Header, Content } = Layout;

function App() {
  const [current, setCurrent] = useState("cases");

  const renderPage = () => {
    if (current === "cases") return <CasePage />;
    if (current === "runs") return <RunPage />;
    if (current === "reports") return <ReportPage />;
    return <CasePage />;
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[current]}
          onClick={(e) => setCurrent(e.key)}
          items={[
            { key: "cases", label: "用例管理" },
            { key: "runs", label: "测试执行" },
            { key: "reports", label: "测试报告" },
          ]}
        />
      </Header>
      <Content style={{ padding: "24px", background: "#f5f5f5" }}>
        {renderPage()}
      </Content>
    </Layout>
  );
}

export default App;