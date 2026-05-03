import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Layout, Menu, Space, Spin, Typography } from "antd";
import { getCurrentUser, logout } from "./api/auth";
import ApiDocPage from "./pages/ApiDocPage";
import CasePage from "./pages/CasePage";
import FunctionCasePage from "./pages/FunctionCasePage";
import LoginPage from "./pages/LoginPage";
import ModelConfigPage from "./pages/ModelConfigPage";
import ProjectPage from "./pages/ProjectPage";
import RequirementPage from "./pages/RequirementPage";
import ReportPage from "./pages/ReportPage";
import ParameterPage from "./pages/ParameterPage";
import ScenePage from "./pages/ScenePage";
import UserPage from "./pages/UserPage";

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const PAGE_KEYS = [
  "cases",
  "functionCases",
  "projects",
  "requirements",
  "scenes",
  "reports",
  "params",
  "apiDocs",
  "modelConfig",
  "users",
];

const clearStoredAuth = () => {
  localStorage.removeItem("auth_token");
  localStorage.removeItem("auth_user");
};

export default function App() {
  const [currentPage, setCurrentPage] = useState("cases");
  const [currentUser, setCurrentUser] = useState(null);
  const [authChecking, setAuthChecking] = useState(true);

  const isAdmin = currentUser?.roles?.includes("admin");

  const handleAuthLost = useCallback(() => {
    clearStoredAuth();
    setCurrentUser(null);
    setCurrentPage("cases");
  }, []);

  useEffect(() => {
    const validateLogin = async () => {
      const token = localStorage.getItem("auth_token");
      if (!token) {
        setAuthChecking(false);
        return;
      }

      try {
        const res = await getCurrentUser();
        setCurrentUser(res.data);
        localStorage.setItem("auth_user", JSON.stringify(res.data));
      } catch {
        handleAuthLost();
      } finally {
        setAuthChecking(false);
      }
    };

    window.addEventListener("auth:unauthorized", handleAuthLost);
    validateLogin();
    return () => window.removeEventListener("auth:unauthorized", handleAuthLost);
  }, [handleAuthLost]);

  const menuItems = useMemo(() => {
    const items = [
      { key: "projects", label: "项目管理" },
      { key: "modelConfig", label: "模型管理" },
      {
        key: "function-cases-group",
        label: "功能用例管理",
        children: [
          { key: "requirements", label: "需求管理" },
          { key: "functionCases", label: "功能用例" },
        ],
      },
      {
        key: "api-cases-group",
        label: "接口用例管理",
        children: [
          { key: "apiDocs", label: "接口文档" },
          { key: "cases", label: "接口用例" },
          { key: "scenes", label: "场景管理" },
        ],
      },
      { key: "reports", label: "报告管理" },
      { key: "params", label: "参数管理" },
    ];
    if (isAdmin) {
      items.push({ key: "users", label: "用户管理" });
    }
    return items;
  }, [isAdmin]);

  const handleLogin = (user) => {
    setCurrentUser(user);
    setCurrentPage("cases");
  };

  const handleLogout = async () => {
    try {
      await logout();
    } catch {
      // 本地退出优先
    } finally {
      handleAuthLost();
    }
  };

  const handleMenuClick = (e) => {
    if (PAGE_KEYS.includes(e.key)) {
      setCurrentPage(e.key);
    }
  };

  const renderPage = () => {
    if (currentPage === "cases") return <CasePage />;
    if (currentPage === "functionCases") return <FunctionCasePage />;
    if (currentPage === "projects") return <ProjectPage />;
    if (currentPage === "requirements") return <RequirementPage />;
    if (currentPage === "reports") return <ReportPage />;
    if (currentPage === "params") return <ParameterPage />;
    if (currentPage === "scenes") return <ScenePage />;
    if (currentPage === "apiDocs") return <ApiDocPage />;
    if (currentPage === "modelConfig") return <ModelConfigPage />;
    if (currentPage === "users" && isAdmin) return <UserPage />;
    return <CasePage />;
  };

  if (authChecking) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Spin />
      </div>
    );
  }

  if (!currentUser) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider width={220} style={{ background: "#001529" }}>
        <div
          style={{
            height: 64,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Text
            style={{
              color: "#fff",
              fontSize: 18,
              fontWeight: "bold",
              letterSpacing: 1,
            }}
          >
            TestMind
          </Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[currentPage]}
          defaultOpenKeys={["function-cases-group", "api-cases-group"]}
          onClick={handleMenuClick}
          items={menuItems}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: "#fff",
            padding: "0 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-end",
          }}
        >
          <Space>
            <Text>{currentUser.display_name || currentUser.username}</Text>
            <Button size="small" onClick={handleLogout}>
              退出
            </Button>
          </Space>
        </Header>
        <Content style={{ padding: 24 }}>{renderPage()}</Content>
      </Layout>
    </Layout>
  );
}
