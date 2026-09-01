from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, UniqueConstraint, func

from app.core.database import Base


class UserProjectPermission(Base):
    __tablename__ = "user_project_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", name="uq_user_project_permission"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="用户ID")
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True, comment="项目ID")
    can_operate = Column(Boolean, default=True, nullable=False, comment="是否允许操作项目")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
