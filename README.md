# GEO · 品牌 AI 可见性监测

GEO 是一个面向品牌运营的可见性监测平台。用户可以维护品牌资料与监测问题，通过模型服务或网页采集获取回答，并在工作台查看回答记录、任务进度和品牌提及分析。

## 项目流程

```text
维护品牌与监测问题
        ↓
提交问答采集任务
        ↓
后台 Worker 调用模型 API 或 Playwright 浏览器
        ↓
保存回答与来源信息，分析品牌及别名提及
        ↓
工作台查看回答、任务和统计
```

品牌、问题、回答和任务按用户隔离。Job 记录采集状态及输入快照；Worker 在后台执行任务，并通过租约和心跳管理执行状态。回答保存在 SQLite，Redis 用于统计缓存。

## 技术架构

- 前端：React、TypeScript、Vite
- 后端：FastAPI、FastAPI Users、SQLAlchemy Async ORM
- 数据：SQLite、Alembic、Redis
- 采集：HTTP API、Playwright
- 部署：Nginx、Docker Compose

浏览器访问前端后，Nginx 提供静态页面并将 `/api` 请求转发到 FastAPI。FastAPI 处理身份验证与业务请求，将采集任务交给后台 Worker；Worker 选择 API 或浏览器渠道，完成后将回答和分析结果写入数据库。

## 代码结构

```text
backend/app/api/       HTTP 路由
backend/app/core/      认证、日志、限流和通用配置
backend/app/database/  ORM 模型、数据库引擎与 Session
backend/app/services/  Provider、Worker、缓存和业务服务
backend/migrations/    Alembic 数据库迁移
frontend/src/          工作台、登录页面和 API 客户端
docker/                Dockerfile、Compose 与 Nginx 配置
licenses/              第三方许可证文本
```

第三方来源说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
