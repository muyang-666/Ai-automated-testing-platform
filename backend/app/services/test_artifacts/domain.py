"""TestArtifact 领域常量（Service 层事实源，models/schemas 引用以免 magic string 漂移）。"""

from app.models.test_artifact.artifact_node import (  # noqa: F401
    NODE_TYPE_ROOT,
    NODE_TYPE_GROUP,
    NODE_TYPE_TEST_POINT,
    NODE_TYPE_TEST_CASE,
)
from app.models.test_artifact.artifact_operation import (  # noqa: F401
    OP_ADD_NODE,
    OP_UPDATE_NODE,
    OP_DELETE_NODE,
    OP_MOVE_NODE,
    OP_RESTORE,
)
from app.models.test_artifact.artifact_revision import (  # noqa: F401
    ACTOR_TYPE_USER,
    ACTOR_TYPE_AGENT,
    ACTOR_TYPE_SYSTEM,
)
from app.models.test_artifact.test_artifact import (  # noqa: F401
    ARTIFACT_TYPE_TEST_DESIGN,
    ARTIFACT_STATUS_ACTIVE,
    ARTIFACT_STATUS_ARCHIVED,
)

# 客户端可对 update_node 提交的受控字段白名单（§17：服务端控制字段必须拒绝/忽略）
WRITABLE_NODE_FIELDS = ("title", "content", "source_refs")

# 服务端控制字段：客户端 update patch 一律拒绝
SERVER_CONTROLLED_FIELDS = (
    "id",
    "artifact_id",
    "owner_user_id",
    "created_revision",
    "deleted_revision",
    "created_by",
    "node_type",
    "parent_id",
    "order_key",
    "current_revision",
    "project_id",
    "root_node_id",
    "status",
)

# 根创建 revision_no
ROOT_REVISION_NO = 1
