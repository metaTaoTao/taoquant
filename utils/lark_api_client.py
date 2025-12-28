"""
Lark (飞书) API 客户端

支持通过 App ID 和 App Secret 访问 Lark API，包括：
- 获取 access_token
- 访问文件列表
- 下载文件
- 读取文件内容
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import requests


class LarkAPIClient:
    """Lark API 客户端"""

    BASE_URL = "https://open.larksuite.com/open-apis"

    def __init__(self, app_id: str, app_secret: str):
        """
        初始化 Lark API 客户端

        Parameters
        ----------
        app_id : str
            Lark App ID
        app_secret : str
            Lark App Secret
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

    def _get_access_token(self) -> str:
        """
        获取 access_token（带缓存）

        Returns
        -------
        str
            access_token
        """
        # 如果 token 还有效，直接返回
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        # 获取新 token
        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get("code") != 0:
                raise ValueError(f"获取 access_token 失败: {result.get('msg')}")

            self._access_token = result.get("tenant_access_token")
            # token 有效期通常是 2 小时，我们提前 5 分钟刷新
            self._token_expires_at = time.time() + result.get("expire", 7200) - 300

            return self._access_token
        except Exception as e:
            raise RuntimeError(f"获取 access_token 失败: {e}") from e

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        发送 API 请求

        Parameters
        ----------
        method : str
            HTTP 方法（GET, POST, etc.）
        endpoint : str
            API 端点（不包含 base URL）
        params : Optional[Dict[str, Any]]
            URL 参数
        json_data : Optional[Dict[str, Any]]
            JSON 请求体

        Returns
        -------
        Dict[str, Any]
            API 响应
        """
        token = self._get_access_token()
        url = f"{self.BASE_URL}{endpoint}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, params=params, json=json_data, timeout=30)
            else:
                raise ValueError(f"不支持的 HTTP 方法: {method}")

            response.raise_for_status()
            result = response.json()

            if result.get("code") != 0:
                raise ValueError(f"API 请求失败: {result.get('msg')}")

            return result
        except Exception as e:
            raise RuntimeError(f"API 请求失败: {e}") from e

    def list_files(
        self,
        folder_token: Optional[str] = None,
        page_size: int = 50,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        列出文件/文件夹

        Parameters
        ----------
        folder_token : Optional[str]
            文件夹 token（如果为 None，则列出根目录）
        page_size : int
            每页数量
        page_token : Optional[str]
            分页 token

        Returns
        -------
        Dict[str, Any]
            文件列表
        """
        endpoint = "/drive/v1/files"
        params = {
            "page_size": page_size,
        }
        if folder_token:
            params["folder_token"] = folder_token
        if page_token:
            params["page_token"] = page_token

        return self._request("GET", endpoint, params=params)

    def get_file_info(self, file_token: str) -> Dict[str, Any]:
        """
        获取文件信息

        Parameters
        ----------
        file_token : str
            文件 token

        Returns
        -------
        Dict[str, Any]
            文件信息
        """
        endpoint = f"/drive/v1/files/{file_token}/meta"
        return self._request("GET", endpoint)

    def download_file(self, file_token: str, output_path: Optional[str] = None) -> bytes:
        """
        下载文件

        Parameters
        ----------
        file_token : str
            文件 token
        output_path : Optional[str]
            输出路径（如果提供，文件将保存到该路径）

        Returns
        -------
        bytes
            文件内容
        """
        token = self._get_access_token()
        url = f"{self.BASE_URL}/drive/v1/files/{file_token}/download"

        headers = {
            "Authorization": f"Bearer {token}",
        }

        try:
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()

            file_content = response.content

            if output_path:
                with open(output_path, "wb") as f:
                    f.write(file_content)
                print(f"✅ 文件已保存到: {output_path}")

            return file_content
        except Exception as e:
            raise RuntimeError(f"下载文件失败: {e}") from e

    def get_file_content(self, file_token: str) -> str:
        """
        获取文件内容（文本文件）

        Parameters
        ----------
        file_token : str
            文件 token

        Returns
        -------
        str
            文件内容
        """
        content = self.download_file(file_token)
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("utf-8", errors="ignore")

    def search_files(
        self,
        query: str,
        search_scopes: Optional[List[Dict[str, Any]]] = None,
        page_size: int = 50,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        搜索文件

        Parameters
        ----------
        query : str
            搜索关键词
        search_scopes : Optional[List[Dict[str, Any]]]
            搜索范围
        page_size : int
            每页数量
        page_token : Optional[str]
            分页 token

        Returns
        -------
        Dict[str, Any]
            搜索结果
        """
        endpoint = "/drive/v1/files/search"
        json_data = {
            "query": query,
            "page_size": page_size,
        }
        if search_scopes:
            json_data["search_scopes"] = search_scopes
        if page_token:
            json_data["page_token"] = page_token

        return self._request("POST", endpoint, json_data=json_data)

    def get_shared_files(self, page_size: int = 50, page_token: Optional[str] = None) -> Dict[str, Any]:
        """
        获取共享给我的文件

        Parameters
        ----------
        page_size : int
            每页数量
        page_token : Optional[str]
            分页 token

        Returns
        -------
        Dict[str, Any]
            共享文件列表
        """
        # 注意：这个 API 可能需要特定的权限，具体请参考 Lark 文档
        # 这里使用搜索 API 来查找共享文件
        return self.search_files(query="", page_size=page_size, page_token=page_token)


def parse_file_token_from_url(url: str) -> Optional[str]:
    """
    从 Lark 文件 URL 中解析文件 token

    Parameters
    ----------
    url : str
        Lark 文件 URL（例如：https://xxx.feishu.cn/docx/xxxxx）

    Returns
    -------
    Optional[str]
        文件 token，如果无法解析则返回 None
    """
    # Lark 文件 URL 格式：
    # https://xxx.feishu.cn/docx/xxxxx
    # https://xxx.larksuite.com/docx/xxxxx
    # 其中 xxxxx 是文件 token

    import re

    patterns = [
        r"/(?:docx|docs|sheet|bitable|file)/([a-zA-Z0-9]+)",
        r"token=([a-zA-Z0-9]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


if __name__ == "__main__":
    # 示例用法
    import os

    app_id = os.getenv("LARK_APP_ID")
    app_secret = os.getenv("LARK_APP_SECRET")

    if not app_id or not app_secret:
        print("⚠️ 请设置环境变量 LARK_APP_ID 和 LARK_APP_SECRET")
        print("\n如何获取 App ID 和 App Secret:")
        print("1. 访问 https://open.larksuite.com/app")
        print("2. 创建应用或选择已有应用")
        print("3. 在'凭证与基础信息'中获取 App ID 和 App Secret")
    else:
        client = LarkAPIClient(app_id=app_id, app_secret=app_secret)

        # 示例：列出文件
        print("📁 正在列出文件...")
        try:
            result = client.list_files()
            print(f"✅ 成功获取文件列表: {json.dumps(result, indent=2, ensure_ascii=False)}")
        except Exception as e:
            print(f"❌ 获取文件列表失败: {e}")


