"""本机部署入口：演示库持久化隔离，停止标记触发 Uvicorn 优雅关闭。"""
import argparse
import asyncio
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# 演示环境复用正式路由与 Worker，仅替换数据库和模型来源。
def demo_app(database_path: Path, worker_count: int = 1, shutdown_timeout: int = 3):
    from alembic import command
    from alembic.config import Config
    from backend.app.database.engine import create_database_engine

    database_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config(str(ROOT / 'backend' / 'alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'backend' / 'migrations'))
    config.set_main_option('sqlalchemy.url', 'sqlite:///' + database_path.as_posix())
    command.upgrade(config, 'head')
    with patch.dict('os.environ', {
        'DEEPSEEK_API_KEY': 'local-demo-no-provider',
        'GEO_DATABASE_URL': 'sqlite+aiosqlite:///' + database_path.as_posix(),
    }), patch('dotenv.load_dotenv'):
        import backend.app.api.routes as api
        import backend.app.main as main
        import backend.app.database.session as db
        import backend.app.services.worker as worker

    engine = create_database_engine('sqlite+aiosqlite:///' + database_path.as_posix())
    main.engine = db.engine = worker.engine = engine
    main.get_worker_count = lambda: worker_count
    main.get_shutdown_timeout = lambda: shutdown_timeout

    async def model(question, client):
        from backend.app.services.providers import ProviderAnswer
        await asyncio.sleep(2)
        return ProviderAnswer(
            answer=f'## 本机演示回答\n\n这是一段固定规则生成的模拟内容，没有调用真实模型。\n\n你的问题是：{question}',
            provider='mock', model='local-demo',
        )

    worker.query_deepseek = api.query_deepseek = model
    main.app.state.runtime_mode = 'demo'
    return main.app


# 用 Uvicorn 的退出标记停止服务，等待 lifespan 清理 Worker 和连接。
async def serve(app, port: int, stop_file: Path):
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='info'))

    async def watch_stop():
        while not server.should_exit:
            if stop_file.exists():
                server.should_exit = True
                return
            await asyncio.sleep(0.2)

    watcher = asyncio.create_task(watch_stop())
    try:
        await server.serve()
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['demo', 'live'], default='demo')
    parser.add_argument('--port', type=int, default=8014)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    args.runtime.mkdir(parents=True, exist_ok=True)
    if args.mode == 'demo':
        app = demo_app(args.runtime / 'demo.db')
    else:
        from backend.app.main import app
    asyncio.run(serve(app, args.port, args.runtime / 'stop.request'))
