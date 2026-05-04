import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Col,
  Drawer,
  message,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import { getProjectList } from "../api/project";
import ModuleTree from "../components/ModuleTree";
import api from "../services/api";
import {
  getStoredProjectId,
  resolveProjectId,
  storeProjectId,
} from "../utils/projectSelection";

const { Paragraph, Title, Text } = Typography;

const unwrapResponse = (res) => (res?.data !== undefined ? res.data : res);

const statusColorMap = {
  passed: "success",
  failed: "error",
  error: "error",
  running: "processing",
  completed: "processing",
  pending: "default",
};

const formatDateTime = (value) => (value ? new Date(value).toLocaleString() : "-");

const renderStatusTag = (value) => {
  if (!value) return "-";
  return <Tag color={statusColorMap[value] || "default"}>{value}</Tag>;
};

function ScopeMetricCard({ title, value, suffix }) {
  return (
    <Card className="report-metric-card">
      <Statistic title={title} value={value ?? 0} suffix={suffix} />
    </Card>
  );
}

function ReportPage() {
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(getStoredProjectId);
  const [selectedModuleId, setSelectedModuleId] = useState(null);

  const [reportList, setReportList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [reportSummary, setReportSummary] = useState(null);

  const [currentReport, setCurrentReport] = useState(null);
  const [reportDrawerOpen, setReportDrawerOpen] = useState(false);

  const selectedProject = projects.find((item) => item.id === selectedProjectId);
  const scopeName = selectedModuleId
    ? `模块 #${selectedModuleId}`
    : selectedProject?.name || "当前项目";

  const fetchProjects = async () => {
    try {
      const res = await getProjectList();
      setProjects(res.data || []);
    } catch {
      message.error("获取项目列表失败");
    }
  };

  const fetchReports = async () => {
    setLoading(true);
    try {
      const res = await api.get("/reports");
      setReportList(unwrapResponse(res) || []);
    } catch (error) {
      message.error(error?.response?.data?.detail || "获取测试报告列表失败");
    } finally {
      setLoading(false);
    }
  };

  const fetchReportSummary = async () => {
    setSummaryLoading(true);
    try {
      const params = {};
      if (selectedProjectId) params.project_id = selectedProjectId;
      if (selectedModuleId != null) params.module_id = selectedModuleId;
      const res = await api.get("/reports/summary", { params });
      setReportSummary(unwrapResponse(res));
    } catch (error) {
      message.error(
        error.response?.data?.detail ||
          error.response?.data?.message ||
          error.message ||
          "获取报告统计失败"
      );
    } finally {
      setSummaryLoading(false);
    }
  };

  const handleGenerateProjectReport = async () => {
    if (!selectedProjectId) {
      message.warning("请先选择项目");
      return;
    }
    try {
      setGenerating(true);
      const params = { project_id: selectedProjectId };
      if (selectedModuleId != null) params.module_id = selectedModuleId;
      const res = await api.post("/reports/generate-project", null, { params });
      const data = unwrapResponse(res);

      message.success("测试报告生成成功");
      setCurrentReport(data);
      setReportDrawerOpen(true);
      fetchReports();
      fetchReportSummary();
    } catch (error) {
      message.error(error?.response?.data?.detail || "生成测试报告失败");
    } finally {
      setGenerating(false);
    }
  };

  const handleViewReport = async (reportId) => {
    try {
      const res = await api.get(`/reports/${reportId}`);
      setCurrentReport(unwrapResponse(res));
      setReportDrawerOpen(true);
    } catch (error) {
      message.error(error?.response?.data?.detail || "获取报告详情失败");
    }
  };

  useEffect(() => {
    fetchProjects();
    fetchReports();
  }, []);

  useEffect(() => {
    if (projects.length > 0) {
      const nextProjectId = resolveProjectId(projects, selectedProjectId);
      if (nextProjectId !== selectedProjectId) {
        setSelectedProjectId(nextProjectId);
        storeProjectId(nextProjectId);
      }
    }
  }, [projects, selectedProjectId]);

  useEffect(() => {
    if (selectedProjectId) {
      fetchReportSummary();
    }
  }, [selectedProjectId, selectedModuleId]);

  const handleProjectChange = (value) => {
    setSelectedProjectId(value);
    storeProjectId(value);
    setSelectedModuleId(null);
  };

  const overview = reportSummary?.overview || {};
  const functionTest = reportSummary?.function_test || {};
  const apiTest = reportSummary?.api_test || {};
  const sceneChain = reportSummary?.scene_chain || {};

  const reportColumns = [
    { title: "报告ID", dataIndex: "id", width: 90 },
    { title: "报告名称", dataIndex: "report_name", ellipsis: true },
    {
      title: "类型",
      dataIndex: "report_type",
      width: 160,
      render: (value) => <Tag>{value}</Tag>,
    },
    { title: "总步骤", dataIndex: "total_count", width: 90 },
    { title: "通过", dataIndex: "passed_count", width: 80 },
    { title: "失败", dataIndex: "failed_count", width: 80 },
    {
      title: "通过率",
      dataIndex: "pass_rate",
      width: 90,
      render: (value) => `${value}%`,
    },
    {
      title: "操作",
      width: 120,
      render: (_, record) => (
        <Button className="standard-action-btn" onClick={() => handleViewReport(record.id)}>
          查看报告
        </Button>
      ),
    },
  ];

  const recentApiRunColumns = [
    { title: "执行ID", dataIndex: "id", width: 90 },
    { title: "用例ID", dataIndex: "case_id", width: 90 },
    { title: "状态", dataIndex: "status", width: 100, render: renderStatusTag },
    { title: "结果", dataIndex: "result", width: 100, render: renderStatusTag },
    {
      title: "响应码",
      dataIndex: "response_status_code",
      width: 100,
      render: (value) => value ?? "-",
    },
    { title: "创建时间", dataIndex: "created_at", width: 180, render: formatDateTime },
  ];

  const recentSceneRunColumns = [
    { title: "执行ID", dataIndex: "id", width: 90 },
    { title: "场景ID", dataIndex: "scene_id", width: 90 },
    { title: "状态", dataIndex: "status", width: 100, render: renderStatusTag },
    { title: "总步骤", dataIndex: "total_steps", width: 90 },
    { title: "通过", dataIndex: "passed_steps", width: 80 },
    { title: "失败", dataIndex: "failed_steps", width: 80 },
    { title: "跳过", dataIndex: "skipped_steps", width: 80 },
    {
      title: "耗时(ms)",
      dataIndex: "duration_ms",
      width: 100,
      render: (value) => value ?? "-",
    },
    { title: "创建时间", dataIndex: "created_at", width: 180, render: formatDateTime },
  ];

  return (
    <div className="standard-page report-page">
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Card className="standard-toolbar-card">
          <Row justify="space-between" align="middle">
            <Col>
              <Space>
                <span className="standard-project-label">项目：</span>
                <Select
                  placeholder="请选择项目"
                  value={selectedProjectId}
                  onChange={handleProjectChange}
                  options={projects.map((p) => ({ label: p.name, value: p.id }))}
                  style={{ width: 240 }}
                  popupClassName="standard-select-dropdown"
                />
                <Tag>{scopeName}</Tag>
              </Space>
            </Col>
            <Col>
              <Space className="report-toolbar-scope">
                <Text strong>当前统计范围</Text>
                <Tag>{scopeName}</Tag>
                <Button
                  className="report-generate-secondary"
                  loading={generating}
                  onClick={handleGenerateProjectReport}
                >
                  生成该范围报告
                </Button>
              </Space>
            </Col>
          </Row>
        </Card>

        <div className="standard-layout">
          <div className="standard-module-shell">
            <ModuleTree
              projectId={selectedProjectId}
              selectedModuleId={selectedModuleId}
              onSelect={setSelectedModuleId}
              showCreateButton={false}
            />
          </div>

          <div className="standard-list-panel">
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={8}>
                <Card className="report-ring-card" loading={summaryLoading}>
                  <Progress
                    type="circle"
                    percent={functionTest.pass_rate ?? 0}
                    strokeColor="#111"
                    trailColor="#e5e5e5"
                    format={(percent) => `${percent}%`}
                  />
                  <div>
                    <Title level={4}>功能测试通过率</Title>
                    <Text>功能用例 {overview.function_case_count ?? 0} / 需求数 {overview.requirement_count ?? 0}</Text>
                  </div>
                </Card>
              </Col>
              <Col xs={24} lg={8}>
                <Card className="report-ring-card" loading={summaryLoading}>
                  <Progress
                    type="circle"
                    percent={apiTest.pass_rate ?? 0}
                    strokeColor="#111"
                    trailColor="#e5e5e5"
                    format={(percent) => `${percent}%`}
                  />
                  <div>
                    <Title level={4}>接口执行通过率</Title>
                    <Text>接口用例 {overview.api_case_count ?? 0} / 模块数 {overview.module_count ?? 0}</Text>
                  </div>
                </Card>
              </Col>
              <Col xs={24} lg={8}>
                <Card className="report-ring-card" loading={summaryLoading}>
                  <Progress
                    type="circle"
                    percent={sceneChain.pass_rate ?? 0}
                    strokeColor="#111"
                    trailColor="#e5e5e5"
                    format={(percent) => `${percent}%`}
                  />
                  <div>
                    <Title level={4}>串联执行通过率</Title>
                    <Text>通过 {sceneChain.passed_runs ?? 0} / 总计 {sceneChain.total_runs ?? 0}</Text>
                  </div>
                </Card>
              </Col>
            </Row>

            <Row gutter={[16, 16]} className="report-metric-grid">
              <Col xs={12} md={8} xl={4}><ScopeMetricCard title="模块数" value={overview.module_count} /></Col>
              <Col xs={12} md={8} xl={4}><ScopeMetricCard title="接口用例" value={overview.api_case_count} /></Col>
              <Col xs={12} md={8} xl={4}><ScopeMetricCard title="功能用例" value={overview.function_case_count} /></Col>
              <Col xs={12} md={8} xl={4}><ScopeMetricCard title="需求数" value={overview.requirement_count} /></Col>
              <Col xs={12} md={8} xl={4}><ScopeMetricCard title="场景数" value={overview.scene_count} /></Col>
              <Col xs={12} md={8} xl={4}><ScopeMetricCard title="报告数" value={reportList.length} /></Col>
            </Row>

            <Card title="测试报告列表" className="standard-list-card report-section-card">
              <Table
                rowKey="id"
                columns={reportColumns}
                dataSource={reportList}
                loading={loading}
                pagination={{ pageSize: 6 }}
                scroll={{ x: 900 }}
              />
            </Card>

            <Card title="最近接口执行记录" className="standard-list-card report-section-card">
              <Table
                rowKey="id"
                columns={recentApiRunColumns}
                dataSource={reportSummary?.recent_api_runs || []}
                loading={summaryLoading}
                pagination={false}
                scroll={{ x: 760 }}
              />
            </Card>

            <Card title="最近真实串联场景执行记录" className="standard-list-card report-section-card">
              <Table
                rowKey="id"
                columns={recentSceneRunColumns}
                dataSource={reportSummary?.recent_scene_runs || []}
                loading={summaryLoading}
                pagination={false}
                scroll={{ x: 900 }}
              />
            </Card>
          </div>
        </div>

        <Drawer
          title="测试报告详情"
          placement="right"
          width="50vw"
          rootClassName="standard-drawer report-detail-drawer"
          open={reportDrawerOpen}
          onClose={() => {
            setReportDrawerOpen(false);
            setCurrentReport(null);
          }}
          footer={null}
          destroyOnClose
        >
          {currentReport ? (
            <Space direction="vertical" size={16} style={{ width: "100%" }}>
              <Title level={4} style={{ margin: 0 }}>
                {currentReport.report_name}
              </Title>

              <Space wrap>
                <Tag>{currentReport.report_type}</Tag>
                <Text>总步骤：{currentReport.total_count}</Text>
                <Text>通过：{currentReport.passed_count}</Text>
                <Text>失败：{currentReport.failed_count}</Text>
                <Text>通过率：{currentReport.pass_rate}%</Text>
              </Space>

              <Card size="small" title="风险总结">
                <Paragraph>{currentReport.risk_summary || "暂无风险总结"}</Paragraph>
              </Card>

              <Card size="small" title="报告正文">
                <Paragraph copyable={{ text: currentReport.summary || "" }}>
                  <pre className="report-detail-pre">
                    {currentReport.summary || "暂无报告内容"}
                  </pre>
                </Paragraph>
              </Card>
            </Space>
          ) : (
            <p>当前无报告内容</p>
          )}
        </Drawer>
      </Space>
    </div>
  );
}

export default ReportPage;
