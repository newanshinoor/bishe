import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy import create_engine


def init_mysql_database_with_history():
    db_url = "mysql+pymysql://root:123456@localhost:3306/fruit_shop"
    engine = create_engine(db_url)

    # 🌟 同步更新：大幅拉开基础销量差距，加入芒果
    items_config = {
        '土豆': {'base_price': 4.0, 'base_sales': 15.0, 'base_decay': 0.001, 'temp_sens': 1.0},
        '西瓜': {'base_price': 6.0, 'base_sales': 12.0, 'base_decay': 0.005, 'temp_sens': 1.5},
        '黄瓜': {'base_price': 7.0, 'base_sales': 8.0, 'base_decay': 0.008, 'temp_sens': 1.3},
        '西红柿': {'base_price': 9.0, 'base_sales': 7.0, 'base_decay': 0.010, 'temp_sens': 1.5},
        '香蕉': {'base_price': 8.0, 'base_sales': 6.0, 'base_decay': 0.015, 'temp_sens': 2.5},
        '苹果': {'base_price': 12.0, 'base_sales': 5.0, 'base_decay': 0.005, 'temp_sens': 1.2},
        '芒果': {'base_price': 15.0, 'base_sales': 3.5, 'base_decay': 0.025, 'temp_sens': 3.0},
        '葡萄': {'base_price': 20.0, 'base_sales': 2.5, 'base_decay': 0.020, 'temp_sens': 2.5},
        '草莓': {'base_price': 40.0, 'base_sales': 1.2, 'base_decay': 0.030, 'temp_sens': 4.0}
    }

    now = pd.Timestamp.now(tz='Asia/Shanghai').tz_localize(None).floor('h')
    start_date = now - pd.Timedelta(days=14)
    date_range = pd.date_range(start=start_date, end=now, freq='h')
    records = []

    print("正在重塑过去 14 天的完美历史基准 (适配极差销量与动态补货)...")
    for item, cfg in items_config.items():
        freshness = 1.0
        # 初始库存与基础销量挂钩
        inventory = 300.0

        for dt in date_range:
            hour = dt.hour
            day_of_week = dt.weekday()
            is_weekend = 1 if day_of_week >= 5 else 0

            month_day = dt.strftime('%m-%d')
            holidays = ['04-04', '04-05', '04-06', '05-01', '05-02', '05-03', '05-04', '05-05']
            is_holiday = 1 if month_day in holidays else 0

            days_passed = (dt - start_date).days
            base_temp = 15 + (days_passed * 0.2)
            temperature = round(base_temp + 8 * np.sin((hour - 8) * np.pi / 12) + np.random.normal(0, 2), 1)
            is_rainy = 1 if np.random.rand() < 0.15 else 0

            if hour == 6:
                freshness = 1.0
                # 动态智能按量补货
                inventory = 300.0
            else:
                temp_diff = temperature - 20.0
                dynamic_multiplier = max(0.2, 1.0 + (temp_diff * 0.05 * cfg['temp_sens']))
                freshness = max(0.1, freshness - (cfg['base_decay'] * dynamic_multiplier))

            current_price = cfg['base_price']
            if hour >= 20 or freshness < 0.6:
                current_price = round(cfg['base_price'] * 0.7, 2)

            if hour in [17, 18, 19, 20]:
                peak_multiplier = 2.5
            elif hour in [7, 8, 9]:
                peak_multiplier = 1.5
            elif hour in [11, 12, 13]:
                peak_multiplier = 1.2
            elif hour >= 22 or hour < 6:
                peak_multiplier = 0.01
            else:
                peak_multiplier = 0.6

            if hour >= 22 or hour < 6:
                base_bonus = 1.0
            else:
                base_bonus = 2.0 if is_holiday else 1.5 if is_weekend else 1.0

            if is_rainy:
                rain_penalty = 0.8 if item in ['土豆', '黄瓜', '西红柿'] else 0.4
                if base_bonus > 1.0: base_bonus = 1.0
            else:
                rain_penalty = 1.0

            expected_sales = cfg['base_sales'] * peak_multiplier * base_bonus * rain_penalty * (freshness ** 2.0)

            if current_price < cfg['base_price']: expected_sales *= 1.8
            if item == '西瓜':
                if temperature > 32:
                    expected_sales *= 3.0
                elif temperature > 26:
                    expected_sales *= 2.0
                elif temperature < 18:
                    expected_sales *= 0.2

            noise = np.random.normal(0, max(0.1, expected_sales * 0.15))
            actual_sales = expected_sales + noise

            if 6 <= hour <= 21:
                min_guarantee = cfg['base_sales'] * 0.15
                actual_sales = max(min_guarantee, actual_sales)
            else:
                if np.random.rand() < 0.85:
                    actual_sales = 0.0
                else:
                    actual_sales = max(0.0, actual_sales)

            actual_sales = round(min(actual_sales, inventory), 2)
            inventory -= actual_sales

            records.append({
                'item_name': item, 'datetime': dt, 'hour': hour,
                'day_of_week': day_of_week, 'is_weekend': is_weekend, 'is_holiday': is_holiday,
                'temperature': temperature, 'is_rainy': is_rainy,
                'freshness': round(freshness, 3), 'inventory': round(inventory, 2),
                'price': current_price, 'actual_sales': actual_sales
            })

    df = pd.DataFrame(records)
    df.to_sql('fruit_sales_history', con=engine, if_exists='replace', index=False)
    print("✅ 数据库刷入成功！")


if __name__ == '__main__':
    init_mysql_database_with_history()