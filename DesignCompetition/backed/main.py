from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html

from backed.config.settings import settings
from backed.api.task_routes import router as task_router
from backed.api.chat_api import router as chat_router
from backed.api.auth_api import router as auth_router
from backed.core.websocket_manager import manager
from backed.core.scheduler import start_scheduler

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    docs_url=None,  # 关闭默认
    redoc_url=None
)

# 关键：手动指定国内CDN，解决空白问题
@app.get("/docs/", include_in_schema=False)
async def custom_docs():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="API Docs",
        swagger_js_url="https://cdn.bootcdn.net/ajax/libs/swagger-ui/5.9.0/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.bootcdn.net/ajax/libs/swagger-ui/5.9.0/swagger-ui.css",
    )
# 强制跨域配置（测试用，消除所有跨域干扰）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# @app.on_event("startup")
# async def print_routes():
#     for r in app.routes:
#         print(r.path, r.methods)

# 启动定时任务
start_scheduler()
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        manager.disconnect(user_id)

app.include_router(task_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(auth_router, prefix="/api") # 前缀 /api 生效

# 健康检查（验证后端是否存活）
@app.get("/health")
def health_check():
    return {"status": "ok"}



# if __name__ == "__main__":
#     # 可选：从.env读取端口，保留默认8000
#     port = int(os.getenv("API_PORT", 8000))
#     uvicorn.run(
#         "main:app",
#         host="0.0.0.0",
#         port=port,  # 适配.env的API_PORT，无则用8000
#         reload=settings.DEBUG  # 复用settings.DEBUG，和你原有逻辑一致
#     )


