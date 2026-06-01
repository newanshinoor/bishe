from __future__ import annotations

import hashlib
import html
import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.payment_state import (
    get_payment_order,
    mark_payment_completed,
    payment_manager,
)
from routers.user import create_access_token


router = APIRouter(prefix="/api/payment", tags=["模拟支付网关"])


class MockScanLoginReq(BaseModel):
    scene: Optional[str] = None
    nickname: Optional[str] = None


class PaymentCallbackReq(BaseModel):
    order_id: str
    payment_channel: str = "mock_wechat"
    gateway_trade_no: Optional[str] = None
    paid_amount: Optional[float] = None


def _build_mock_customer(openid: str) -> int:
    """
    根据 openid 生成稳定的演示 customer_id。
    真实微信/支付宝授权时，这一步通常是用 openid 去用户表中查找或创建顾客记录。
    """
    digest = hashlib.sha256(openid.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 900000 + 100000


@router.post("/mock-login")
def mock_scan_login(req: MockScanLoginReq):
    """
    模拟“扫码登录/用户授权”。

    前端调用后会拿到一个带 openid 和 customer_id 的 JWT，
    后续建单时通过 Authorization: Bearer <token> 传给后端。
    """
    scene = req.scene or uuid.uuid4().hex[:12]
    openid_seed = f"{scene}:{req.nickname or 'guest'}"
    openid = f"mock_openid_{hashlib.sha256(openid_seed.encode('utf-8')).hexdigest()[:16]}"
    customer_id = _build_mock_customer(openid)

    token = create_access_token(
        data={
            "sub": openid,
            "openid": openid,
            "customer_id": customer_id,
            "login_type": "mock_scan",
        }
    )

    return {
        "status": "success",
        "token_type": "Bearer",
        "token": token,
        "openid": openid,
        "customer_id": customer_id,
        "nickname": req.nickname or "模拟顾客",
    }


@router.get("/status/{order_id}")
def get_payment_status(order_id: str):
    """支付状态查询接口，供轮询兜底使用。"""
    order = get_payment_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return {
        "status": order["status"],
        "order_id": order_id,
        "customer_id": order["customer_id"],
        "amount": order["amount"],
        "paid_at": order.get("paid_at"),
    }


@router.websocket("/ws/{order_id}")
async def payment_notify_ws(websocket: WebSocket, order_id: str):
    """
    支付结果通知 WebSocket。

    前端创建订单后连接此地址；当 /api/payment/callback 被调用时，
    后端会主动推送 payment_success，让前端跳转成功页或展示支付成功。
    """
    await payment_manager.connect(order_id, websocket)

    order = get_payment_order(order_id)
    await websocket.send_json(
        {
            "event": "payment_status",
            "order_id": order_id,
            "status": order["status"] if order else "not_found",
        }
    )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        payment_manager.disconnect(order_id, websocket)


@router.get("/confirm-page/{order_id}", response_class=HTMLResponse)
def payment_confirm_page(order_id: str, request: Request):
    """
    模拟支付网关确认页。

    二维码指向此页面。扫码后点击“确认支付”，页面会调用 /api/payment/callback，
    相当于第三方支付平台给商户系统发送异步回调。
    """
    order = get_payment_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    safe_order_id = html.escape(order_id)
    safe_amount = html.escape(f"{order['amount']:.2f}")
    channel = order.get("payment_channel", "mock_wechat")
    safe_channel = html.escape(channel)
    js_order_id = json.dumps(order_id)
    js_channel = json.dumps(channel)
    js_amount = json.dumps(float(order["amount"]))
    js_callback_url = json.dumps(callback_url)
    callback_url = str(request.base_url).rstrip("/") + "/api/payment/callback"

    return HTMLResponse(
        f"""
        <!doctype html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <title>模拟支付网关</title>
          <style>
            body {{
              margin: 0;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
              background: #f3f6fb;
              color: #1f2937;
              display: flex;
              align-items: center;
              justify-content: center;
              min-height: 100vh;
            }}
            main {{
              width: min(420px, calc(100vw - 32px));
              background: #fff;
              border-radius: 16px;
              box-shadow: 0 18px 50px rgba(15, 23, 42, 0.16);
              padding: 28px;
            }}
            h1 {{ margin: 0 0 16px; font-size: 24px; }}
            .amount {{ font-size: 38px; font-weight: 800; margin: 18px 0; color: #dc2626; }}
            .meta {{ line-height: 1.8; color: #4b5563; }}
            button {{
              width: 100%;
              border: 0;
              border-radius: 10px;
              padding: 14px 18px;
              margin-top: 24px;
              background: #16a34a;
              color: white;
              font-size: 17px;
              font-weight: 700;
              cursor: pointer;
            }}
            #result {{ margin-top: 16px; font-weight: 700; color: #16a34a; }}
          </style>
        </head>
        <body>
          <main>
            <h1>模拟支付确认</h1>
            <div class="meta">订单号：{safe_order_id}</div>
            <div class="meta">支付通道：{safe_channel}</div>
            <div class="amount">¥ {safe_amount}</div>
            <button id="payBtn">确认支付</button>
            <div id="result"></div>
          </main>
          <script>
            const btn = document.getElementById("payBtn");
            const result = document.getElementById("result");
            btn.onclick = async () => {{
              btn.disabled = true;
              btn.textContent = "正在提交...";
              const res = await fetch({js_callback_url}, {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify({{
                  order_id: {js_order_id},
                  payment_channel: {js_channel},
                  gateway_trade_no: "MOCK_" + Date.now(),
                  paid_amount: {js_amount}
                }})
              }});
              const data = await res.json();
              if (data.status === "success") {{
                result.textContent = "支付成功，售卖终端将自动跳转。";
                btn.textContent = "已支付";
              }} else {{
                result.textContent = data.message || "支付失败";
                btn.disabled = false;
                btn.textContent = "重新确认";
              }}
            }};
          </script>
        </body>
        </html>
        """
    )


@router.post("/callback")
async def payment_callback(req: PaymentCallbackReq):
    """
    模拟第三方支付回调 Webhook。

    真实支付平台会在用户付款完成后，由平台服务器请求这个接口；
    本项目演示时由确认页或 Postman/curl 手动调用它。
    """
    order = mark_payment_completed(
        order_id=req.order_id,
        payment_channel=req.payment_channel,
        gateway_trade_no=req.gateway_trade_no or f"MOCK_{uuid.uuid4().hex[:16].upper()}",
        paid_amount=req.paid_amount,
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    await payment_manager.notify(
        req.order_id,
        {
            "event": "payment_success",
            "order_id": req.order_id,
            "status": "completed",
            "redirect": f"/payment-success?order_id={req.order_id}",
            "paid_at": order["paid_at"],
        },
    )

    return {
        "status": "success",
        "order_id": req.order_id,
        "payment_status": "completed",
        "gateway_trade_no": order["gateway_trade_no"],
    }
