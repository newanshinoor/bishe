from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import WebSocket


# 演示环境使用内存保存支付订单状态。
# 生产环境建议替换为 payment_order 表 + Redis Pub/Sub，避免多进程或重启后状态丢失。
payment_orders: Dict[str, Dict[str, Any]] = {}


def create_payment_order(
    order_id: str,
    customer_id: int,
    amount: float,
    payment_url: str,
    qr_code_url: str,
    transaction_ids: List[str],
    payment_channel: str = "mock_wechat",
    customer_id_hash: Optional[str] = None,
    customer_platform: Optional[str] = None,
    expire_seconds: int = 120,
) -> Dict[str, Any]:
    """创建一笔待支付的模拟网关订单。"""
    now = datetime.now()
    order = {
        "order_id": order_id,
        "customer_id": customer_id,
        "customer_id_hash": customer_id_hash,
        "customer_platform": customer_platform,
        "amount": round(float(amount), 2),
        "status": "pending",
        "payment_channel": payment_channel,
        "payment_url": payment_url,
        "qr_code_url": qr_code_url,
        "transaction_ids": transaction_ids,
        "gateway_trade_no": None,
        "created_at": now.isoformat(timespec="seconds"),
        "expire_at": (now + timedelta(seconds=expire_seconds)).isoformat(timespec="seconds"),
        "paid_at": None,
    }
    payment_orders[order_id] = order
    return order


def get_payment_order(order_id: str) -> Optional[Dict[str, Any]]:
    """读取订单状态。"""
    return payment_orders.get(order_id)


def mark_payment_completed(
    order_id: str,
    payment_channel: str = "mock_wechat",
    gateway_trade_no: Optional[str] = None,
    paid_amount: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """模拟第三方支付平台回调成功后，将订单置为已支付。"""
    order = payment_orders.get(order_id)
    if not order:
        return None

    order["status"] = "completed"
    order["payment_channel"] = payment_channel
    order["gateway_trade_no"] = gateway_trade_no
    order["paid_amount"] = round(float(paid_amount), 2) if paid_amount is not None else order["amount"]
    order["paid_at"] = datetime.now().isoformat(timespec="seconds")
    return order


class PaymentConnectionManager:
    """维护订单号到前端 WebSocket 连接的映射。"""

    def __init__(self) -> None:
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, order_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(order_id, []).append(websocket)

    def disconnect(self, order_id: str, websocket: WebSocket) -> None:
        sockets = self._connections.get(order_id)
        if not sockets:
            return
        if websocket in sockets:
            sockets.remove(websocket)
        if not sockets:
            self._connections.pop(order_id, None)

    async def notify(self, order_id: str, payload: Dict[str, Any]) -> None:
        """通知正在等待该订单支付结果的前端页面。"""
        sockets = list(self._connections.get(order_id, []))
        for websocket in sockets:
            try:
                await websocket.send_json(payload)
            except Exception:
                self.disconnect(order_id, websocket)


payment_manager = PaymentConnectionManager()
