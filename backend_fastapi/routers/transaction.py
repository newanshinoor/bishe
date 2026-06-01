from fastapi import APIRouter, HTTPException, Depends, Header, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import mimetypes
import time
import cv2
import torch
import torch.nn as nn
import os
import re
import uuid
from datetime import datetime
from urllib.parse import quote
import jwt

# === 数据库相关引入 ===
from sqlalchemy import Column, String, Integer, Numeric, DateTime
from sqlalchemy.orm import Session
# 假设你有一个 core/database.py 文件，里面配置了 SQLAlchemy 的 Base 和 get_db
# 如果路径或命名不同，请根据你的实际项目结构调整
from core.database import Base, get_db
from core.payment_state import create_payment_order, get_payment_order
from routers.user import ALGORITHM, SECRET_KEY

router = APIRouter(prefix="/api/transaction", tags=["交易与防作弊模块"])


# ==========================================
# 0. 定义数据库映射模型 (ORM)
# ==========================================
class TransactionDB(Base):
    __tablename__ = "transaction"

    transaction_id = Column(String(32), primary_key=True, index=True, comment="交易流水单号")
    customer_id = Column(Integer, nullable=False, comment="购买顾客编号")
    product_name = Column(String(50), nullable=False, comment="售卖果蔬名")
    total_amount = Column(Numeric(8, 2), nullable=False, comment="交易原始总重")
    pay_amount = Column(Numeric(8, 2), nullable=False, comment="顾客实际支付扣款额")
    profit = Column(Numeric(8, 2), nullable=False, comment="本单利润")
    tag = Column(Integer, nullable=False, default=0, comment="违规标签")
    creat_at = Column(DateTime, nullable=False, default=datetime.now, comment="订单产生时间")


# ==========================================
# 1. 防作弊模型部分 (保留你的原始逻辑)
# ==========================================
class AntiCheatLSTM(nn.Module):
    def __init__(self, input_size=6, hidden_size=64, num_layers=2, num_classes=4):
        super(AntiCheatLSTM, self).__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, num_classes)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


MODEL_PATH = r"D:\pycharmProjects\fruit_recognition_system\model_training\LSTM\anti_cheat_lstm.pth"
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = AntiCheatLSTM().to(device)

if os.path.exists(MODEL_PATH):
    try:
        model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
        model.eval()
        print("Anti-fraud LSTM model loaded successfully.")
    except RuntimeError as exc:
        print(f"Anti-fraud LSTM model shape mismatch, please retrain: {exc}")


class TransactionSequence(BaseModel):
    features: List[List[float]]


@router.post("/verify")
async def verify_transaction(data: TransactionSequence):
    """
    接收时序特征，返回行为判定结果
    """
    try:
        input_tensor = torch.tensor([data.features]).float().to(device)

        with torch.no_grad():
            outputs = model(input_tensor)
            probabilities = torch.softmax(outputs, dim=1)
            _, predicted = torch.max(outputs, 1)
            result_idx = predicted.item()
            lstm_score = float(probabilities[0, result_idx].item())

        mapping = {0: "normal", 1: "swap", 2: "occlusion", 3: "lift"}
        status = mapping.get(result_idx, "unknown")

        return {
            "status": "success",
            "prediction": status,
            "is_secure": status == "normal",
            "code": result_idx,
            "lstm_score": round(lstm_score, 3)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 2. 支付结算与数据库联动部分
# ==========================================

def get_current_customer(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    从 Bearer Token 中解析当前顾客身份。

    token 可以来自普通登录，也可以来自 /api/payment/mock-login 的扫码授权模拟接口。
    真实业务中这里通常会做 JWT 校验、用户状态检查、风控检查等。
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Authorization Bearer Token，请先扫码授权",
        )

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期，请重新扫码授权",
        )

    customer_id = payload.get("customer_id")
    if customer_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 中缺少 customer_id，请使用新的扫码授权接口重新登录",
        )

    return {
        "customer_id": int(customer_id),
        "openid": payload.get("openid"),
        "subject": payload.get("sub"),
    }


