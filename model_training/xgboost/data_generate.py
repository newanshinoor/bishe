import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.model_selection import train_test_split


def generate_and_split_ultimate_dataset():
    np.random.seed(42)

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

    start_date = datetime(2026, 3, 1)
    num_days = 60
    date_range = pd.date_range(start=start_date, periods=num_days * 24, freq='h')
    records = []

    print("正在向系统注入【连续价格弹性】的真实果蔬商业数据...")
    for item, cfg in items_config.items():
        freshness = 1.0
        inventory = 300.0

        for dt in date_range:
            hour = dt.hour
            day_of_week = dt.weekday()
            is_weekend = 1 if day_of_week >= 5 else 0

            month_day = dt.strftime('%m-%d')
            holidays = ['04-04', '04-05', '04-06', '05-01', '05-02', '05-03', '05-04', '05-05']
            is_holiday = 1 if month_day in holidays else 0

            days_passed = (dt - start_date).days
            temperature = round(15 + (days_passed * 0.2) + 8 * np.sin((hour - 8) * np.pi / 12) + np.random.normal(0, 2),
                                1)
            is_rainy = 1 if np.random.rand() < 0.15 else 0

            if hour == 6:
                freshness = 1.0
                inventory = 300.0
            else:
                temp_diff = temperature - 20.0
                dynamic_multiplier = max(0.2, 1.0 + (temp_diff * 0.05 * cfg['temp_sens']))
                freshness = max(0.1, freshness - (cfg['base_decay'] * dynamic_multiplier))

            # ==========================================
            # 🌟 终极升级：给 AI 教会真正的【价格弹性】
            # ==========================================
            # 让历史数据中随机出现“大降价”、“微降”、“原价”、“微涨”、“大涨价”
            random_price_factor = np.random.choice([0.7, 0.85, 1.0, 1.0, 1.0, 1.15, 1.3])
            current_price = round(cfg['base_price'] * random_price_factor, 2)

            # 如果到了晚上或者不新鲜了，强行骨折大甩卖
            if hour >= 20 or freshness < 0.6:
                current_price = round(cfg['base_price'] * 0.6, 2)

            if hour in [17, 18, 19]:
                peak_multiplier = 2.5
            elif hour in [16, 20]:
                peak_multiplier = 1.8
            elif hour in [7, 8]:
                peak_multiplier = 1.5
            elif hour == 9:
                peak_multiplier = 1.0
            elif hour in [11, 12]:
                peak_multiplier = 1.2
            elif hour == 13:
                peak_multiplier = 0.9
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

            # 🌟 核心引擎：价格对销量的直接缩放控制
            price_ratio = current_price / cfg['base_price']
            if price_ratio < 1.0:
                # 如果降价，销量最高可以爆涨到原来的 2.5 倍
                expected_sales *= (1.0 + (1.0 - price_ratio) * 2.5)
            elif price_ratio > 1.0:
                # 如果涨价，销量会遭遇断崖式下跌，最惨跌到原来的 0.1 倍
                expected_sales *= max(0.1, 1.0 - (price_ratio - 1.0) * 2.0)

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
            inventory = max(0.0, inventory - actual_sales)

            records.append({
                'item_name': item, 'datetime': dt, 'hour': hour,
                'day_of_week': day_of_week, 'is_weekend': is_weekend, 'is_holiday': is_holiday,
                'freshness': round(freshness, 3), 'inventory': round(inventory, 2),
                'price': current_price, 'temperature': temperature, 'is_rainy': is_rainy,
                'actual_sales': actual_sales
            })

    df = pd.DataFrame(records)
    df = df.sort_values(by=['item_name', 'datetime']).reset_index(drop=True)
    df['sales_last_1h'] = df.groupby('item_name')['actual_sales'].shift(1)
    df['sales_yesterday_same_hour'] = df.groupby('item_name')['actual_sales'].shift(24)
    df['sales_last_week_same_hour'] = df.groupby('item_name')['actual_sales'].shift(168)
    df['sales_next_hour'] = df.groupby('item_name')['actual_sales'].shift(-1)
    df = df.dropna().reset_index(drop=True)

    final_columns = [
        'item_name', 'datetime', 'hour', 'day_of_week', 'is_weekend', 'is_holiday',
        'freshness', 'inventory', 'price', 'temperature', 'is_rainy',
        'sales_last_1h', 'sales_yesterday_same_hour', 'sales_last_week_same_hour', 'sales_next_hour'
    ]
    df = df[final_columns]

    df_sorted = df.sort_values(by=['datetime', 'item_name']).reset_index(drop=True)
    train_df, test_df = train_test_split(df_sorted, test_size=0.2, shuffle=False)
    train_df = train_df.drop(columns=['datetime'])
    test_df = test_df.drop(columns=['datetime'])

    train_df.to_csv('xgboost_train_80.csv', index=False, encoding='utf-8-sig')
    test_df.to_csv('xgboost_test_20.csv', index=False, encoding='utf-8-sig')
    print("✅ 拆分完毕！模型训练的教科书已升级，AI 将学会动态价格弹性！")


if __name__ == "__main__":
    generate_and_split_ultimate_dataset()