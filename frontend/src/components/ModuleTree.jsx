import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Dropdown,
  Form,
  Input,
  message,
  Modal,
  Spin,
  Tree,
} from "antd";
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  UpOutlined,
  DownOutlined,
  MoreOutlined,
} from "@ant-design/icons";
import {
  createModule,
  deleteModule,
  getModuleTree,
  reorderModules,
  updateModule,
} from "../api/module";

function getErrorMessage(error) {
  return (
    error?.response?.data?.detail ||
    error?.response?.data?.message ||
    error?.message ||
    "操作失败"
  );
}

function transformToTreeData(modules, flatMap) {
  return modules.map((m) => {
    flatMap[String(m.id)] = m;
    return {
      key: String(m.id),
      title: m.name,
      children: m.children?.length
        ? transformToTreeData(m.children, flatMap)
        : [],
      data: m,
    };
  });
}

export default function ModuleTree({
  projectId,
  selectedModuleId,
  onSelect,
  onChange,
}) {
  const [treeData, setTreeData] = useState([]);
  const [flatMap, setFlatMap] = useState({});
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState("create");
  const [editingModule, setEditingModule] = useState(null);
  const [targetParentId, setTargetParentId] = useState(null);
  const [expandedKeys, setExpandedKeys] = useState([]);
  const [form] = Form.useForm();

  const loadTree = useCallback(async () => {
    if (!projectId) {
      setTreeData([]);
      setFlatMap({});
      return;
    }
    setLoading(true);
    try {
      const res = await getModuleTree(projectId);
      const map = {};
      const tree = transformToTreeData(res.data || [], map);
      setTreeData(tree);
      setFlatMap(map);
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadTree();
  }, [loadTree]);

  const closeModal = () => {
    setModalOpen(false);
    setEditingModule(null);
    setTargetParentId(null);
    form.resetFields();
  };

  const openCreateModal = (parentId) => {
    setModalMode("create");
    setEditingModule(null);
    setTargetParentId(parentId);
    form.resetFields();
    setModalOpen(true);
  };

  const openEditModal = (module) => {
    setModalMode("edit");
    setEditingModule(module);
    setTargetParentId(null);
    form.setFieldsValue({
      name: module.name,
      description: module.description,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (modalMode === "create") {
        await createModule({
          project_id: projectId,
          parent_id: targetParentId,
          name: values.name,
          description: values.description || null,
        });
        message.success("模块创建成功");
        if (targetParentId) {
          setExpandedKeys((prev) => {
            const key = String(targetParentId);
            return prev.includes(key) ? prev : [...prev, key];
          });
        }
      } else {
        await updateModule(editingModule.id, {
          name: values.name,
          description: values.description || null,
        });
        message.success("模块更新成功");
      }
      closeModal();
      loadTree();
      onChange?.();
    } catch (error) {
      if (error?.response) {
        message.error(getErrorMessage(error));
      }
    }
  };

  const handleDelete = (module) => {
    Modal.confirm({
      title: "确认删除该模块吗？",
      content: `模块「${module.name}」将被删除，此操作不可恢复。`,
      okText: "确认删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await deleteModule(module.id);
          message.success("模块删除成功");
          loadTree();
          onChange?.();
        } catch (error) {
          message.error(getErrorMessage(error));
        }
      },
    });
  };

  const handleMove = async (moduleId, direction) => {
    const mod = flatMap[String(moduleId)];
    if (!mod) return;

    const siblings = Object.values(flatMap)
      .filter((m) => m.parent_id === mod.parent_id)
      .sort((a, b) => a.sort_order - b.sort_order);

    const idx = siblings.findIndex((m) => m.id === moduleId);
    const newIdx = idx + (direction === "up" ? -1 : 1);
    if (newIdx < 0 || newIdx >= siblings.length) return;

    [siblings[idx], siblings[newIdx]] = [siblings[newIdx], siblings[idx]];

    try {
      await reorderModules({
        parent_id: mod.parent_id,
        ordered_module_ids: siblings.map((m) => m.id),
      });
      message.success("排序调整成功");
      loadTree();
      onChange?.();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const getActionItems = (nodeData) => {
    const mod = nodeData.data;
    const siblings = Object.values(flatMap)
      .filter((m) => m.parent_id === mod.parent_id)
      .sort((a, b) => a.sort_order - b.sort_order);
    const idx = siblings.findIndex((m) => m.id === mod.id);

    return [
      {
        key: "addChild",
        icon: <PlusOutlined />,
        label: "新增子模块",
        onClick: ({ domEvent }) => {
          domEvent.stopPropagation();
          openCreateModal(mod.id);
        },
      },
      {
        key: "edit",
        icon: <EditOutlined />,
        label: "编辑",
        onClick: ({ domEvent }) => {
          domEvent.stopPropagation();
          openEditModal(mod);
        },
      },
      { type: "divider" },
      {
        key: "moveUp",
        icon: <UpOutlined />,
        label: "上移",
        disabled: idx === 0,
        onClick: ({ domEvent }) => {
          domEvent.stopPropagation();
          handleMove(mod.id, "up");
        },
      },
      {
        key: "moveDown",
        icon: <DownOutlined />,
        label: "下移",
        disabled: idx === siblings.length - 1,
        onClick: ({ domEvent }) => {
          domEvent.stopPropagation();
          handleMove(mod.id, "down");
        },
      },
      { type: "divider" },
      {
        key: "delete",
        icon: <DeleteOutlined />,
        label: "删除",
        danger: true,
        onClick: ({ domEvent }) => {
          domEvent.stopPropagation();
          handleDelete(mod);
        },
      },
    ];
  };

  const titleRender = (nodeData) => {
    const isSelected =
      selectedModuleId != null &&
      String(selectedModuleId) === nodeData.key;

    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          width: "100%",
        }}
      >
        <span
          style={{
            color: isSelected ? "#1677ff" : undefined,
            fontWeight: isSelected ? 500 : undefined,
          }}
          title={nodeData.data?.description || nodeData.title}
        >
          {nodeData.title}
        </span>
        <Dropdown
          menu={{ items: getActionItems(nodeData) }}
          trigger={["click"]}
        >
          <Button
            size="small"
            type="text"
            icon={<MoreOutlined />}
            onClick={(e) => e.stopPropagation()}
          />
        </Dropdown>
      </div>
    );
  };

  const handleTreeSelect = (keys) => {
    if (keys.length === 0) return;
    const key = keys[0];
    const mod = flatMap[key];
    onSelect?.(Number(key), mod);
  };

  if (!projectId) {
    return (
      <div
        style={{
          padding: 24,
          textAlign: "center",
          color: "#999",
          border: "1px dashed #d9d9d9",
          borderRadius: 8,
        }}
      >
        请先选择项目
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <Button
          type="primary"
          size="small"
          icon={<PlusOutlined />}
          onClick={() => openCreateModal(null)}
          block
        >
          新增一级模块
        </Button>
      </div>

      <Spin spinning={loading}>
        {treeData.length === 0 ? (
          <div
            style={{
              padding: 24,
              textAlign: "center",
              color: "#999",
            }}
          >
            暂无模块，请新增
          </div>
        ) : (
          <Tree
            treeData={treeData}
            titleRender={titleRender}
            selectedKeys={
              selectedModuleId != null ? [String(selectedModuleId)] : []
            }
            onSelect={handleTreeSelect}
            expandedKeys={expandedKeys}
            onExpand={(keys) => setExpandedKeys(keys)}
            blockNode
          />
        )}
      </Spin>

      <Modal
        title={
          modalMode === "create"
            ? targetParentId
              ? "新增子模块"
              : "新增一级模块"
            : "编辑模块"
        }
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={closeModal}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="模块名称"
            rules={[{ required: true, message: "请输入模块名称" }]}
          >
            <Input placeholder="请输入模块名称" maxLength={100} />
          </Form.Item>

          <Form.Item name="description" label="模块描述">
            <Input.TextArea rows={3} placeholder="请输入模块描述" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