class OrderCreateReq(BaseModel):
    items: List[Dict[str, Any]]
    total_amount: float
    payment_channel: str = "mock_wechat"


@router.post("/create")
async def create_transaction(
    req: OrderCreateReq,
    request: Request,
    db: Session = Depends(get_db),
    customer: Dict[str, Any] = Depends(get_current_customer),
):
    """
    创建订单：将前端购物车中的商品拆分成多条流水存入 transaction 表
    """
    # 1. 生成一个统一个的前端展示订单号（用于支付查状态）
    parent_order_id = f"ORD_{uuid.uuid4().hex[:10].upper()}"

    current_time = datetime.now()
    customer_id = customer["customer_id"]
    transaction_ids = []

    try:
        # 2. 遍历购物车，每一项生成一条 transaction 记录
        for item in req.items:
            # 使用 uuid hex 生成 32 位的流水单号
            tx_id = uuid.uuid4().hex
            transaction_ids.append(tx_id)

            # 从前端获取重量和价格数据 (需确保转换为浮点数)
            item_weight = float(item.get("weight", 0))
            item_pay_amount = float(item.get("price", 0))

            # 利润计算模拟：假设利润是售价的 30% (实际可以根据你的进货价逻辑修改)
            item_profit = round(item_pay_amount * 0.3, 2)

            # 违规标签默认设为 0 (正常)
            item_tag = 0

            new_tx = TransactionDB(
                transaction_id=tx_id,
                customer_id=customer_id,
                product_name=item.get("name", "未知商品"),
                total_amount=item_weight,  # 交易原始总重
                pay_amount=item_pay_amount,  # 顾客实际支付扣款额
                profit=item_profit,  # 本单利润
                tag=item_tag,
                creat_at=current_time
            )
            db.add(new_tx)

        # 3. 提交事务，真正写入 MySQL
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"数据库写入失败: {str(e)}")

    # 4. 创建一笔模拟支付网关订单。
    # 二维码指向 /api/payment/confirm-page/{order_id}，扫码后进入确认页；
    # 确认页会调用 /api/payment/callback，模拟第三方支付平台异步回调。
    base_url = str(request.base_url).rstrip("/")
    payment_url = f"{base_url}/api/payment/confirm-page/{parent_order_id}"
    qr_url = (
        "https://api.qrserver.com/v1/create-qr-code/"
        f"?size=250x250&data={quote(payment_url, safe='')}"
    )
    create_payment_order(
        order_id=parent_order_id,
        customer_id=customer_id,
        amount=req.total_amount,
        payment_url=payment_url,
        qr_code_url=qr_url,
        transaction_ids=transaction_ids,
        payment_channel=req.payment_channel,
    )

    return {
        "order_id": parent_order_id,
        "total_amount": req.total_amount,
        "customer_id": customer_id,
        "openid": customer.get("openid"),
        "payment_status": "pending",
        "payment_url": payment_url,
        "qr_code_url": qr_url,
        "msg": "订单流水已成功录入数据库"
    }


@router.get("/status/{order_id}")
async def get_transaction_status(order_id: str):
    """
    前端轮询支付状态
    """
    order = get_payment_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return {
        "status": order["status"],
        "order_id": order_id,
        "customer_id": order["customer_id"],
        "paid_at": order.get("paid_at"),
    }


# ==========================================
# 3. 后台管理系统 (Admin Dashboard) 专用接口
# ==========================================

