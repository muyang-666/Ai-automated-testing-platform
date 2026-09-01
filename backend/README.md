# AI Test Assistant Backend

## 启动方式

```bash
pip install -r requirements.txt
python scripts/seed_demo_data.py
uvicorn app.main:app --reload --port 8001
```

默认数据库为 MySQL：`mysql+pymysql://root:123456@127.0.0.1:3306/ai_test_assistant?charset=utf8mb4`。
如本机账号密码不同，请在 `.env` 中覆盖 `DATABASE_URL`。
