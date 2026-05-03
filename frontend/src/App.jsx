import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Layout, Menu, Space, Spin, Typography } from "antd";
import { getCurrentUser, logout } from "./api/auth";
import CasePage from "./pages/CasePage";
import FunctionCasePage from "./pages/FunctionCasePage";
import LoginPage from "./pages/LoginPage";
import ProjectPage from "./pages/ProjectPage";
import RequirementPage from "./pages/RequirementPage";
import RunPage from "./pages/RunPage";
import ReportPage from "./pages/ReportPage";
import ParameterPage from "./pages/ParameterPage";
import ScenePage from "./pages/ScenePage";
import UserPage from "./pages/UserPage";

const { Header, Content } = Layout;
const { Text } = Typography;

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
      { key: "cases", label: "用例管理" },
      { key: "functionCases", label: "功能用例" },
      { key: "projects", label: "项目管理" },
      { key: "requirements", label: "需求管理" },
      { key: "runs", label: "执行管理" },
      { key: "scenes", label: "场景管理" },
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
      // 本地退出优先，后端 session 已失效或网络异常时也回到登录页。
    } finally {
      handleAuthLost();
    }
  };

  const handleMenuClick = (e) => {
    if (e.key === "users" && !isAdmin) {
      setCurrentPage("cases");
      return;
    }
    setCurrentPage(e.key);
  };

  const renderPage = () => {
    if (currentPage === "cases") return <CasePage />;
    if (currentPage === "functionCases") return <FunctionCasePage />;
    if (currentPage === "projects") return <ProjectPage />;
    if (currentPage === "requirements") return <RequirementPage />;
    if (currentPage === "runs") return <RunPage />;
    if (currentPage === "reports") return <ReportPage />;
    if (currentPage === "params") return <ParameterPage />;
    if (currentPage === "scenes") return <ScenePage />;
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
      <Header style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[currentPage]}
          onClick={handleMenuClick}
          items={menuItems}
          style={{ flex: 1, minWidth: 0 }}
        />

        <Space>
          <Text style={{ color: "rgba(255, 255, 255, 0.88)" }}>
            {currentUser.display_name || currentUser.username}
          </Text>
          <Button size="small" onClick={handleLogout}>
            退出
          </Button>
        </Space>
      </Header>

      <Content style={{ padding: 24 }}>{renderPage()}</Content>
    </Layout>
  );
}
