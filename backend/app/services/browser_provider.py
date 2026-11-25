"""豆包网页采集：独立用户资料目录、单次提交、明确完成标记。"""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import re
from time import monotonic
from urllib.parse import urlsplit, parse_qs

from filelock import FileLock, Timeout as LockTimeout

from backend.app.services.providers import ProviderAnswer

DOUBAO_URL = "https://www.doubao.com/chat/"
INPUT = '[data-testid="chat_input_input"] [contenteditable="true"]'
RECEIVE = '[data-testid="receive_message"]'
TEXT = '[data-testid="message_text_content"]'


class BrowserCollectionError(RuntimeError):
    """可显示给任务用户的浏览器渠道错误，不含页面原文或Cookie。"""


@dataclass(frozen=True)
class BrowserSettings:
    enabled: bool
    channel: str
    headless: bool
    timeout: int
    profile_root: Path


# profile只能由后端配置与用户编号确定，HTTP请求不能提交路径或任意网址。
def settings() -> BrowserSettings:
    try:
        timeout = int(os.getenv("GEO_BROWSER_TIMEOUT", "120"))
    except ValueError:
        raise BrowserCollectionError("浏览器配置无效：timeout必须是10到300之间的整数") from None
    value = BrowserSettings(
        enabled=os.getenv("GEO_BROWSER_ENABLED", "false").lower() in {"true", "1"},
        channel=os.getenv("GEO_BROWSER_CHANNEL", "msedge" if os.name == "nt" else "chromium"),
        headless=os.getenv("GEO_BROWSER_HEADLESS", "true").lower() in {"true", "1"},
        timeout=timeout,
        profile_root=Path(os.getenv("GEO_BROWSER_PROFILE_ROOT", str(
            Path(os.getenv("GEO_DATA_DIR", str(Path(__file__).resolve().parents[3] / ".data"))) / "browser-profiles"))),
    )
    if value.channel not in {"chromium", "msedge", "chrome"} or not 10 <= value.timeout <= 300:
        raise BrowserCollectionError("浏览器配置无效：channel或timeout超出支持范围")
    return value


# 与登录助手共享非阻塞文件锁，不同Worker/进程不能同时使用同一用户的profile。
@asynccontextmanager
async def browser_context(user_id: int, *, headless: bool | None = None):
    from playwright.async_api import async_playwright, Error as PlaywrightError
    config = settings()
    if not config.enabled:
        raise BrowserCollectionError("浏览器采集未启用，请配置 GEO_BROWSER_ENABLED=true 后重启")
    if user_id <= 0:
        raise BrowserCollectionError("浏览器采集缺少有效用户")
    profile = config.profile_root.resolve() / f"user-{user_id}" / "doubao"
    profile.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(profile.parent / "doubao.lock"))
    try:
        lock.acquire(timeout=0)
    except LockTimeout:
        raise BrowserCollectionError("该用户的豆包浏览器正在使用，请关闭登录助手或等待当前采集结束后手动重试") from None
    try:
        async with async_playwright() as playwright:
            try:
                context = await playwright.chromium.launch_persistent_context(
                    str(profile), headless=config.headless if headless is None else headless,
                    viewport={"width":1360,"height":900}, locale="zh-CN", accept_downloads=False,
                    timeout=30000, **({"channel":config.channel} if config.channel != "chromium" else {}),
                )
            except PlaywrightError:
                raise BrowserCollectionError("浏览器无法启动，请检查安装、资料目录占用和浏览器渠道配置") from None
            try:
                context.set_default_timeout(10000)
                yield context
            finally:
                try:
                    await context.close()
                except PlaywrightError:
                    pass  # 登录助手由用户关闭浏览器时上下文可能已经断开。
    finally:
        lock.release()


# 只识别阻塞登录、人工验证与发送失败，普通访客登录按钮不算阻塞。
async def check_intervention(page):
    if parse_qs(urlsplit(page.url).query).get("from_logout") == ["1"]:
        raise BrowserCollectionError("豆包会话已退出，请重新运行登录助手检查")
    for item in await page.locator('iframe[src*="captcha"], [id*="captcha"], [class*="captcha-verify"]').all():
        if await item.is_visible():
            raise BrowserCollectionError("豆包要求验证码，请在登录助手中人工处理后手动重试")
    for dialog in await page.locator('[role="dialog"], [role="alertdialog"]').all():
        if await dialog.is_visible():
            text = await dialog.inner_text()
            if re.search("验证码|安全验证|滑块|验证身份", text):
                raise BrowserCollectionError("豆包要求人工验证，请运行登录助手处理后手动重试")
            if re.search("登录|手机号|扫码", text):
                raise BrowserCollectionError("豆包要求登录，请运行对应用户的登录助手")
    if await page.locator('input[type="tel"]:visible').count():
        raise BrowserCollectionError("豆包要求登录，请运行对应用户的登录助手")
    if await page.get_by_test_id("message_box_failed_icon").count():
        raise BrowserCollectionError("豆包显示发送失败，问题可能已发送，请检查网站后手动重试")


