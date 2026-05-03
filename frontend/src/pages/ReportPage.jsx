import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Col,
  message,
  Modal,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import api from "../services/api";

const { Paragraph, Title, Text } = Typography;

const unwrapResponse = (res) => {
  return res?.data !== undefined ? res.data : res;
};

const statusColorMap = {
  passed: "green",
  failed: "red",
  error: "red",
  running: "blue",
  completed: "blue",
  pending: "default",
};

const formatDateTime = (value) => {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString();
};

const renderStatusTag = (value) => {
  if (!value) {
    return "-";
  }
  return <Tag color={statusColorMap[value] || "default"}>{value}</Tag>;
};

function ReportPage() {
  const [reportList, setReportList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [reportSummary, setReportSummary] = useState(null);

  const [currentReport, setCurrentReport] = useState(null);
  const [reportModalOpen, setReportModalOpen] = useState(false);

  const fetchReports = async () => {
    setLoading(true);
    try {
      const res = await api.get("/reports");
      const data = unwrapResponse(res);
      setReportList(data || []);
    } catch (error) {
      message.error(error?.response?.data?.detail || "获取测试报告列表失败");
    } finally {
      setLoading(false);
    }
  };

  const fetchReportSummary = async () => {
    setSummaryLoading(true);
    try {
      const res = await api.get("/reports/summary");
      const data = unwrapResponse(res);
      setReportSummary(data);
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
    try {
      setGenerating(true);
      const res = await api.post("/reports/generate-project");
      const data = unwrapResponse(res);

      message.success("项目级测试报告生成成功");
      setCurrentReport(data);
      setReportModalOpen(true);
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
      const data = unwrapResponse(res);
      setCurrentReport(data);
      setReportModalOpen(true);
    } catch (error) {
      message.error(error?.response?.data?.detail || "获取报告详情失败");
    }
  };

  useEffect(() => {
    fetchReports();
    fetchReportSummary();
  }, []);

  const overview = reportSummary?.overview || {};
  const apiTest = reportSummary?.api_test || {};
  const sceneChain = reportSummary?.scene_chain || {};

  const columns = [
    {
      title: "报告ID",
      dataIndex: "id",
      width: 100,
    },
    {
      title: "报告名称",
      dataIndex: "report_name",
    },
    {
      title: "报告类型",
      dataIndex: "report_type",
      width: 180,
      render: (value) => <Tag color="blue">{value}</Tag>,
    },
    {
      title: "总步骤数",
      dataIndex: "total_count",
      width: 100,
    },
    {
      title: "通过",
      dataIndex: "passed_count",
      width: 80,
    },
    {
      title: "失败",
      dataIndex: "failed_count",
      width: 80,
    },
    {
      title: "通过率",
      dataIndex: "pass_rate",
      width: 100,
      render: (value) => `${value}%`,
    },
    {
      title: "操作",
      width: 120,
      render: (_, record) => (
        <Button type="primary" onClick={() => handleViewReport(record.id)}>
          查看报告
        </Button>
      ),
    },
  ];

  const recentApiRunColumns = [
    {
      title: "执行ID",
      dataIndex: "id",
      width: 90,
    },
    {
      title: "用例ID",
      dataIndex: "case_id",
      width: 90,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 110,
      render: renderStatusTag,
    },
    {
      title: "结果",
      dataIndex: "result",
      width: 110,
      render: renderStatusTag,
    },
    {
      title: "响应状态码",
      dataIndex: "response_status_code",
      width: 120,
      render: (value) => value ?? "-",
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 200,
      render: formatDateTime,
    },
  ];

  const recentSceneRunColumns = [
    {
      title: "执行ID",
      dataIndex: "id",
      width: 90,
    },
    {
      title: "场景ID",
      dataIndex: "scene_id",
      width: 90,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 110,
      render: renderStatusTag,
    },
    {
      title: "总步骤",
      dataIndex: "total_steps",
      width: 90,
    },
    {
      title: "通过",
      dataIndex: "passed_steps",
      width: 80,
    },
    {
      title: "失败",
      dataIndex: "failed_steps",
      width: 80,
    },
    {
      title: "跳过",
      dataIndex: "skipped_steps",
      width: 80,
    },
    {
      title: "耗时(ms)",
      dataIndex: "duration_ms",
      width: 100,
      render: (value) => value ?? "-",
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 200,
      render: formatDateTime,
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card loading={summaryLoading}>
            <Statistic title="项目数" value={overview.project_count ?? 0} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card loading={summaryLoading}>
            <Statistic title="接口用例数" value={overview.api_case_count ?? 0} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card loading={summaryLoading}>
            <Statistic title="功能用例数" value={overview.function_case_count ?? 0} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card loading={summaryLoading}>
            <Statistic title="需求数" value={overview.requirement_count ?? 0} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card loading={summaryLoading}>
            <Statistic title="场景数" value={overview.scene_count ?? 0} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card loading={summaryLoading}>
            <Statistic
              title="接口测试通过率"
              value={apiTest.pass_rate ?? 0}
              precision={2}
              suffix="%"
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card loading={summaryLoading}>
            <Statistic
              title="串联执行通过率"
              value={sceneChain.pass_rate ?? 0}
              precision={2}
              suffix="%"
            />
          </Card>
        </Col>
      </Row>

      <Card title="最近接口测试执行记录">
        <Table
          rowKey="id"
          columns={recentApiRunColumns}
          dataSource={reportSummary?.recent_api_runs || []}
          loading={summaryLoading}
          pagination={false}
        />
      </Card>

      <Card title="最近真实串联场景执行记录">
        <Table
          rowKey="id"
          columns={recentSceneRunColumns}
          dataSource={reportSummary?.recent_scene_runs || []}
          loading={summaryLoading}
          pagination={false}
          scroll={{ x: 900 }}
        />
      </Card>

      <Card title="测试报告管理">
        <Space style={{ width: "100%", justifyContent: "space-between" }}>
          <Text>
            点击下方按钮后，系统会自动执行场景管理中的全部场景，并基于执行结果生成项目级接口测试报告。
          </Text>
          <Button
            type="primary"
            loading={generating}
            onClick={handleGenerateProjectReport}
          >
            一键生成测试报告
          </Button>
        </Space>
      </Card>

      <Card title="测试报告列表">
        <Table
          rowKey="id"
          columns={columns}
          dataSource={reportList}
          loading={loading}
          pagination={{ pageSize: 5 }}
        />
      </Card>

      <Modal
        title="测试报告详情"
        open={reportModalOpen}
        onCancel={() => {
          setReportModalOpen(false);
          setCurrentReport(null);
        }}
        footer={null}
        width={1000}
      >
        {currentReport ? (
          <Space direction="vertical" size={16} style={{ width: "100%" }}>
            <Title level={4} style={{ margin: 0 }}>
              {currentReport.report_name}
            </Title>

            <Space wrap>
              <Text>报告类型：{currentReport.report_type}</Text>
              <Text>总步骤数：{currentReport.total_count}</Text>
              <Text>通过：{currentReport.passed_count}</Text>
              <Text>失败：{currentReport.failed_count}</Text>
              <Text>通过率：{currentReport.pass_rate}%</Text>
            </Space>

            <Card size="small" title="风险总结">
              <Paragraph>{currentReport.risk_summary || "暂无风险总结"}</Paragraph>
            </Card>

            <Card size="small" title="报告正文">
              <Paragraph copyable={{ text: currentReport.summary || "" }}>
                <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                  {currentReport.summary || "暂无报告内容"}
                </pre>
              </Paragraph>
            </Card>
          </Space>
        ) : (
          <p>当前无报告内容</p>
        )}
      </Modal>
    </Space>
  );
}

export default ReportPage;
