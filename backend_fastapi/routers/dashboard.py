# backend_fastapi/routers/dashboard.py
from fastapi import APIRouter
import pandas as pd
import numpy as np
import joblib
import requests
import chinese_calendar as lunar
from core.database import engine
from core.inventory_schema import ensure_inventory_schema
from core.pricing_optimizer import optimize_sales_volume_price
import traceback
from time import monotonic

router = APIRouter(prefix="/api/dashboard", tags=["大屏看板与预测"])

MODEL_PATH = r'D:\pycharmProjects\fruit_recognition_system\model_training\xgboost\xgboost_sales_model.pkl'
try:
    model = joblib.load(MODEL_PATH)
    print("XGBoost model loaded successfully.")
except FileNotFoundError:
    print(f"Model file not found: {MODEL_PATH}, please check the path.")
    model = None

FEATURE_COLUMNS = [
    'item_name', 'hour', 'day_of_week', 'is_weekend', 'is_holiday',
    'freshness', 'inventory', 'price', 'temperature', 'is_rainy',
    'sales_last_1h', 'sales_yesterday_same_hour', 'sales_last_week_same_hour'
]

# 🌟 1. 设立果蔬永远不变的“基准价锚点”
BASE_PRICE_MAP = {
    '土豆': 4.0, '西瓜': 6.0, '黄瓜': 7.0, '西红柿': 9.0,
    '香蕉': 8.0, '苹果': 12.0, '芒果': 15.0, '葡萄': 20.0, '草莓': 40.0
}

TRAIN_CATEGORIES = ['土豆', '芒果', '苹果', '草莓', '葡萄', '西瓜', '西红柿', '香蕉', '黄瓜']
FRUIT_CATEGORIES = TRAIN_CATEGORIES
WEATHER_CACHE_TTL_SECONDS = 600.0
_weather_cache = {"updated_at": 0.0, "data": None}


def predict_sales_with_xgboost(feature_dict):
    """Run one XGBoost sales forecast with the supplied candidate price."""
    if model is None:
        return 0.0

    df_features = pd.DataFrame([feature_dict])[FEATURE_COLUMNS]
    df_features['item_name'] = pd.Categorical(
        df_features['item_name'],
        categories=TRAIN_CATEGORIES,
    )
    return max(0.0, float(model.predict(df_features)[0]))


def predict_sales_batch_with_xgboost(feature_dicts):
    """Run candidate-price forecasts in one model call to keep the API responsive."""
    if model is None or not feature_dicts:
        return []

    df_features = pd.DataFrame(feature_dicts)[FEATURE_COLUMNS]
    df_features['item_name'] = pd.Categorical(
        df_features['item_name'],
        categories=TRAIN_CATEGORIES,
    )
    return [max(0.0, float(value)) for value in model.predict(df_features)]


def fetch_real_weather_24h():
    now = monotonic()
    if _weather_cache["data"] is not None and now - _weather_cache["updated_at"] < WEATHER_CACHE_TTL_SECONDS:
        return _weather_cache["data"]

    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {"latitude": 39.9042, "longitude": 116.4074, "hourly": ["temperature_2m", "precipitation_probability"],
                  "timezone": "Asia/Shanghai", "forecast_days": 2}
        response = requests.get(url, params=params, timeout=1.2).json()
        weather_dict = {}
        for t, temp, precip in zip(response['hourly']['time'], response['hourly']['temperature_2m'],
                                   response['hourly']['precipitation_probability']):
            weather_dict[t.replace('T', ' ')] = {'temp': temp, 'rainy': 1 if precip > 30 else 0}
        _weather_cache["updated_at"] = now
        _weather_cache["data"] = weather_dict
        return weather_dict
    except:
        return None


