# services/llm_service.py
import requests
# from backed.config.settings import MODEL_NAME  # 可删除，直接用.env的配置
import os
from dotenv import load_dotenv

from backed.config.settings import settings

class LLMService:
    def __init__(self):
        # 读取火山方舟配置（严格匹配示例）
        self.api_key = settings.LLM_API_KEY
        self.base_url = settings.LLM_BASE_URL
        self.model_name = settings.LLM_MODEL
        self.timeout = 30

        # 校验必填配置
        if not self.api_key:
            raise ValueError("请在.env文件中配置DAPI_KEY！")
        if not self.model_name:
            raise ValueError("请在.env文件中配置MODEL_NAME！")

    def chat(self, messages):
        """
        调用火山方舟 豆包 API（完全匹配官方示例）
        """
        try:
            # 构造请求体（和官方示例完全一致）
            payload = {
                "model": self.model_name,  # 示例中的模型名
                "messages": messages,      # 对话列表（格式兼容）
                "temperature": 0.7,
                "max_tokens": 2000
            }

            # 请求头（和官方示例一致：Bearer + Key）
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            # 调用火山方舟 API（禁用SSL验证，避免国内环境证书问题）
            response = requests.post(
                url=self.base_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=False  # 新增：解决国内环境SSL证书问题
            )

            # 校验响应
            response.raise_for_status()
            result = response.json()

            # 提取回复（格式和OpenAI兼容）
            return result["choices"][0]["message"]["content"].strip()

        except requests.exceptions.Timeout:
            return "抱歉，请求超时了，请稍后再试～"
        except requests.exceptions.RequestException as e:
            return f"抱歉，调用豆包失败：{str(e)[:60]}，请稍后再试～"
        except KeyError as e:
            return f"抱歉，返回格式异常：{str(e)}，请稍后再试～"
        except Exception as e:
            return f"抱歉，未知错误：{str(e)[:60]}，请稍后再试～"