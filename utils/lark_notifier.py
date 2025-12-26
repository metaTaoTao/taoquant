"""
Lark (飞书) 消息通知工具

支持通过 Webhook 或 API 发送消息到 Lark 群聊。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import requests


class LarkNotifier:
    """Lark 消息通知器"""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
    ):
        """
        初始化 Lark 通知器

        Parameters
        ----------
        webhook_url : Optional[str]
            Lark Webhook URL（最简单的方式）
        app_id : Optional[str]
            Lark App ID（用于 API 方式）
        app_secret : Optional[str]
            Lark App Secret（用于 API 方式）
        """
        self.webhook_url = webhook_url
        self.app_id = app_id
        self.app_secret = app_secret

    def send_text(self, text: str, title: Optional[str] = None) -> bool:
        """
        发送纯文本消息

        Parameters
        ----------
        text : str
            消息内容
        title : Optional[str]
            消息标题（可选）

        Returns
        -------
        bool
            是否发送成功
        """
        if self.webhook_url:
            return self._send_via_webhook(text, title)
        elif self.app_id and self.app_secret:
            return self._send_via_api(text, title)
        else:
            raise ValueError("需要提供 webhook_url 或 (app_id, app_secret)")

    def send_card(
        self,
        title: str,
        content: str,
        fields: Optional[list[Dict[str, Any]]] = None,
        buttons: Optional[list[Dict[str, Any]]] = None,
    ) -> bool:
        """
        发送卡片消息（更美观）

        Parameters
        ----------
        title : str
            卡片标题
        content : str
            卡片内容
        fields : Optional[list[Dict[str, Any]]]
            字段列表，格式: [{"title": "字段名", "value": "字段值"}]
        buttons : Optional[list[Dict[str, Any]]]
            按钮列表，格式: [{"text": "按钮文本", "url": "链接"}]

        Returns
        -------
        bool
            是否发送成功
        """
        if self.webhook_url:
            return self._send_card_via_webhook(title, content, fields, buttons)
        elif self.app_id and self.app_secret:
            return self._send_card_via_api(title, content, fields, buttons)
        else:
            raise ValueError("需要提供 webhook_url 或 (app_id, app_secret)")

    def _send_via_webhook(self, text: str, title: Optional[str] = None) -> bool:
        """通过 Webhook 发送文本消息"""
        payload = {"msg_type": "text", "content": {"text": text}}
        if title:
            payload["content"]["text"] = f"**{title}**\n\n{text}"

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            return result.get("code") == 0
        except Exception as e:
            print(f"[Lark] 发送消息失败: {e}")
            return False

    def _send_card_via_webhook(
        self,
        title: str,
        content: str,
        fields: Optional[list[Dict[str, Any]]] = None,
        buttons: Optional[list[Dict[str, Any]]] = None,
    ) -> bool:
        """通过 Webhook 发送卡片消息"""
        elements = []

        # 标题
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"# {title}"}})

        # 内容
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": content}})

        # 字段
        if fields:
            field_items = []
            for field in fields:
                field_title = field.get("title", "")
                field_value = field.get("value", "")
                field_items.append(
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": f"**{field_title}**: {field_value}"},
                    }
                )
            elements.extend(field_items)

        # 按钮
        if buttons:
            button_elements = []
            for button in buttons:
                button_text = button.get("text", "")
                button_url = button.get("url", "")
                button_elements.append(
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": button_text},
                        "url": button_url,
                        "type": "default",
                    }
                )
            elements.append({"tag": "action", "actions": button_elements})

        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {"title": {"tag": "plain_text", "content": title}, "template": "blue"},
                "elements": elements,
            },
        }

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            return result.get("code") == 0
        except Exception as e:
            print(f"[Lark] 发送卡片消息失败: {e}")
            return False

    def _send_via_api(self, text: str, title: Optional[str] = None) -> bool:
        """通过 API 发送文本消息（需要先获取 access_token）"""
        # TODO: 实现 API 方式
        raise NotImplementedError("API 方式暂未实现，请使用 Webhook 方式")

    def _send_card_via_api(
        self,
        title: str,
        content: str,
        fields: Optional[list[Dict[str, Any]]] = None,
        buttons: Optional[list[Dict[str, Any]]] = None,
    ) -> bool:
        """通过 API 发送卡片消息（需要先获取 access_token）"""
        # TODO: 实现 API 方式
        raise NotImplementedError("API 方式暂未实现，请使用 Webhook 方式")


def format_evaluation_summary(include_cro_crisis: bool = False) -> Dict[str, Any]:
    """
    格式化策略评价总结，用于发送到 Lark

    Parameters
    ----------
    include_cro_crisis : bool
        是否包含 CRO Crisis 视角的评价

    Returns
    -------
    Dict[str, Any]
        格式化的消息内容
    """
    content = """## 📊 综合评价

**策略类型**: 均值回归网格交易（做空波动率）

### ✅ 优势
1. **风控机制完善**: 多层级风险管理，持仓级止损，强制去杠杆，紧急停止
2. **执行逻辑清晰**: 订单配对机制明确，多因子体系动态调整
3. **生存能力强**: SUIUSDT 回测中，所有 regime 都成功抗住（最低权益 99%+）

### ⚠️ 劣势
1. **无统计优势**: 所有 regime 的 Sharpe 都是负数（-4.48 到 -5.32）
2. **0% 胜率**: 所有交易都亏损（可能是回测期间价格持续下跌）
3. **参数复杂度高**: 100+ 参数，过拟合风险

