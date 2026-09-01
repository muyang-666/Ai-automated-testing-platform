import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Drawer,
  Empty,
  Form,
  Input,
  message,
  Popconfirm,
  Select,
  Spin,
  Tag,
} from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import {
  createProject,
  deleteProject,
  getProjectList,
  getProjectSummary,
  updateProject,
} from "../api/project";
import { getStoredCurrentUser, isAdminUser } from "../utils/authPermissions";

const STATUS_OPTIONS = [
  { label: "全部", value: "" },
  { label: "启用", value: "active" },
  { label: "归档", value: "archived" },
  { label: "停用", value: "disabled" },
];

const STATUS_TAG_MAP = {
  active: { className: "project-status-active", label: "启用" },
  archived: { className: "project-status-archived", label: "归档" },
  disabled: { className: "project-status-disabled", label: "停用" },
};

const toSummaryProject = (project) => ({
  ...project,
  api_case_count: project.api_case_count || 0,
  function_case_count: project.function_case_count || 0,
  requirement_count: project.requirement_count || 0,
  scene_count: project.scene_count || 0,
});

const formatDateTime = (value) => (value ? new Date(value).toLocaleString("zh-CN") : "-");

export default function ProjectPage() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [createDrawerOpen, setCreateDrawerOpen] = useState(false);
  const [editDrawerOpen, setEditDrawerOpen] = useState(false);
  const [editingProject, setEditingProject] = useState(null);
  const [keyword, setKeyword] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [form] = Form.useForm();
  const canManageProjects = isAdminUser(getStoredCurrentUser());

  const fetchProjects = async (searchKeyword, searchStatus) => {
    setLoading(true);
    try {
      const params = {};
      const kw = searchKeyword !== undefined ? searchKeyword : keyword;
      const st = searchStatus !== undefined ? searchStatus : statusFilter;
      if (kw) params.keyword = kw;
      if (st) params.status = st;

      try {
        const res = await getProjectSummary(params);
        setProjects((res.data || []).map(toSummaryProject));
      } catch {
        const fallbackRes = await getProjectList(params);
        setProjects((fallbackRes.data || []).map(toSummaryProject));
      }
    } catch {
      message.error("获取项目列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openCreateDrawer = () => {
    setEditingProject(null);
    form.resetFields();
    form.setFieldsValue({ status: "active" });
    setCreateDrawerOpen(true);
  };

  const openEditDrawer = (record) => {
    setEditingProject(record);
    form.setFieldsValue({
      projectName: record.name,
      projectDescription: record.description,
      status: record.status,
    });
    setEditDrawerOpen(true);
  };

  const closeCreateDrawer = () => {
    setCreateDrawerOpen(false);
    setEditingProject(null);
    form.resetFields();
  };

  const closeEditDrawer = () => {
    setEditDrawerOpen(false);
    setEditingProject(null);
    form.resetFields();
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        name: values.projectName,
        description: values.projectDescription,
        status: values.status,
      };
      setSubmitting(true);

      if (editingProject) {
        await updateProject(editingProject.id, payload);
        message.success("项目更新成功");
        closeEditDrawer();
      } else {
        await createProject(payload);
        message.success("项目创建成功");
        closeCreateDrawer();
      }

      fetchProjects();
    } catch (error) {
      if (error?.response) {
        message.error(error?.response?.data?.detail || "保存失败");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (projectId) => {
    try {
      await deleteProject(projectId);
      message.success("项目删除成功");
      fetchProjects();
    } catch {
      message.error("项目删除失败");
    }
  };

  const handleSearch = (value) => {
    setKeyword(value);
    fetchProjects(value, statusFilter);
  };

  const handleStatusChange = (value) => {
    setStatusFilter(value);
    fetchProjects(keyword, value);
  };

  const renderProjectCard = (project) => {
    const tag = STATUS_TAG_MAP[project.status] || {
      className: "project-status-disabled",
      label: project.status,
    };

    return (
      <Card key={project.id} className="project-card" bordered>
        <div className="project-card-top">
          <span className="project-card-id">ID #{project.id}</span>
          <Tag className={`project-status-tag ${tag.className}`}>{tag.label}</Tag>
        </div>

        <h2 className="project-card-title">{project.name}</h2>
        <p className="project-card-description">{project.description || "暂无项目描述"}</p>

        <div className="project-stat-grid">
          <div className="project-stat-item">
            <span>{project.function_case_count}</span>
            <label>功能用例</label>
          </div>
          <div className="project-stat-item">
            <span>{project.api_case_count}</span>
            <label>接口用例</label>
          </div>
          <div className="project-stat-item">
            <span>{project.requirement_count}</span>
            <label>需求</label>
          </div>
          <div className="project-stat-item">
            <span>{project.scene_count}</span>
            <label>场景</label>
          </div>
        </div>

        <div className="project-card-meta">
          <div>
            <span>创建时间</span>
            <strong>{formatDateTime(project.created_at)}</strong>
          </div>
          <div>
            <span>更新时间</span>
            <strong>{formatDateTime(project.updated_at)}</strong>
          </div>
        </div>

        {canManageProjects && (
          <div className="project-card-actions">
            <Button icon={<EditOutlined />} onClick={() => openEditDrawer(project)}>
              编辑
            </Button>
            <Popconfirm
              title="确认删除该项目吗？"
              okText="确认"
              cancelText="取消"
              okButtonProps={{ className: "project-popconfirm-ok-button" }}
              onConfirm={() => handleDelete(project.id)}
            >
              <Button className="project-delete-button" icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          </div>
        )}
      </Card>
    );
  };

  return (
    <div className="project-page">
      <div className="project-page-header">
        <div>
          <h1>项目管理</h1>
          <p>按项目查看基础信息、用例资产和场景统计</p>
        </div>
      </div>

      <div className="project-toolbar">
        <div className="project-toolbar-filters">
          <Input.Search
            placeholder="搜索项目名称"
            allowClear
            autoComplete="new-password"
            name="project_search_keyword"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onSearch={handleSearch}
          />
          <Select
            placeholder="状态筛选"
            options={STATUS_OPTIONS}
            value={statusFilter}
            onChange={handleStatusChange}
            popupClassName="project-select-dropdown"
          />
        </div>
        {canManageProjects && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateDrawer}>
            新增项目
          </Button>
        )}
      </div>

      <Spin spinning={loading}>
        {projects.length > 0 ? (
          <div className="project-card-grid">{projects.map(renderProjectCard)}</div>
        ) : (
          <div className="project-empty">
            <Empty description="暂无项目" />
          </div>
        )}
      </Spin>

      <Drawer
        title="新增项目"
        placement="right"
        width="50vw"
        rootClassName="project-drawer"
        open={createDrawerOpen}
        onClose={closeCreateDrawer}
        destroyOnClose
        footer={
          <div className="project-edit-drawer-footer">
            <Button onClick={closeCreateDrawer} disabled={submitting}>
              取消
            </Button>
            <Button
              type="primary"
              className="project-modal-ok-button"
              onClick={handleSubmit}
              loading={submitting}
            >
              保存
            </Button>
          </div>
        }
      >
        <Form form={form} layout="vertical" autoComplete="off">
          <Form.Item
            name="projectName"
            label="项目名称"
            rules={[{ required: true, message: "请输入项目名称" }]}
          >
            <Input
              placeholder="请输入项目名称"
              maxLength={100}
              autoComplete="new-password"
              name="project_form_title_create"
            />
          </Form.Item>

          <Form.Item name="projectDescription" label="项目描述">
            <Input.TextArea
              rows={3}
              placeholder="请输入项目描述"
              autoComplete="new-password"
              name="project_form_detail_create"
            />
          </Form.Item>

          <Form.Item name="status" label="项目状态">
            <Select
              popupClassName="project-select-dropdown"
              options={[
                { label: "启用", value: "active" },
                { label: "归档", value: "archived" },
                { label: "停用", value: "disabled" },
              ]}
            />
          </Form.Item>
        </Form>
      </Drawer>

      <Drawer
        title="编辑项目"
        placement="right"
        width="50vw"
        rootClassName="project-drawer"
        open={editDrawerOpen}
        onClose={closeEditDrawer}
        destroyOnClose
        footer={
          <div className="project-edit-drawer-footer">
            <Button onClick={closeEditDrawer} disabled={submitting}>
              取消
            </Button>
            <Button
              type="primary"
              className="project-modal-ok-button"
              onClick={handleSubmit}
              loading={submitting}
            >
              保存
            </Button>
          </div>
        }
      >
        <Form form={form} layout="vertical" autoComplete="off">
          <Form.Item
            name="projectName"
            label="项目名称"
            rules={[{ required: true, message: "请输入项目名称" }]}
          >
            <Input
              placeholder="请输入项目名称"
              maxLength={100}
              autoComplete="new-password"
              name="project_form_title_edit"
            />
          </Form.Item>

          <Form.Item name="projectDescription" label="项目描述">
            <Input.TextArea
              rows={3}
              placeholder="请输入项目描述"
              autoComplete="new-password"
              name="project_form_detail_edit"
            />
          </Form.Item>

          <Form.Item name="status" label="项目状态">
            <Select
              popupClassName="project-select-dropdown"
              options={[
                { label: "启用", value: "active" },
                { label: "归档", value: "archived" },
                { label: "停用", value: "disabled" },
              ]}
            />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
