import { Layout, Menu } from "antd";
import { useState } from "react";
import CasePage from "./pages/CasePage";
import RunPage from "./pages/RunPage";
import ReportPage from "./pages/ReportPage";
import ParameterPage from "./pages/ParameterPage";

const { Header, Content } = Layout;

export default function App() {
  const [currentPage, setCurrentPage] = useState("cases");

  const renderPage = () => {
    if (currentPage === "cases") return <CasePage />;
    if (currentPage === "runs") return <RunPage />;
    if (currentPage === "reports") return <ReportPage />;
    if (currentPage === "params") return <ParameterPage />;
    return <CasePage />;
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[currentPage]}
          onClick={(e) => setCurrentPage(e.key)}
          items={[
            { key: "cases", label: "测试用例管理" },
            { key: "runs", label: "执行管理" },
            { key: "reports", label: "报告管理" },
            { key: "params", label: "参数管理" },
          ]}
        />
      </Header>

      <Content style={{ padding: 24 }}>
        {renderPage()}
      </Content>
    </Layout>
  );
}