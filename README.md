# AI Automated Testing Platform

一个面向测试开发场景的 **AI 自动化测试平台 V1**，当前聚焦 **单接口自动化测试闭环**，支持从测试用例管理到代码生成、执行、分析、报告沉淀的完整流程。

## 项目简介

本项目的核心闭环为：

**测试用例管理**  
→ **规则生成 pytest 测试代码**  
→ **pytest 执行测试**  
→ **失败日志分析**  
→ **测试报告生成**

当前版本更适合作为：

- 面向测试开发场景的 AI 工具平台原型
- 单接口自动化测试平台
- 规则生成测试代码与执行验证平台

## 当前功能

- 测试用例管理（支持新增、查询、编辑、删除）
- 规则生成 pytest 测试代码
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
- MySQL
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
```

## 本地启动

后端默认使用 MySQL：

```text
mysql+pymysql://root:123456@127.0.0.1:3306/ai_test_assistant?charset=utf8mb4
```

如本机 MySQL 密码不同，复制 `backend/.env.example` 为 `backend/.env` 后修改 `DATABASE_URL`。

```bash
cd backend
pip install -r requirements.txt
python scripts/seed_demo_data.py
uvicorn app.main:app --reload --port 8001
```

答辩时可以再开一个同代码后端作为“被测系统”：

```bash
cd backend
uvicorn app.main:app --reload --port 8002
```

如果要让演示用例打到第二套后端，先设置 `DEMO_TARGET_BASE_URL=http://127.0.0.1:8002` 再执行 `python scripts/seed_demo_data.py`。