# 每次先清空到新对话，绝不把已有历史回答当成本次采集结果。
async def prepare_chat(page, url):
    from playwright.async_api import TimeoutError as PlaywrightTimeout
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except PlaywrightTimeout:
        pass
    await check_intervention(page)
    await page.locator(INPUT).wait_for(state="visible", timeout=20000)
    if not await page.get_by_test_id("flow_chat_guidance_page").is_visible():
        await page.get_by_test_id("create_conversation_button").click()
        await page.get_by_test_id("flow_chat_guidance_page").wait_for(state="visible")
    if await page.locator(RECEIVE).count():
        raise BrowserCollectionError("无法确认空白新对话，尚未发送问题，请检查豆包页面适配")
    if (urlsplit(page.url).scheme,urlsplit(page.url).netloc) != (urlsplit(url).scheme,urlsplit(url).netloc):
        raise BrowserCollectionError("页面跳转到其他站点，已停止采集")


# 只发送一次，核对用户消息和助手块，要求显式结束标记加两秒稳定。
async def ask_page(page, question: str, url: str = DOUBAO_URL) -> str:
    await prepare_chat(page, url)
    await page.locator(INPUT).fill(question)
    await page.get_by_test_id("chat_input_send_button").click()
    sent = page.locator('[data-testid="send_message"] [data-testid="message_text_content"]')
    deadline = monotonic() + 15
    while True:
        await check_intervention(page)
        if await sent.count() == 1 and (await sent.inner_text()).strip() == question.strip():
            break
        if monotonic() >= deadline:
            raise BrowserCollectionError("网页未确认本次问题，提交结果未知，请检查后手动重试")
        await asyncio.sleep(.2)
    previous, stable_since = "", monotonic()
    while True:
        await check_intervention(page)
        replies = page.locator(RECEIVE)
        if await replies.count() > 1:
            raise BrowserCollectionError("出现多条回答，无法确定本次结果，已停止采集")
        if await replies.count() == 1:
            blocks = replies.first.locator(TEXT)
            text = "\n\n".join(t.strip() for t in await blocks.all_inner_texts() if t.strip())
            if len(text)>30000:
                raise BrowserCollectionError("网页回答超过30000字符限制")
            if text != previous:
                previous, stable_since = text, monotonic()
            complete = await blocks.count() > 0 and await blocks.evaluate_all(
                "els=>els.every(e=>e.getAttribute('data-streaming')==='false')")
            if complete and text and monotonic()-stable_since>=2:
                if await sent.count()!=1 or (await sent.inner_text()).strip()!=question.strip():
                    raise BrowserCollectionError("网页问题与任务不一致，拒绝保存回答")
                return text
        await asyncio.sleep(.3)


# 真实渠道入口始终使用固定站点；URL注入仅在测试中调用内部ask_page。
async def query_doubao(question: str, user_id: int) -> ProviderAnswer:
    from playwright.async_api import Error as PlaywrightError
    try:
        async with browser_context(user_id) as context:
            page = context.pages[0] if context.pages else await context.new_page()
            async with asyncio.timeout(settings().timeout):
                answer = await ask_page(page, question)
            return ProviderAnswer(answer, "browser:doubao", None)
    except (TimeoutError, PlaywrightError):
        raise BrowserCollectionError("豆包浏览器操作超时或失败，问题可能已发送，请检查登录、网络和页面适配后手动重试") from None


# 用户在独立可见浏览器自行登录；不读取日常浏览器，也不接收密码。
async def login_helper(user_id: int):
    async with browser_context(user_id, headless=False) as context:
        closed = asyncio.Event()
        context.on("close", lambda _: closed.set())
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(DOUBAO_URL, wait_until="domcontentloaded")
        print("请自行完成登录/验证，完成后关闭整个助手浏览器。", flush=True)
        await closed.wait()


if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--login-user", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(login_helper(args.login_user))
