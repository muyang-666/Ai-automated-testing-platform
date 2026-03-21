import { useEffect, useState } from "react";
import {
  Button,
  Card,
  message,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import api from "../services/api";

const { Paragraph, Title, Text } = Typography;

const unwrapResponse = (res) => {
  return res?.data !== undefined ? res.data : res;
};

function ReportPage() {
  const [reportList, setReportList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

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

  const handleGenerateProjectReport = async () => {
    try {
      setGenerating(true);
      const res = await api.post("/reports/generate-project");
      const data = unwrapResponse(res);

      message.success("项目级测试报告生成成功");
      setCurrentReport(data);
      setReportModalOpen(true);
      fetchReports();
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
  }, []);

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

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
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