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


## 提示词与 skills

较长的 LLM 说明放在 `src/backend/skills/` 下的 **Markdown skill** 里：每个子目录一个 `SKILL.md`，可选 YAML 头（`name`、`description`）。运行时由 `src/backend/skills/loader.py` 扫描并缓存，`load_skill("<name>")` 返回正文。

**已进入主系统提示**（`src/backend/prompt.py` 的 `assemble_prompt`，经 `src/backend/state.py` 拉取）：

| Skill `name`（frontmatter） | 用途 |
|------------------------------|------|
| `base-role` | 核心角色与安全约束（每轮系统提示都有）。 |
| `route-intake`、`route-school-match`、`route-visa-advisory`、`route-timeline`、`route-general-qa` | **当前模式**段落，对应路由（如 `school_match` → `route-school-match`）。未匹配路由时回退到 `route-general-qa`。 |

**仍在代码里拼接**（不是整篇 skill 文档）：已知学生信息、顾问笔记、历史会话摘要等区块的标题与列表格式，便于注入实时数据。

**同目录下其它 skill**（通过 `src/backend/memory.py` 的 `get_extraction_prompt()`、`get_summarization_prompt()` 读取）：`extraction`、`summarization`。把实体抽取或摘要类提示放在 Markdown 里，由调用方选用，避免在业务代码里堆长字符串。
