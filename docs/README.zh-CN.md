# EduPilot

面向留学咨询的对话式智能体：**从零实现的** Python 编排（不使用 LangChain / LangGraph）。包含 agent 循环、工具分发、基于 SQLite 的记忆与检查点、对话压缩、提示组装，以及可选的 MCP 路由。

**English:** [README.md](../README.md)

## 环境要求

- Python 3.11+
- OpenAI 兼容 API 密钥（例如 DeepSeek）

## 安装

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate      # macOS / Linux

pip install -r requirements.txt
copy .env.example .env           # 编辑 .env  
```

## 运行

**网页界面 + API**（在仓库根目录）：

```bash
uvicorn src.backend.api:app --reload --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000`；项目使用FastAPI,接口文档在运行时自动生成。

**命令行 agent 循环**（可选）：

```bash
python -m src.backend.loop
```

## 测试

```bash
pytest tests/ -v
```



