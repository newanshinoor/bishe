# backend_fastapi/routers/commodity.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
import pandas as pd
from core.database import engine
from core.inventory_schema import ensure_inventory_schema

router = APIRouter(prefix="/api", tags=["商品与库存管理"])


class PriceUpdateRequest(BaseModel):
    item_name: str
    new_price: float = Field(ge=0.0)


class CommodityUpdateRequest(BaseModel):
    item_name: str
    inventory: float = Field(ge=0.0)
    price: float = Field(ge=0.0)
    cost_price: float = Field(ge=0.0)
    freshness: float = Field(ge=0.0, le=1.0)


@router.get("/commodities")
def get_commodities():
    try:
        ensure_inventory_schema()
        query = text(
            "SELECT item_name, inventory, price, cost_price, freshness "
            "FROM fruit_inventory ORDER BY inventory ASC"
        )
        df = pd.read_sql(query, engine)
        return {"status": "success", "data": df.to_dict(orient="records")}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/update_price")
def update_price(req: PriceUpdateRequest):
    try:
        ensure_inventory_schema()
        with engine.begin() as conn:
            cost_price = conn.execute(
                text("SELECT cost_price FROM fruit_inventory WHERE item_name = :item_name"),
                {"item_name": req.item_name},
            ).scalar()
            if cost_price is None:
                raise HTTPException(status_code=404, detail="商品不存在")
            if req.new_price < float(cost_price):
                raise HTTPException(
                    status_code=400,
                    detail=f"售价不能低于成本止损底价 ¥{float(cost_price):.2f}",
                )

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

        # 🌟 打印炫酷的业务日志
        print(f"[Pricing] Successfully updated {req.item_name} price to: {req.new_price}. Triggering AI re-prediction...")
        return {"status": "success", "message": f"{req.item_name} 调价成功"}
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@router.post("/update_commodity")
def update_commodity(req: CommodityUpdateRequest):
    try:
        if req.price < req.cost_price:
            raise HTTPException(status_code=400, detail="基础售价不能低于成本价")

        ensure_inventory_schema()
        with engine.begin() as conn:
            # 1. 更新主表
            conn.execute(
                text(
                    "UPDATE fruit_inventory "
                    "SET inventory = :i, price = :p, cost_price = :c, freshness = :f "
                    "WHERE item_name = :n"
                ),
                {
                    "i": req.inventory,
                    "p": req.price,
                    "c": req.cost_price,
                    "f": req.freshness,
                    "n": req.item_name,
                })

            # 2. 同步更新历史表
            query = text("SELECT MAX(datetime) FROM fruit_sales_history WHERE item_name = :item_name")
            latest_time = conn.execute(query, {"item_name": req.item_name}).scalar()

            if latest_time:
                conn.execute(text(
                    "UPDATE fruit_sales_history SET inventory = :i, price = :p, freshness = :f WHERE item_name = :n AND datetime = :dt"),
                    {"i": req.inventory, "p": req.price, "f": req.freshness, "n": req.item_name,
                     "dt": latest_time})

        print(
            f"\n📦 [后台补货指令] {req.item_name} 更新完毕 -> 库存:{req.inventory}kg, "
            f"售价:¥{req.price}, 成本价:¥{req.cost_price}, 新鲜度:{req.freshness}")
        return {"status": "success", "message": f"{req.item_name} 信息更新成功！"}
    except HTTPException:
        raise
    except Exception as e:
        return {"status": "error", "message": str(e)}
