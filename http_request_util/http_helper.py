import requests
import json
from typing import Dict, Any, Optional, Union


class HttpClient:
    """通用HTTP RESTful接口调用类"""

    def __init__(self, base_url: str = "", default_headers: Dict[str, str] = None):
        """
        初始化HTTP客户端
        
        Args:
            base_url: API的基础URL
            default_headers: 默认请求头
        """
        self.base_url = base_url
        self.default_headers = default_headers or {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        self.session = requests.Session()
    
    def _build_url(self, endpoint: str) -> str:
        """构建完整的URL"""
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        return f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    
    def _prepare_headers(self, headers: Dict[str, str] = None) -> Dict[str, str]:
        """准备请求头"""
        prepared_headers = self.default_headers.copy()
        if headers:
            prepared_headers.update(headers)
        return prepared_headers
    
    def _handle_response(self, response: requests.Response, parse_json: bool = True) -> Any:
        """处理响应"""
        if not response.ok:
            response.raise_for_status()
        
        if parse_json and response.content:
            try:
                return response.json()
            except json.JSONDecodeError:
                return response.text
        
        return response.text if response.content else None
    
    def _prepare_request_body(
        self,
        data: Any = None,
        json_data: Any = None,
        headers: Dict[str,str] = None,        
    ) -> tuple[Any, Dict[str,str]]:
        prepared_headers = self._prepare_headers(headers)
        
        if json_data is None:
            return data, prepared_headers
        
        if isinstance(json_data, (bytes, bytearray)):
            body = json_data
        elif isinstance(json_data, str):
            body = json_data
        else:
            body = json.dumps(json_data, ensure_ascii=False)
        prepared_headers.setdefault("Content-Type", "application/json")
        return body, prepared_headers
    
    def get(self, endpoint: str, params: Dict[str, Any] = None, headers: Dict[str, str] = None, 
            timeout: int = 30, parse_json: bool = True) -> Any:
        """
        发送GET请求
        
        Args:
            endpoint: API端点
            params: 查询参数
            headers: 自定义请求头
            timeout: 超时时间（秒）
            parse_json: 是否解析JSON响应
        
        Returns:
            解析后的响应数据
        """
        url = self._build_url(endpoint)
        headers = self._prepare_headers(headers)
        
        response = self.session.get(url, params=params, headers=headers, timeout=timeout)
        return self._handle_response(response, parse_json)
    
    def post(self, endpoint: str, data: Any = None, json_data: Any = None, 
             params: Dict[str, Any] = None, headers: Dict[str, str] = None,
             timeout: int = 30, parse_json: bool = True) -> Any:
        """
        发送POST请求
        
        Args:
            endpoint: API端点
            data: 表单数据或原始数据
            json_data: JSON数据（将自动序列化）
            params: 查询参数
            headers: 自定义请求头
            timeout: 超时时间（秒）
            parse_json: 是否解析JSON响应
        
        Returns:
            解析后的响应数据
        """
        url = self._build_url(endpoint)
        request_body, headers = self._prepare_request_body(data=data, json_data=json_data, headers=headers)
        
        response = self.session.post(
            url,
            data=request_body,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        
        return self._handle_response(response, parse_json)
    
    def put(self, endpoint: str, data: Any = None, json_data: Any = None, 
            params: Dict[str, Any] = None, headers: Dict[str, str] = None,
            timeout: int = 30, parse_json: bool = True) -> Any:
        """
        发送PUT请求
        
        Args:
            endpoint: API端点
            data: 表单数据或原始数据
            json_data: JSON数据（将自动序列化）
            params: 查询参数
            headers: 自定义请求头
            timeout: 超时时间（秒）
            parse_json: 是否解析JSON响应
        
        Returns:
            解析后的响应数据
        """
        url = self._build_url(endpoint)
        request_body, headers = self._prepare_request_body(data=data, json_data=json_data, headers=headers)
        
        response = self.session.post(
            url,
            data=request_body,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        return self._handle_response(response, parse_json)
    
    def delete(self, endpoint: str, params: Dict[str, Any] = None, 
              headers: Dict[str, str] = None, json_data: Any = None,
              timeout: int = 30, parse_json: bool = True) -> Any:
        """
        发送DELETE请求
        
        Args:
            endpoint: API端点
            params: 查询参数
            headers: 自定义请求头
            json_data: JSON数据（将自动序列化）
            timeout: 超时时间（秒）
            parse_json: 是否解析JSON响应
        
        Returns:
            解析后的响应数据
        """
        url = self._build_url(endpoint)
        request_body, headers = self._prepare_request_body(data=data, json_data=json_data, headers=headers)
        
        response = self.session.post(
            url,
            data=request_body,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        return self._handle_response(response, parse_json)
    
    def patch(self, endpoint: str, data: Any = None, json_data: Any = None, 
             params: Dict[str, Any] = None, headers: Dict[str, str] = None,
             timeout: int = 30, parse_json: bool = True) -> Any:
        """
        发送PATCH请求
        
        Args:
            endpoint: API端点
            data: 表单数据或原始数据
            json_data: JSON数据（将自动序列化）
            params: 查询参数
            headers: 自定义请求头
            timeout: 超时时间（秒）
            parse_json: 是否解析JSON响应
        
        Returns:
            解析后的响应数据
        """
        url = self._build_url(endpoint)
        request_body, headers = self._prepare_request_body(data=data, json_data=json_data, headers=headers)
        
        response = self.session.post(
            url,
            data=request_body,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        return self._handle_response(response, parse_json)
    
    def close(self):
        """关闭会话"""
        self.session.close()
