"""容器入口：迁移独立数据卷中的 SQLite，再启动一个 Uvicorn 进程。"""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# 容器使用固定的数据目录，演示与真实采集分别保存数据库。
def create_app():
    mode = os.getenv('GEO_MODE', 'demo')
    if mode not in {'demo', 'live'}:
        raise ValueError('GEO_MODE must be demo or live')
    data_dir = Path(os.getenv('GEO_DATA_DIR', '/data')).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    if mode == 'demo':
        from backend.app.run_backend import demo_app
        worker_count = int(os.getenv('GEO_WORKER_COUNT', '2'))
        shutdown_timeout = int(os.getenv('GEO_WORKER_SHUTDOWN_TIMEOUT', '10'))
        if worker_count <= 0 or shutdown_timeout <= 0:
            raise ValueError('Worker count and shutdown timeout must be positive')
        return demo_app(data_dir / 'demo.db', worker_count, shutdown_timeout)

    database_path = data_dir / 'geo_learning.db'
    os.environ['GEO_DATABASE_URL'] = 'sqlite+aiosqlite:///' + database_path.as_posix()
    from alembic import command
    from alembic.config import Config
    config = Config(str(ROOT / 'backend' / 'alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'backend' / 'migrations'))
    config.set_main_option('sqlalchemy.url', 'sqlite:///' + database_path.as_posix())
    command.upgrade(config, 'head')
    from backend.app.main import app
    return app


if __name__ == '__main__':
    import uvicorn
    app = create_app()
    uvicorn.run(app, host='0.0.0.0', port=8000, workers=1,
                proxy_headers=False, timeout_graceful_shutdown=20)