@router.get("/sales_and_pricing")
def get_sales_and_pricing():
    predictions = {}
    pricing_strategy = []
    now = pd.Timestamp.now(tz='Asia/Shanghai').tz_localize(None).floor('h')
    future_hours = [now + pd.Timedelta(hours=i) for i in range(1, 25)]
    date_strings = [dt.strftime('%m-%d %H:00') for dt in future_hours]

    real_weather_data = fetch_real_weather_24h()
    future_conditions = []

    for dt in future_hours:
        check_date = dt.date()
        is_weekend = 1 if dt.dayofweek >= 5 else 0
        try:
            is_holiday = 1 if lunar.is_holiday(check_date) else 0
            if lunar.is_workday(check_date): is_holiday, is_weekend = 0, 0
        except:
            is_holiday = is_weekend
        dt_key = dt.strftime('%Y-%m-%d %H:00')
        if real_weather_data and dt_key in real_weather_data:
            temp_forecast = real_weather_data[dt_key]['temp']
            rain_forecast = real_weather_data[dt_key]['rainy']
        else:
            temp_forecast = round(22 + 6 * np.sin((dt.hour - 8) * np.pi / 12), 1)
            rain_forecast = 1 if np.random.rand() < 0.1 else 0
        future_conditions.append(
            {'hour': dt.hour, 'day_of_week': dt.dayofweek, 'temperature': temp_forecast, 'is_rainy': rain_forecast,
             'is_weekend': is_weekend, 'is_holiday': is_holiday})

    try:
        ensure_inventory_schema()
        df_inventory = pd.read_sql('SELECT * FROM fruit_inventory', con=engine)
        df_history = pd.read_sql('SELECT * FROM fruit_sales_history', con=engine)
        df_history['datetime'] = pd.to_datetime(df_history['datetime'])
    except Exception as e:
        return {"error": "Database connection failed"}

    for item in FRUIT_CATEGORIES:
        inv_row = df_inventory[df_inventory['item_name'] == item]
        if inv_row.empty: continue

        current_inventory = float(inv_row.iloc[0]['inventory'])
        current_price = float(inv_row.iloc[0]['price'])
        cost_price = float(inv_row.iloc[0]['cost_price'])
        current_freshness = float(inv_row.iloc[0]['freshness'])

        item_history = df_history[df_history['item_name'] == item].set_index('datetime')
        last_1h_sales = float(item_history.iloc[-1]['actual_sales']) if not item_history.empty else 0.0

        base_p = BASE_PRICE_MAP.get(item, 10.0)
        best_price, best_sales_pred = current_price, 0.0
        floor_price = cost_price
        inventory_policy = "模型不可用，暂时保持当前售价"

        if model is not None and item in TRAIN_CATEGORIES:
            try:
                weather_0, target_time_0 = future_conditions[0], future_hours[0]
                yesterday_time_0, last_week_time_0 = target_time_0 - pd.Timedelta(days=1), target_time_0 - pd.Timedelta(
                    days=7)
                sales_yesterday_0 = float(item_history.loc[
                                              yesterday_time_0, 'actual_sales']) if yesterday_time_0 in item_history.index else last_1h_sales
                sales_last_week_0 = float(item_history.loc[
                                              last_week_time_0, 'actual_sales']) if last_week_time_0 in item_history.index else last_1h_sales

                feature_context = {
                    "item_name": item, "hour": weather_0['hour'], "day_of_week": weather_0['day_of_week'],
                    "is_weekend": weather_0['is_weekend'], "is_holiday": weather_0['is_holiday'],
                    "freshness": current_freshness, "inventory": current_inventory, "price": current_price,
                    "temperature": weather_0['temperature'], "is_rainy": weather_0['is_rainy'],
                    "sales_last_1h": last_1h_sales, "sales_yesterday_same_hour": sales_yesterday_0,
                    "sales_last_week_same_hour": sales_last_week_0
                }

                def predict_candidate_sales(candidate_price):
                    return predict_sales_with_xgboost(
                        {**feature_context, "price": candidate_price}
                    )

                def predict_candidate_sales_batch(candidate_prices):
                    return predict_sales_batch_with_xgboost([
                        {**feature_context, "price": candidate_price}
                        for candidate_price in candidate_prices
                    ])

                recommendation = optimize_sales_volume_price(
                    current_price=current_price,
                    cost_price=cost_price,
                    inventory=current_inventory,
                    freshness=current_freshness,
                    market_anchor_price=base_p,
                    predict_sales=predict_candidate_sales,
                    predict_sales_batch=predict_candidate_sales_batch,
                )
                best_price = recommendation.suggested_price
                best_sales_pred = recommendation.predicted_sales
                floor_price = recommendation.floor_price
                inventory_policy = recommendation.policy
            except Exception as e:
                print(f"Optimization error for '{item}': {e}")

        if current_price < floor_price:
            status, reason = "up", f"当前售价低于库存策略止损底价 ¥{floor_price:.2f}，建议立即上调。"
        elif best_price > current_price + 0.1:
            status, reason = "up", f"建议售价 ¥{best_price:.2f} 仍可达到最大预测销量 {best_sales_pred:.1f}kg，同时减少不必要让利。"
        elif best_price < current_price - 0.1:
            status, reason = "down", f"下调至 ¥{best_price:.2f} 可达到最大预测销量 {best_sales_pred:.1f}kg，且不低于止损底价 ¥{floor_price:.2f}。"
        else:
            status, reason = "normal", f"当前售价已能达到最大预测销量 {best_sales_pred:.1f}kg，无需调价。"
        reason = f"{reason} {inventory_policy}。"

        pricing_strategy.append(
            {"name": item, "base_price": round(current_price, 2), "suggested_price": round(best_price, 2),
             "cost_price": round(cost_price, 2), "floor_price": round(floor_price, 2),
             "predicted_sales": round(best_sales_pred, 2), "reason": reason, "status": status})

        hourly_sales_pred = []
        if model is not None and item in TRAIN_CATEGORIES:
            try:
                temp_inventory, temp_freshness, temp_last_1h = current_inventory, current_freshness, last_1h_sales
                for i in range(24):
                    weather, target_time = future_conditions[i], future_hours[i]
                    yesterday_time, last_week_time = target_time - pd.Timedelta(days=1), target_time - pd.Timedelta(
                        days=7)
                    if weather['hour'] == 6: temp_inventory, temp_freshness = 300.0, 1.0
                    sales_yesterday = float(item_history.loc[
                                                yesterday_time, 'actual_sales']) if yesterday_time in item_history.index else temp_last_1h
                    sales_last_week = float(item_history.loc[
                                                last_week_time, 'actual_sales']) if last_week_time in item_history.index else temp_last_1h

                    feature_dict = {
                        "item_name": item, "hour": weather['hour'], "day_of_week": weather['day_of_week'],
                        "is_weekend": weather['is_weekend'], "is_holiday": weather['is_holiday'],
                        "freshness": temp_freshness, "inventory": temp_inventory, "price": current_price,
                        "temperature": weather['temperature'], "is_rainy": weather['is_rainy'],
                        "sales_last_1h": temp_last_1h, "sales_yesterday_same_hour": sales_yesterday,
                        "sales_last_week_same_hour": sales_last_week
                    }
                    pred_val = predict_sales_with_xgboost(feature_dict)
                    pred_val = min(pred_val, temp_inventory)

                    hourly_sales_pred.append(round(pred_val, 2))
                    temp_last_1h, temp_inventory = pred_val, max(0.0, temp_inventory - pred_val)
                    temp_freshness = max(0.1, temp_freshness - 0.005)
            except Exception as e:
                for i in range(24): hourly_sales_pred.append(max(0, int(temp_last_1h * 0.8 + np.random.normal(0, 0.5))))

        predictions[item] = hourly_sales_pred if hourly_sales_pred else [0] * 24

    return {"dates": date_strings, "sales_predictions": predictions, "pricing_strategy": pricing_strategy}


