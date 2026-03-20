import { useEffect, useState } from "react";
import { Button, Card, Input, message } from "antd";
import { getParameterFile, updateParameterFile } from "../api/parameterFile";

const { TextArea } = Input;

export default function ParameterPage() {
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);

  const loadFile = async () => {
    try {
      const res = await getParameterFile();
      setContent(res.data.content || "");
    } catch (error) {
      message.error("读取参数文件失败");
    }
  };

  const handleSave = async () => {
    try {
      setLoading(true);
      await updateParameterFile({ content });
      message.success("参数文件保存成功");
    } catch (error) {
      message.error(error?.response?.data?.detail || "保存失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFile();
  }, []);

  return (
    <Card title="参数文件管理">
      <TextArea
        rows={20}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="请输入 parameter.py 内容"
      />
      <Button
        type="primary"
        onClick={handleSave}
        loading={loading}
        style={{ marginTop: 16 }}
      >
        保存参数文件
      </Button>
    </Card>
  );
}