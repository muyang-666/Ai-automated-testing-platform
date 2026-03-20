# AI Automated Testing Platform

一个面向测试开发场景的 **AI 自动化测试平台 V1**，当前聚焦 **单接口自动化测试闭环**，支持从测试用例管理到代码生成、执行、分析、报告沉淀的完整流程。

## 项目简介

本项目的核心闭环为：

**测试用例管理**  
→ **LLM 生成 pytest 测试代码**  
→ **pytest 执行测试**  
→ **失败日志分析**  
→ **测试报告生成**

当前版本更适合作为：

- 面向测试开发场景的 AI 工具平台原型
- 单接口自动化测试平台
- AI 辅助测试代码生成与执行验证平台

## 当前功能

- 测试用例管理（支持新增、查询、编辑、删除）
- LLM 生成 pytest 测试代码
- 测试代码文件落盘与持久化保存
- pytest 动态执行测试
- 执行记录管理
- 详细日志查看
- 接口响应结果采集与展示
- AI 失败日志分析
- 测试报告生成与查询

## 技术栈

### 后端
- Python
- FastAPI
- SQLAlchemy
- SQLite
- Pydantic
- pytest
- httpx

### 前端
- React
- Vite
- Axios
- Ant Design

## 项目结构

```text
backend/   后端服务
frontend/  前端页面

