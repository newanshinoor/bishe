# backend_fastapi/routers/commodity.py
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
import pandas as pd
from core.database import engine

router = APIRouter(prefix="/api", tags=["商品与库存管理"])


class PriceUpdateRequest(BaseModel):
    item_name: str
    new_price: float


class CommodityUpdateRequest(BaseModel):
    item_name: str
    inventory: float
    price: float
    freshness: float


@router.get("/commodities")
def get_commodities():
    try:
        query = text("SELECT item_name, inventory, price, freshness FROM fruit_inventory ORDER BY inventory ASC")
        df = pd.read_sql(query, engine)
        return {"status": "success", "data": df.to_dict(orient="records")}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/update_price")
def update_price(req: PriceUpdateRequest):
    try:
        with engine.connect() as conn:
            # 1. 更新主表 fruit_inventory
            conn.execute(text("UPDATE fruit_inventory SET price = :new_price WHERE item_name = :item_name"),
                         {"new_price": req.new_price, "item_name": req.item_name})

            # 2. 同步更新历史表的最后一刻状态
            query = text("SELECT MAX(datetime) FROM fruit_sales_history WHERE item_name = :item_name")
            latest_time = conn.execute(query, {"item_name": req.item_name}).scalar()

            if latest_time:
                conn.execute(text(
                    "UPDATE fruit_sales_history SET price = :new_price WHERE item_name = :item_name AND datetime = :dt"),
                    {"new_price": req.new_price, "item_name": req.item_name, "dt": latest_time})
            conn.commit()

        # 🌟 打印炫酷的业务日志
        print(f"[Pricing] Successfully updated {req.item_name} price to: {req.new_price}. Triggering AI re-prediction...")
        return {"status": "success", "message": f"{req.item_name} 调价成功"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/update_commodity")
def update_commodity(req: CommodityUpdateRequest):
    try:
        with engine.connect() as conn:
            # 1. 更新主表
            conn.execute(
                text("UPDATE fruit_inventory SET inventory = :i, price = :p, freshness = :f WHERE item_name = :n"),
                {"i": req.inventory, "p": req.price, "f": req.freshness, "n": req.item_name})

            # 2. 同步更新历史表
            query = text("SELECT MAX(datetime) FROM fruit_sales_history WHERE item_name = :item_name")
            latest_time = conn.execute(query, {"item_name": req.item_name}).scalar()

            if latest_time:
                conn.execute(text(
                    "UPDATE fruit_sales_history SET inventory = :i, price = :p, freshness = :f WHERE item_name = :n AND datetime = :dt"),
                    {"i": req.inventory, "p": req.price, "f": req.freshness, "n": req.item_name,
                     "dt": latest_time})
            conn.commit()

        print(
            f"\n📦 [后台补货指令] {req.item_name} 更新完毕 -> 库存:{req.inventory}kg, 价格:¥{req.price}, 新鲜度:{req.freshness}")
        return {"status": "success", "message": f"{req.item_name} 信息更新成功！"}
    except Exception as e:
        return {"status": "error", "message": str(e)}