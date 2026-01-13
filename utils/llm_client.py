"""
LLM客户端
=========
调用大模型API
"""

import os
import json
from typing import Dict, Any, Optional

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class LLMClient:
    """LLM客户端"""
    
    def __init__(self, 
                 api_key: str = None,
                 base_url: str = None,
                 model: str = None):
        """
        初始化
        
        Args:
            api_key: API密钥，默认从环境变量LLM_API_KEY读取
            base_url: API地址，默认从环境变量LLM_BASE_URL读取
            model: 模型名称，默认从环境变量LLM_MODEL读取
        """
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "")
        self.model = model or os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B")
        
        self.client = None
        if HAS_OPENAI and self.api_key and self.base_url:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
    
    def is_available(self) -> bool:
        """检查LLM是否可用"""
        return self.client is not None
    
    def call(self, prompt: str, model: str = None) -> str:
        """
        调用LLM
        
        Args:
            prompt: 提示词
            model: 模型名称（可选）
        
        Returns:
            模型输出文本
        """
        if not self.client:
            raise RuntimeError("LLM客户端未配置，请设置环境变量LLM_API_KEY和LLM_BASE_URL")
        
        resp = self.client.chat.completions.create(
            model=model or self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
            temperature=0.1,
        )
        
        return resp.choices[0].message.content or ""
    
    def call_json(self, prompt: str, model: str = None) -> Dict[str, Any]:
        """
        调用LLM并解析JSON输出
        
        Args:
            prompt: 提示词
            model: 模型名称（可选）
        
        Returns:
            解析后的JSON对象
        """
        content = self.call(prompt, model)
        return self._parse_json(content)
    
    def _parse_json(self, raw: str) -> Dict[str, Any]:
        """从LLM输出中提取JSON"""
        if not raw:
            return {}
        
        raw = raw.strip()
        
        # 去掉markdown代码块
        if raw.startswith("```"):
            lines = raw.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)
        
        # 找JSON边界
        start = raw.find("{")
        end = raw.rfind("}")
        
        if start == -1 or end == -1 or start >= end:
            return {}
        
        json_str = raw[start:end + 1]
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {}


# 全局实例
_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """获取LLM客户端单例"""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