@router.get("/list")
async def get_transaction_list(tag: int = None, db: Session = Depends(get_db)):
    """
    获取订单流水列表，供后台管理系统展示
    tag: 0=正常, 1=换货作弊, 2=遮挡作弊
    """
    try:
        query = db.query(TransactionDB)
        if tag is not None:
            query = query.filter(TransactionDB.tag == tag)

        # 按时间倒序排列，最新的订单在最前面
        records = query.order_by(TransactionDB.creat_at.desc()).all()

        result = []
        for r in records:
            result.append({
                "transaction_id": r.transaction_id,
                "customer_id": r.customer_id,
                "product_name": r.product_name,
                "total_amount": float(r.total_amount),  # 原始总重
                "pay_amount": float(r.pay_amount),  # 支付金额
                "profit": float(r.profit),  # 利润
                "tag": r.tag,  # 违规标签
                "creat_at": r.creat_at.strftime("%Y-%m-%d %H:%M:%S") if r.creat_at else ""
            })
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TagUpdateReq(BaseModel):
    tag: int


@router.put("/{transaction_id}/tag")
async def update_transaction_tag(transaction_id: str, req: TagUpdateReq, db: Session = Depends(get_db)):
    """
    更新订单的违规标签状态（后台人工标记异常或恢复正常）
    """
    try:
        tx = db.query(TransactionDB).filter(TransactionDB.transaction_id == transaction_id).first()
        if not tx:
            return {"status": "error", "message": "未找到该交易记录"}

        tx.tag = req.tag
        db.commit()
        return {"status": "success", "message": "状态更新成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{transaction_id}")