# =======================================================
# 🌟 全新追加：数字监控中心 API (与交易表、库存表、历史销量表 100% 真实联动)
# =======================================================
@router.get("/advanced_monitor")
def get_advanced_monitor():
    try:
        # 1. 真实查库：今日交易额与订单数（限正常单 tag=0）
        query_sales = """
            SELECT SUM(pay_amount) as total_sales, COUNT(transaction_id) as total_orders
            FROM transaction 
            WHERE DATE(creat_at) = CURDATE() AND tag = 0
        """
        try:
            df_sales = pd.read_sql(query_sales, con=engine)
            today_sales = float(df_sales['total_sales'].fillna(0).iloc[0])
            today_orders = int(df_sales['total_orders'].fillna(0).iloc[0])
        except:
            today_sales, today_orders = 0.0, 0

        # 2. 真实查库：商品库存与新鲜度，用于智能建议
        try:
            ensure_inventory_schema()
            df_inv = pd.read_sql(
                'SELECT item_name, price, cost_price, inventory, freshness FROM fruit_inventory',
                con=engine,
            )
        except:
            df_inv = pd.DataFrame()

        alerts, pricing = [], []
        sales_pricing_payload = get_sales_and_pricing()
        strategy_by_name = {
            item['name']: item
            for item in sales_pricing_payload.get('pricing_strategy', [])
        }
        if not df_inv.empty:
            for _, row in df_inv.iterrows():
                name, price = row['item_name'], float(row['price'])
                inv, fresh = float(row['inventory']), float(row['freshness'])

                if inv < 15:
                    alerts.append({"name": name, "status": "畅销紧缺", "color": "blue", "current": inv, "max": 50,
                                   "percent": (inv / 50) * 100})
                elif inv > 35 and fresh < 0.6:
                    alerts.append({"name": name, "status": "积压警告", "color": "yellow", "current": inv, "max": 50,
                                   "percent": (inv / 50) * 100})

                strategy = strategy_by_name.get(name)
                if strategy and abs(float(strategy['suggested_price']) - price) > 0.01:
                    new_price = float(strategy['suggested_price'])
                    change_percent = ((new_price - price) / price * 100.0) if price else 0.0
                    pricing.append({
                        "name": name,
                        "tag": "XGBoost 走量优化",
                        "tag_color": "green" if change_percent >= 0 else "red",
                        "old_price": price,
                        "new_price": new_price,
                        "discount": f"{change_percent:+.1f}%",
                        "reason": strategy['reason'],
                    })
        else:
            alerts = [{"name": "苹果", "status": "畅销", "color": "blue", "current": 12, "max": 50, "percent": 24}]
            pricing = []

        # 3. 🌟 真实查库：历史销量图表 (动态获取分类，彻底告别写死)
        try:
            df_history = pd.read_sql('SELECT item_name, actual_sales, datetime FROM fruit_sales_history', con=engine)
            if not df_history.empty:
                # 动态提取所有真实的种类（自动去重）
                real_fruits = df_history['item_name'].dropna().unique().tolist()
            else:
                real_fruits = []
        except:
            df_history = pd.DataFrame()
            real_fruits = []

        history_chart = {}
        # 将动态获取的真实果蔬种类组合进目标列表
        target_fruits = ['all'] + real_fruits
        now = pd.Timestamp.now()

        # 生成标准的 X轴 时间节点
        last_7_days = [(now - pd.Timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
        last_6_months = [(now - pd.DateOffset(months=i)).strftime('%Y-%m') for i in range(5, -1, -1)]
        hours_list = [f"{i:02d}:00" for i in range(8, 23)]  # 早上8点到晚上10点

        # 初始化图表数据结构
        for f in target_fruits:
            history_chart[f] = {
                "hour": {"x": hours_list, "y": [0] * len(hours_list)},
                "day": {"x": [d[5:] for d in last_7_days], "y": [0] * len(last_7_days)},
                "month": {"x": last_6_months, "y": [0] * len(last_6_months)}
            }

        # 利用 Pandas 进行高性能的多维聚合运算
        if not df_history.empty:
            df_history['datetime'] = pd.to_datetime(df_history['datetime'])
            df_history['date'] = df_history['datetime'].dt.strftime('%Y-%m-%d')
            df_history['hour'] = df_history['datetime'].dt.strftime('%H:00')
            df_history['month'] = df_history['datetime'].dt.strftime('%Y-%m')

            for f in target_fruits:
                df_f = df_history if f == 'all' else df_history[df_history['item_name'] == f]

                if not df_f.empty:
                    # 统计今日各小时销量
                    df_f_today = df_f[df_f['datetime'].dt.date == now.date()]
                    hour_grouped = df_f_today.groupby('hour')['actual_sales'].sum().to_dict()
                    history_chart[f]['hour']['y'] = [float(hour_grouped.get(h, 0)) for h in hours_list]

                    # 统计近 7 天销量
                    day_grouped = df_f[df_f['date'].isin(last_7_days)].groupby('date')['actual_sales'].sum().to_dict()
                    history_chart[f]['day']['y'] = [float(day_grouped.get(d, 0)) for d in last_7_days]

                    # 统计近 6 个月销量
                    month_grouped = df_f[df_f['month'].isin(last_6_months)].groupby('month')[
                        'actual_sales'].sum().to_dict()
                    history_chart[f]['month']['y'] = [float(month_grouped.get(m, 0)) for m in last_6_months]

        return {
            "status": "success",
            "data": {
                "today_sales": today_sales,
                "today_orders": today_orders,
                "alerts": alerts[:3],
                "pricing": pricing[:2],
                "history_chart": history_chart  # 完美包含所有真实种类的聚合数据
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}