### 🔍 关键问题
1. **0% 胜率和负 Sharpe**: 需要验证是否是市场环境问题
2. **库存积累过快**: BULLISH_RANGE 在下跌行情中风险最高
3. **参数稳健性未知**: 需要系统性参数敏感性分析

### 📈 回测结果 (SUIUSDT 2025-09-03 至 2025-10-17)

| Regime | 总收益率 | Sharpe | 最大回撤 | 胜率 |
|--------|----------|--------|----------|------|
| BULLISH_RANGE | -0.98% | -4.48 | -1.98% | 0% |
| NEUTRAL_RANGE | -0.80% | -4.77 | -1.51% | 0% |
| BEARISH_RANGE | -0.67% | -5.32 | -1.10% | 0% |

### 🎯 最终决定

**有条件批准**

**部署前必须满足的条件**:
1. 解释 0% 胜率问题（在上涨和横盘市场环境下回测）
2. 参数稳健性分析（系统性参数敏感性分析）
3. 样本外验证（至少 3 个不同市场环境下的回测）

**当前状态**:
- ✅ 风控机制: 优秀（可以部署）
- ⚠️ 收益能力: 未知（需要进一步验证）
- ⚠️ 参数稳健性: 未知（需要进一步分析）

**建议**: 可以小资金实盘测试，验证执行逻辑，密切监控库存积累和胜率。"""

    if include_cro_crisis:
        content += """

---

## 🚨 CRO Crisis 视角：极端压力测试

### 核心问题
**"当多个坏事情同时发生时，这个策略如何死亡？"**

### 极端场景分析

#### 1. 清算级联 (Liquidation Cascades)
- **风险**: 价格快速下跌触发大量清算，导致价格进一步下跌
- **策略脆弱性**: 
  - 网格在价格快速下跌时无法及时平仓
  - 限价单可能无法成交，库存无法减少
  - 10x 杠杆下，价格下跌 10% 就会爆仓
- **应对**: ✅ 持仓级止损和强制去杠杆已实现，但需要验证在极端市场下的执行速度

#### 2. 资金费率爆炸 (Funding Rate Dislocations)
- **风险**: 资金费率突然飙升到 1%+（如 LUNA 崩盘时）
- **策略脆弱性**:
  - 多头持仓需要支付巨额资金费率
  - 当前资金费率因子仅在结算窗口附近应用，可能不够及时
- **应对**: ⚠️ 需要添加资金费率阈值，超过阈值时强制去杠杆

#### 3. 交易所故障 (Exchange Outages)
- **风险**: 交易所宕机、API 限流、提现冻结
- **策略脆弱性**:
  - 无法执行止损订单
  - 无法获取实时价格数据
  - 持仓暴露在风险中无法平仓
- **应对**: ⚠️ 需要添加多交易所备份机制，或外部监控系统

#### 4. 相关性崩溃 (Correlation Collapse)
- **风险**: 所有资产同时下跌，无避险资产
- **策略脆弱性**:
  - 假设单资产风险是孤立的
  - 如果多个交易对同时触发风险，总风险可能超出预期
- **应对**: ⚠️ 需要添加组合层面的风险控制

#### 5. 闪崩 (Flash Crash)
- **风险**: 价格在几秒内暴跌 50%+
- **策略脆弱性**:
  - 限价单无法成交
  - 网格关闭机制可能来不及触发
  - 持仓级止损可能无法执行
- **应对**: ⚠️ 需要添加价格变化率检测，超过阈值时立即市价平仓

### CRO Crisis 最终评价

**生存能力**: ⚠️ **中等**

**关键担忧**:
1. 在极端快速市场中，限价单可能无法成交
2. 资金费率爆炸时，缺乏强制去杠杆机制
3. 交易所故障时，无备份方案
4. 闪崩时，止损可能来不及执行

**必须添加的机制**:
1. ✅ 持仓级止损（已实现）
2. ⚠️ 资金费率阈值强制去杠杆（需要添加）
3. ⚠️ 价格变化率检测（需要添加）
4. ⚠️ 多交易所备份（需要添加）
5. ⚠️ 组合层面风险控制（需要添加）

**CRO 建议**: 
- 在添加上述机制之前，**不建议大规模部署**
- 可以小资金测试，但需要密切监控极端市场情况
- 优先实现价格变化率检测和资金费率阈值机制"""

    return {
        "title": "TaoGrid 策略评价报告",
        "content": content,
        "fields": [
            {"title": "评价日期", "value": "2025-12-24"},
            {"title": "评价角色", "value": "Lead Trader + Quantitative Research Lead" + (" + CRO Crisis" if include_cro_crisis else "")},
            {"title": "策略版本", "value": "Lean 实现 (Sprint 2+) + Enhanced Risk Controls (v2.0)"},
        ],
    }


if __name__ == "__main__":
    # 示例用法
    import os

    webhook_url = os.getenv("LARK_WEBHOOK_URL")
    if webhook_url:
        notifier = LarkNotifier(webhook_url=webhook_url)
        summary = format_evaluation_summary()
        success = notifier.send_card(
            title=summary["title"],
            content=summary["content"],
            fields=summary["fields"],
        )
        if success:
            print("✅ 消息已成功发送到 Lark")
        else:
            print("❌ 消息发送失败")
    else:
        print("⚠️ 请设置环境变量 LARK_WEBHOOK_URL")

