from typing import List
from backed.schemas.task_schema import LearningResource
from backed.config.settings import settings
from fastapi import HTTPException
from datetime import datetime
import json
from urllib import request as urlrequest

# -----------------------------
# AI 调用
# -----------------------------
def call_model_for_recommendations(
    goal_category: str,
    goal_detail: str,
    current_phase: str,
    max_results: int
) -> List[LearningResource]:

    if not settings.LLM_API_KEY or not settings.LLM_MODEL:
        raise HTTPException(status_code=400, detail="未配置 ARK_API_KEY 或 ARK_MODEL")

    # AI 请求 payload
    payload = {
        "model": settings.LLM_MODEL,
        "temperature": 0.3,
        "messages": [
            {
                "role": "system",
                "content": "你是专业学习资源推荐助手，请根据用户目标和阶段推荐2025-2026年最新内容"
            },
            {
                "role": "user",
                "content": f"推荐{max_results}个关于'{goal_detail}'的学习资源，目标类别是{goal_category}，阶段{current_phase}。类型包括网页、视频、课程、文章。"
            }
        ],
        # ======================
        # 👇 就加这一大段
        # ======================
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "output_recommendations",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "recommendations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "description": {"type": "string"},
                                        "url": {"type": "string"},
                                        "resource_type": {"type": "string"},
                                        "category": {"type": "string"},
                                        "source": {"type": "string"},
                                        "difficulty": {"type": "string"},
                                        "tags": {"type": "array", "items": {"type": "string"}},
                                        "rating": {"type": "number"}
                                    },
                                    "required": ["title", "description", "url", "resource_type"]
                                }
                            }
                        },
                        "required": ["recommendations"]
                    }
                }
            }
        ],
        "tool_choice": {
            "type": "function",
            "function": {"name": "output_recommendations"}
        }
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(
        settings.LLM_BASE_URL  + "/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.LLM_API_KEY}"
        },
        method="POST"
    )

    try:
        with urlrequest.urlopen(req, timeout=settings.LLM_TIMEOUT) as res:
            body = json.loads(res.read().decode("utf-8"))

        # 模型返回解析
        tool_call = body["choices"][0]["message"]["tool_calls"][0]
        arguments = json.loads(tool_call["function"]["arguments"])
        recommendations_data = arguments.get("recommendations", [])

        resources = []
        for rec in recommendations_data:
            resource = LearningResource(
                id=rec.get("id", f"rec_{len(resources)+1}"),
                title=rec["title"],
                description=rec["description"],
                url=rec["url"],
                resource_type=rec["resource_type"],
                category=rec["category"],
                source=rec["source"],
                publish_date=rec.get("publish_date", datetime.now().isoformat()),
                difficulty=rec.get("difficulty", "medium"),
                duration_minutes=rec.get("duration_minutes", 0),
                tags=rec.get("tags", []),
                view_count=rec.get("view_count", 0),
                rating=rec.get("rating", 0.0)
            )
            resources.append(resource)

        return resources[:max_results]

    except Exception as e:
        # AI 调用失败就返回空列表，交给 fallback 处理
        return []

# -----------------------------
# fallback 推荐
# -----------------------------
def build_fallback_recommendations(goal_category: str, goal_detail: str, max_results: int) -> List[LearningResource]:
    fallback_data = {
        "考研": [LearningResource(
            id="fallback_1",
            title="考研数学基础班",
            description="名师讲解考研数学高等数学基础知识点",
            url="https://www.bilibili.com/video/BV1xx411c7mD",
            resource_type="video",
            category="learning",
            source="B站",
            publish_date="2025-01-15"
        )],
        "考公": [LearningResource(
            id="fallback_2",
            title="行测数量关系解题技巧",
            description="公务员考试行测数量关系快速解题",
            url="https://www.bilibili.com/video/BV1xx411c7mF",
            resource_type="video",
            category="learning",
            source="B站",
            publish_date="2025-01-20"
        )],
        # 可以继续增加其它目标类别
        "default": [
            LearningResource(
                id="fallback_default",
                title=f"{goal_category}学习指南",
                description=f"帮助你学习{goal_detail}的基础入门资源",
                url="https://www.baidu.com",
                resource_type="article",
                category="learning",
                source="系统推荐",
                publish_date="2025-01-01"  
            )]
    }
    # return fallback_data.get(goal_category, [])[:max_results]
    return fallback_data.get(goal_category, fallback_data["default"])[:max_results]
# -----------------------------
# 对外统一入口
# -----------------------------
def get_recommendations_service(
    goal_category: str,
    goal_detail: str,
    current_phase: str,
    max_results: int = 10
) -> List[LearningResource]:

    # 先调用 AI
    recs = call_model_for_recommendations(goal_category, goal_detail, current_phase, max_results)

    # AI 没返回就用 fallback
    if not recs:
        recs = build_fallback_recommendations(goal_category, goal_detail, max_results)

    return recs
