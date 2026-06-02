# backend_fastapi/init_inventory.py
import pandas as pd
from sqlalchemy import create_engine, text


def init_fruit_inventory():
    # ⚠️ 请修改为你自己的 MySQL 账号和密码
    db_url = "mysql+pymysql://root:123456@localhost:3306/fruit_shop"
    engine = create_engine(db_url)

    # 构建基础果蔬档案数据
    data = {
        'item_name': ['苹果', '香蕉', '西红柿', '黄瓜', '草莓', '葡萄', '土豆', '西瓜', '芒果'],
        'price': [12.0, 8.0, 9.0, 7.0, 40.0, 20.0, 4.0, 6.0, 15.0],  # 单价
        'cost_price': [4.8, 3.2, 3.6, 2.8, 16.0, 8.0, 1.6, 2.4, 6.0],  # 成本价
        'inventory': [80.0, 80.0, 80.0, 80.0, 50.0, 60.0, 150.0, 100.0, 50.0],  # 存货量
        'freshness': [0.95, 0.90, 0.92, 0.95, 0.85, 0.88, 0.98, 0.95, 0.88]  # 新鲜度
    }

    df = pd.DataFrame(data)

    try:
        # 将数据写入 MySQL，表名定为 fruit_inventory
        df.to_sql('fruit_inventory', con=engine, if_exists='replace', index=False)

        # 加上主键约束（让 item_name 成为唯一主键，防止出现重复水果）
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE fruit_inventory ADD PRIMARY KEY (item_name);"))
            conn.commit()

        print("✅ 全新果蔬表 (fruit_inventory) 创建并初始化成功！")

    except Exception as e:
        print(f"❌ 建表失败，请检查数据库连接或报错: {e}")


if __name__ == '__main__':
    init_fruit_inventory()
