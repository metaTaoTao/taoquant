"""
Lark 文件管理工具

支持：
- 列出文件
- 搜索文件
- 下载文件
- 读取文件内容
"""

import argparse
import os
import sys
from pathlib import Path

# 设置 UTF-8 编码
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from utils.lark_api_client import LarkAPIClient, parse_file_token_from_url


def main():
    parser = argparse.ArgumentParser(description="Lark 文件管理工具")
    parser.add_argument(
        "--app-id",
        type=str,
        default=None,
        help="Lark App ID（如果不提供，将从环境变量 LARK_APP_ID 读取）",
    )
    parser.add_argument(
        "--app-secret",
        type=str,
        default=None,
        help="Lark App Secret（如果不提供，将从环境变量 LARK_APP_SECRET 读取）",
    )

    subparsers = parser.add_subparsers(dest="command", help="命令")

    # 列出文件
    list_parser = subparsers.add_parser("list", help="列出文件")
    list_parser.add_argument("--folder-token", type=str, default=None, help="文件夹 token（可选）")
    list_parser.add_argument("--page-size", type=int, default=50, help="每页数量")

    # 搜索文件
    search_parser = subparsers.add_parser("search", help="搜索文件")
    search_parser.add_argument("query", type=str, help="搜索关键词")
    search_parser.add_argument("--page-size", type=int, default=50, help="每页数量")

    # 获取文件信息
    info_parser = subparsers.add_parser("info", help="获取文件信息")
    info_parser.add_argument("file_token", type=str, help="文件 token 或 URL")

    # 下载文件
    download_parser = subparsers.add_parser("download", help="下载文件")
    download_parser.add_argument("file_token", type=str, help="文件 token 或 URL")
    download_parser.add_argument("--output", type=str, default=None, help="输出路径（可选）")

    # 读取文件内容
    read_parser = subparsers.add_parser("read", help="读取文件内容（文本文件）")
    read_parser.add_argument("file_token", type=str, help="文件 token 或 URL")

    args = parser.parse_args()

    # 获取 App ID 和 App Secret
    app_id = args.app_id or os.getenv("LARK_APP_ID")
    app_secret = args.app_secret or os.getenv("LARK_APP_SECRET")

    if not app_id or not app_secret:
        print("❌ 错误: 未提供 Lark App ID 和 App Secret")
        print("\n请使用以下方式之一:")
        print("1. 设置环境变量:")
        print("   export LARK_APP_ID='your_app_id'")
        print("   export LARK_APP_SECRET='your_app_secret'")
        print("2. 使用命令行参数:")
        print("   --app-id <your_app_id> --app-secret <your_app_secret>")
        print("\n如何获取 App ID 和 App Secret:")
        print("1. 访问 https://open.larksuite.com/app")
        print("2. 创建应用或选择已有应用")
        print("3. 在'凭证与基础信息'中获取 App ID 和 App Secret")
        print("4. 确保应用有以下权限:")
        print("   - drive:drive:readonly (读取云文档)")
        print("   - drive:drive:readonly:meta (读取文件元信息)")
        return 1

    # 创建客户端
    try:
        client = LarkAPIClient(app_id=app_id, app_secret=app_secret)
        print("✅ 已连接到 Lark API")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return 1

    # 解析文件 token（如果是 URL）
    if hasattr(args, "file_token") and args.file_token:
        file_token = parse_file_token_from_url(args.file_token) or args.file_token
    else:
        file_token = None

    # 执行命令
    try:
        if args.command == "list":
            print(f"📁 正在列出文件...")
            result = client.list_files(
                folder_token=args.folder_token,
                page_size=args.page_size,
            )
            print(f"\n✅ 成功获取文件列表:")
            print(f"   文件数量: {len(result.get('data', {}).get('files', []))}")
            for file in result.get("data", {}).get("files", [])[:10]:  # 只显示前 10 个
                file_type = file.get("type", "unknown")
                file_name = file.get("name", "unknown")
                file_token = file.get("token", "unknown")
                print(f"   - [{file_type}] {file_name} (token: {file_token})")
            if len(result.get("data", {}).get("files", [])) > 10:
                print(f"   ... 还有 {len(result.get('data', {}).get('files', [])) - 10} 个文件")

        elif args.command == "search":
            print(f"🔍 正在搜索: {args.query}")
            result = client.search_files(query=args.query, page_size=args.page_size)
            print(f"\n✅ 搜索结果:")
            for file in result.get("data", {}).get("files", []):
                file_type = file.get("type", "unknown")
                file_name = file.get("name", "unknown")
                file_token = file.get("token", "unknown")
                print(f"   - [{file_type}] {file_name} (token: {file_token})")

        elif args.command == "info":
            print(f"📄 正在获取文件信息: {file_token}")
            result = client.get_file_info(file_token)
            print(f"\n✅ 文件信息:")
            data = result.get("data", {}).get("file", {})
            for key, value in data.items():
                print(f"   {key}: {value}")

        elif args.command == "download":
            output_path = args.output or f"downloaded_file_{file_token[:8]}.bin"
            print(f"⬇️ 正在下载文件: {file_token}")
            print(f"   保存到: {output_path}")
            content = client.download_file(file_token, output_path=output_path)
            print(f"✅ 下载完成，文件大小: {len(content)} 字节")

        elif args.command == "read":
            print(f"📖 正在读取文件内容: {file_token}")
            content = client.get_file_content(file_token)
            print(f"\n✅ 文件内容 ({len(content)} 字符):\n")
            print("=" * 80)
            print(content[:5000])  # 只显示前 5000 个字符
            if len(content) > 5000:
                print(f"\n... (还有 {len(content) - 5000} 个字符未显示)")
            print("=" * 80)

        else:
            parser.print_help()
            return 1

        return 0

    except Exception as e:
        print(f"❌ 操作失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

