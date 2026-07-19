# 技术栈与开源协议声明（Attribution & Licenses）

> 本文件置于项目提交材料的显著位置，用于满足评审「使用开源 / AI 工具须标注名称、来源、协议」的要求。

## 1. 引言

本项目为 **KnowSubtle 个性化学习智能体系统**：后端基于 **FastAPI**，前端为**单文件 SPA**，桌面端使用 **PyQt6** 实现；AI 能力通过 **OpenAI 兼容 API** 由用户自备模型（自备 API Key）提供，本项目本身不绑定、不内置任何特定模型权重。

## 2. 使用的开源项目 / 框架 / 工具

| 名称 | 用途 | 来源 / 仓库 | 开源协议 | 备注 |
| --- | --- | --- | --- | --- |
| Python 3.11 | 运行环境 | https://www.python.org | PSF License | 项目开发与运行所基于的解释器版本 |
| FastAPI | Web 框架 / API | https://github.com/fastapi/fastapi | MIT | 提供后端 REST / 流式接口 |
| Uvicorn | ASGI 服务器 | https://github.com/encode/uvicorn | BSD-3-Clause | 运行 FastAPI 应用的异步服务器 |
| SQLAlchemy | ORM / 数据库 | https://www.sqlalchemy.org | MIT | 学习数据持久化与模型映射 |
| aiosqlite | 异步 SQLite 驱动 | https://github.com/omnilib/aiosqlite | MIT | 配合 SQLAlchemy 的异步数据库访问 |
| httpx | 异步 HTTP 客户端（调用 LLM） | https://github.com/encode/httpx | BSD-3-Clause | 向后端 LLM / OpenAI 兼容接口发起请求 |
| Pydantic | 数据校验 | https://github.com/pydantic/pydantic | MIT | 请求 / 响应模型与配置校验 |
| PyQt6 / PyQtWebEngine | 桌面端 GUI 与内嵌浏览器 | https://www.riverbankcomputing.com | **GPL v3 或 Riverbank 商业许可** | **重要**：若以闭源方式分发桌面程序，须向 Riverbank 购买商业许可 |
| OpenAI 兼容 API（模型由用户自备 Key） | LLM 能力 | 取决于用户所选供应商 | 协议取决于所选模型供应商 | 本项目仅做协议兼容代理，不绑定特定模型 / 不内置权重 |
| 前端：原生 HTML / CSS / JavaScript 单文件 SPA | 界面 | 自研，无第三方前端库 | 自研（随本项目分发） | 规避 CDN 依赖与前端许可风险 |
| 内容安全：自研启发式过滤模块（`moderation.py`） | 离线内容审核 | 自研 | 自研（随本项目分发） | 基础合规兜底，生产建议叠加托管审核服务 |

## 3. 协议合规说明

- **本项目源码分发许可**：当前仓库尚未包含独立的 `LICENSE` 文件；依据 `pyproject.toml` 的声明，计划以 **MIT 许可证** 分发本项目自研源代码。正式发布时将随仓库根目录提供 `LICENSE` 文件。
- **PyQt6 的 GPL v3 条款（重点提示）**：PyQt6 / PyQtWebEngine 以 **GPL v3** 或 Riverbank 商业许可双重授权。若本项目以**开源（GPL 兼容）方式**分发，可自由使用；若用于**闭源商业分发**，需向 Riverbank Computing 购买商业许可，否则可能构成许可冲突。请在闭源分发前评估并合规处理。
- **用户自备模型 / API 的权利归属**：用户自备的模型权重或 API 服务，其知识产权与许可由用户与所选模型供应商约定，本项目不主张其任何权利，亦不对其可用性、合规性或输出内容负责。

## 4. 致谢与备注

- 本系统的智能生成能力来自用户自行配置的大语言模型；系统本身聚焦于**多智能体编排、交互界面与学习数据管理**，不对模型本身的所有权或训练数据主张权利。
- 本系统的前端与后端在 **AI 辅助编程工具** 的协助下完成开发，以提升开发效率与代码质量；最终代码与文档均由项目维护者审阅与确认。

---

*最后更新：2026-06-26*
