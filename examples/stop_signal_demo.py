import asyncio


# 等待外部发出停止信号，不访问数据库或模型。
async def demo_worker(stop_event: asyncio.Event) -> None:
    print("3. Worker 开始运行，信号状态：", stop_event.is_set())
    await stop_event.wait()
    print("6. Worker 收到停止信号，信号状态：", stop_event.is_set())


# 创建信号和后台任务，一秒后通知任务结束。
async def main() -> None:
    stop_event = asyncio.Event()
    print("1. main 创建停止信号，信号状态：", stop_event.is_set())

    worker_task = asyncio.create_task(demo_worker(stop_event))
    print("2. main 安排好 Worker，接下来等待一秒")
    await asyncio.sleep(1)

    stop_event.set()
    print("4. main 设置信号，信号状态：", stop_event.is_set())
    print("5. main 等待 Worker 结束")
    await worker_task
    print("7. main 确认 Worker 已结束")


if __name__ == "__main__":
    asyncio.run(main())
