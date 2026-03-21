import { useEffect, useState } from "react";
import {
  Button,
  Card,
  InputNumber,
  message,
  Popconfirm,
  Select,
  Space,
  Table,
  Typography,
} from "antd";
import { createSceneStep, deleteSceneStep, getCaseList, getSceneSteps } from "../api/scene";

const { Title } = Typography;

export default function SceneStepPage({ scene, onBack }) {
  const [steps, setSteps] = useState([]);
  const [caseOptions, setCaseOptions] = useState([]);
  const [loading, setLoading] = useState(false);

  const [selectedCaseId, setSelectedCaseId] = useState(undefined);
  const [stepOrder, setStepOrder] = useState(1);

  const loadSteps = async () => {
    try {
      setLoading(true);
      const res = await getSceneSteps(scene.id);
      setSteps(res.data || []);
    } catch (error) {
      message.error("读取场景步骤失败");
    } finally {
      setLoading(false);
    }
  };

  const loadCases = async () => {
    try {
      const res = await getCaseList();
      const list = res.data || [];
      setCaseOptions(list);
    } catch (error) {
      message.error("读取测试用例列表失败");
    }
  };

  useEffect(() => {
    if (scene?.id) {
      loadSteps();
      loadCases();
    }
  }, [scene?.id]);

  const handleAddStep = async () => {
    if (!selectedCaseId) {
      message.warning("请先选择测试用例");
      return;
    }
    if (!stepOrder || stepOrder < 1) {
      message.warning("步骤顺序必须大于 0");
      return;
    }

    try {
      await createSceneStep(scene.id, {
        step_order: stepOrder,
        case_id: selectedCaseId,
      });
      message.success("新增场景步骤成功");
      setSelectedCaseId(undefined);
      setStepOrder(1);
      loadSteps();
    } catch (error) {
      message.error(error?.response?.data?.detail || "新增场景步骤失败");
    }
  };

  const handleDeleteStep = async (stepId) => {
    try {
      await deleteSceneStep(stepId);
      message.success("删除步骤成功");
      loadSteps();
    } catch (error) {
      message.error("删除步骤失败");
    }
  };

  const columns = [
    {
      title: "步骤ID",
      dataIndex: "step_order",
      key: "step_order",
      width: 100,
    },
    {
      title: "名称",
      dataIndex: "case_name",
      key: "case_name",
    },
    {
      title: "关联用例ID",
      dataIndex: "case_id",
      key: "case_id",
      width: 120,
    },
    {
      title: "URL",
      dataIndex: "case_url",
      key: "case_url",
      ellipsis: true,
    },
    {
      title: "删除",
      key: "action",
      width: 100,
      render: (_, record) => (
        <Popconfirm
          title="确定删除这个步骤吗？"
          onConfirm={() => handleDeleteStep(record.id)}
        >
          <Button danger size="small">删除</Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <Card>
      <Space direction="vertical" style={{ width: "100%" }} size={16}>
        <Space style={{ justifyContent: "space-between", width: "100%" }}>
          <Title level={4} style={{ margin: 0 }}>
            管理场景用例：{scene.name}
          </Title>
          <Button onClick={onBack}>返回场景列表</Button>
        </Space>

        <Space wrap>
          <InputNumber
            min={1}
            value={stepOrder}
            onChange={setStepOrder}
            placeholder="步骤顺序"
          />
          <Select
            style={{ width: 360 }}
            placeholder="请选择已有测试用例"
            value={selectedCaseId}
            onChange={setSelectedCaseId}
            options={caseOptions.map((item) => ({
              label: `${item.id} - ${item.name}`,
              value: item.id,
            }))}
            showSearch
            optionFilterProp="label"
          />
          <Button type="primary" onClick={handleAddStep}>
            添加到场景
          </Button>
        </Space>

        <Table
          rowKey="id"
          loading={loading}
          dataSource={steps}
          columns={columns}
          pagination={false}
        />
      </Space>
    </Card>
  );
}