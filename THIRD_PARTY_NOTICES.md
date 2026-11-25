# 第三方来源

部分前端组件、CSS 和登录背景图改编自用户提供的本地项目，来源和内容摘要记录在 frontend/source-manifest.json。公司 Logo 与 favicon 已从当前前端移除。登录组件和样式为适配版本，认证请求改接 FastAPI Users，未复制短信、验证码或 Cookie 会话后端。

FastAPI、FastAPI Users、SQLAlchemy、Alembic、HTTPX、Redis 客户端、React、Vite、Lucide 等依赖由其各自许可证约束。依赖版本见 requirements.txt 和 frontend/package-lock.json，Docker 镜像来自各自上游。

`backend/app/core/rate_limits.py` 的 Redis 固定窗口 Lua 算法参考并改写自 [long2ice/fastapi-limiter v0.1.6](https://github.com/long2ice/fastapi-limiter/tree/v0.1.6)，Copyright 2020 long2ice，Apache License 2.0。改动包括使用 EVAL、补足异常 TTL 的处理，以及应用实例内的配置与有界回退计数；没有直接安装该依赖或复用其默认转发头识别逻辑。许可证全文保存在 [licenses/fastapi-limiter-Apache-2.0.txt](licenses/fastapi-limiter-Apache-2.0.txt)。

本仓库暂未声明整体开源许可证；公开可见不等于授予未声明的使用许可。

浏览器采集适配参考用户本机旧 GEO 的 `browser.py`，Playwright 固定版本为 1.58.0。合成页面夹具和浏览器检查不包含在本公开仓库中；它们不含真实豆包网页源码、登录资料或采集回答。Playwright 为安装依赖，不将其实现源码拷入应用目录。