async def delete_transaction(transaction_id: str, db: Session = Depends(get_db)):
    """
    删除单条历史订单记录
    """
    try:
        tx = db.query(TransactionDB).filter(TransactionDB.transaction_id == transaction_id).first()
        if not tx:
            return {"status": "error", "message": "未找到该交易记录"}

        db.delete(tx)
        db.commit()
        return {"status": "success", "message": "记录删除成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 🌟 追加：LSTM 防作弊报警日志接口
# ==========================================
from sqlalchemy import text
from core.database import engine


def _resolve_alarm_file_path(raw_path: str) -> Optional[str]:
    """
    将 alarm_log.shot_path 转成后端可读取的真实磁盘路径。

    兼容以下几种常见写法：
    1. static/alarms/demo.mp4
    2. /static/alarms/demo.mp4
    3. backend_fastapi/static/alarms/demo.mp4
    4. D:/.../backend_fastapi/static/alarms/demo.mp4
    """
    if not raw_path:
        return None

    normalized = raw_path.replace("\\", "/").strip()
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    candidates = []
    if os.path.isabs(raw_path):
        candidates.append(raw_path)

    static_index = normalized.lower().find("static/")
    if static_index >= 0:
        candidates.append(os.path.join(backend_dir, normalized[static_index:]))

    candidates.append(os.path.join(backend_dir, normalized.lstrip("/")))

    for candidate in candidates:
        if not candidate or not os.path.exists(candidate):
            continue

        if os.path.isfile(candidate):
            return os.path.abspath(candidate)

        # 兼容数据库中只填了目录路径的情况：自动取目录下最新的视频/图片证据文件。
        if os.path.isdir(candidate):
            media_files = []
            for name in os.listdir(candidate):
                full_path = os.path.join(candidate, name)
                if os.path.isfile(full_path) and name.lower().endswith((".mp4", ".webm", ".mov", ".avi", ".m4v", ".jpg", ".jpeg", ".png")):
                    media_files.append(full_path)
            if media_files:
                media_files.sort(key=os.path.getmtime, reverse=True)
                return os.path.abspath(media_files[0])

    return None


def _iter_file_range(file_path: str, start: int, end: int, chunk_size: int = 1024 * 1024):
    """按字节范围读取文件，支持浏览器 video 标签的 Range 请求。"""
    with open(file_path, "rb") as file:
        file.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            data = file.read(min(chunk_size, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def _iter_mjpeg_frames(file_path: str):
    """
    使用 OpenCV 解码证据视频，并逐帧转换为浏览器可以直接显示的 JPEG 流。

    OpenCV VideoWriter 默认写出的 mp4v 文件可以由后端读取，但部分浏览器不支持
    直接播放。该兼容流不修改原始证据文件，只在浏览器需要时进行转码展示。
    """
    capture = cv2.VideoCapture(file_path)
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0 or fps > 60:
        fps = 15.0
    frame_interval = 1.0 / fps

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break

            encoded, jpg = cv2.imencode(
                ".jpg",
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, 82],
            )
            if encoded:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpg.tobytes()
                    + b"\r\n"
                )
            time.sleep(frame_interval)
    finally:
        capture.release()


@router.get("/alarms")
def get_alarm_logs():
    """
    获取 LSTM 模型判定的违规报警记录与证据路径
    """
    try:
        with engine.connect() as conn:
            # 查询 alarm_log 表，按时间倒序排列最新的违规记录
            sql = text("""
                SELECT log_id, transaction_id, creat_at, violation_type, lstm_score, shot_path 
                FROM alarm_log 
                ORDER BY creat_at DESC
            """)
            result = conn.execute(sql).fetchall()

            alarms = []
            for row in result:
                shot_path = row[5]
                resolved_path = _resolve_alarm_file_path(shot_path)
                evidence_type = "video"
                if resolved_path and resolved_path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")):
                    evidence_type = "image"

                alarms.append({
                    "log_id": row[0],
                    "transaction_id": row[1],
                    "creat_at": row[2].strftime("%Y-%m-%d %H:%M:%S") if row[2] else "",
                    "violation_type": row[3],
                    "lstm_score": float(row[4]),
                    "shot_path": shot_path,
                    "evidence_url": f"/api/transaction/evidence/{row[0]}",
                    "evidence_type": evidence_type,
                    "evidence_exists": bool(resolved_path),
                })
            return {"status": "success", "data": alarms}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/evidence/{log_id}")
def get_alarm_evidence_file(log_id: int, range_header: Optional[str] = Header(default=None, alias="Range")):
    """
    根据报警日志编号返回证据视频/图片文件。

    前端不要直接拼 shot_path 访问文件；统一访问该接口，可以兼容数据库中存放的
    相对路径、static 路径或 Windows 绝对路径。
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT shot_path FROM alarm_log WHERE log_id = :log_id"),
                {"log_id": log_id},
            ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Evidence log not found")

        file_path = _resolve_alarm_file_path(row[0])
        if not file_path:
            raise HTTPException(status_code=404, detail=f"Evidence file not found: {row[0]}")

        file_size = os.path.getsize(file_path)
        media_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

        # 浏览器 video 标签通常会发送 Range 请求。显式支持 206 Partial Content，
        # 可以避免大视频或部分浏览器环境下只显示黑屏/空白。
        if range_header:
            match = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if not match:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

            start_text, end_text = match.groups()
            start = int(start_text) if start_text else 0
            end = int(end_text) if end_text else file_size - 1
            end = min(end, file_size - 1)

            if start >= file_size or start > end:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

            headers = {
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(end - start + 1),
                "Content-Disposition": f"inline; filename*=UTF-8''{quote(os.path.basename(file_path))}",
            }
            return StreamingResponse(
                _iter_file_range(file_path, start, end),
                status_code=206,
                media_type=media_type,
                headers=headers,
            )

        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(os.path.basename(file_path))}",
        }
        return StreamingResponse(
            _iter_file_range(file_path, 0, file_size - 1),
            media_type=media_type,
            headers=headers,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evidence-mjpeg/{log_id}")
def get_alarm_evidence_mjpeg(log_id: int):
    """
    浏览器兼容的证据视频播放接口。

    当 HTML video 无法直接播放 OpenCV 生成的 mp4v 文件时，前端会自动切换到本接口。
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT shot_path FROM alarm_log WHERE log_id = :log_id"),
                {"log_id": log_id},
            ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Evidence log not found")

        file_path = _resolve_alarm_file_path(row[0])
        if not file_path:
            raise HTTPException(status_code=404, detail=f"Evidence file not found: {row[0]}")

        if file_path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")):
            raise HTTPException(status_code=400, detail="Image evidence does not need MJPEG streaming")

        return StreamingResponse(
            _iter_mjpeg_frames(file_path),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
