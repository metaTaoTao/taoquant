"""
发送策略评价报告到 Lark 群聊

使用方法:
1. 设置环境变量 LARK_WEBHOOK_URL
2. 运行: python scripts/send_evaluation_to_lark.py

或者直接传入 webhook URL:
python scripts/send_evaluation_to_lark.py --webhook-url <your_webhook_url>
"""

import argparse
import os
import sys
from pathlib import Path

# 设置 UTF-8 编码，避免 Windows 下的编码问题
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from utils.lark_notifier import LarkNotifier, format_evaluation_summary


def main():
    parser = argparse.ArgumentParser(description="发送策略评价报告到 Lark")
    parser.add_argument(
        "--webhook-url",
        type=str,
        default=None,
        help="Lark Webhook URL（如果不提供，将从环境变量 LARK_WEBHOOK_URL 读取）",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["card", "text"],
        default="card",
        help="消息格式：card（卡片，推荐）或 text（纯文本）",
    )
    parser.add_argument(
        "--include-cro-crisis",
        action="store_true",
        help="包含 CRO Crisis 视角的极端压力测试分析",
    )

    args = parser.parse_args()

    # 获取 webhook URL
    webhook_url = args.webhook_url or os.getenv("LARK_WEBHOOK_URL")
    if not webhook_url:
        print("❌ 错误: 未提供 Lark Webhook URL")
        print("\n请使用以下方式之一:")
        print("1. 设置环境变量: export LARK_WEBHOOK_URL='your_webhook_url'")
        print("2. 使用命令行参数: --webhook-url <your_webhook_url>")
        print("\n如何获取 Webhook URL:")
        print("1. 在 Lark 群聊中，点击右上角设置")
        print("2. 选择 '群机器人' -> '添加机器人' -> '自定义机器人'")
        print("3. 复制 Webhook URL")
        return 1

    # 创建通知器
    notifier = LarkNotifier(webhook_url=webhook_url)

    # 格式化消息
    summary = format_evaluation_summary(include_cro_crisis=args.include_cro_crisis)

    # 发送消息
    if args.format == "card":
        print("📤 正在发送卡片消息到 Lark...")
        success = notifier.send_card(
            title=summary["title"],
            content=summary["content"],
            fields=summary["fields"],
        )
    else:
        print("📤 正在发送文本消息到 Lark...")
        text_content = f"{summary['title']}\n\n{summary['content']}"
        for field in summary["fields"]:
            text_content += f"\n**{field['title']}**: {field['value']}"
        success = notifier.send_text(text_content, title=summary["title"])

    if success:
        print("✅ 消息已成功发送到 Lark 群聊！")
        return 0
    else:
        print("❌ 消息发送失败，请检查 Webhook URL 是否正确")
        return 1


if __name__ == "__main__":
    sys.exit(main())

