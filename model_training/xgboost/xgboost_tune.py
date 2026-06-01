import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import RandomizedSearchCV
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import joblib
import matplotlib.pyplot as plt

# 解决 matplotlib 中文显示问题 (针对 Windows)
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


def tune_and_train_xgboost():
    print("1. 正在加载数据集...")
    try:
        train_df = pd.read_csv('xgboost_train_80.csv')
        test_df = pd.read_csv('xgboost_test_20.csv')
    except FileNotFoundError:
        print("错误：找不到数据集，请确认 csv 文件在同目录下。")
        return

    train_df['item_name'] = train_df['item_name'].astype('category')
    test_df['item_name'] = test_df['item_name'].astype('category')

    target_col = 'sales_next_hour'
    X_train = train_df.drop(columns=[target_col])
    y_train = train_df[target_col]
    X_test = test_df.drop(columns=[target_col])
    y_test = test_df[target_col]

    print("\n2. 正在启动自动化超参数寻优 (RandomizedSearchCV)...")
    print("   AI 正在尝试各种参数组合，请稍候 1-2 分钟...")

    param_dist = {
        'max_depth': [4, 5, 6, 7, 8],
        'learning_rate': [0.01, 0.05, 0.1, 0.15],
        'n_estimators': [100, 200, 300, 400],
        'subsample': [0.7, 0.8, 0.9],
        'colsample_bytree': [0.7, 0.8, 0.9],
        'min_child_weight': [1, 3, 5]
    }

    base_model = xgb.XGBRegressor(
        enable_categorical=True,
        tree_method='hist',
        random_state=42
    )

    random_search = RandomizedSearchCV(
        estimator=base_model,
        param_distributions=param_dist,
        n_iter=20,
        scoring='neg_mean_squared_error',
        cv=3,
        verbose=1,
        random_state=42,
        n_jobs=-1
    )

    random_search.fit(X_train, y_train)

    print("\n🎉 寻优结束！找到的最优参数组合如下：")
    best_params = random_search.best_params_
    for key, value in best_params.items():
        print(f"   - {key}: {value}")

    print("\n3. 正在使用最优参数重新训练最终模型...")
    final_model = xgb.XGBRegressor(
        enable_categorical=True,
        tree_method='hist',
        random_state=42,
        **best_params
    )

    final_model.fit(
        X_train, y_train,
        eval_set=[(X_train, y_train), (X_test, y_test)],
        verbose=50
    )

    print("\n4. 正在评估最终优化版模型...")
    y_pred = final_model.predict(X_test)
    y_pred = np.maximum(0, y_pred)

    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    print("-" * 40)
    print(f"优化后测试集 RMSE: {rmse:.4f} kg")
    print(f"优化后测试集 MAE : {mae:.4f} kg")
    print(f"优化后测试集 R²  : {r2:.4f}")
    print("-" * 40)

    print("\n5. 正在生成图表并保存模型...")

    # ================= 1. 损失曲线图 =================
    results = final_model.evals_result()
    plt.figure(figsize=(10, 5))
    plt.plot(results['validation_0']['rmse'], label='Train RMSE', color='#1890ff')
    plt.plot(results['validation_1']['rmse'], label='Test RMSE', color='#f5222d', linestyle='--')
    plt.legend()
    plt.title('优化后 XGBoost 模型训练误差下降曲线')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.savefig('training_loss_curve_optimized.png', dpi=300)

    # ================= 2. 拟合对比图 =================
    plt.figure(figsize=(14, 6))
    plt.plot(y_test.values[:120], label='真实销量', color='#a0d911', marker='o', markersize=4)
    plt.plot(y_pred[:120], label='预测销量', color='#722ed1', marker='x', markersize=4)
    plt.fill_between(range(120), y_test.values[:120], y_pred[:120], color='gray', alpha=0.1)
    plt.title(f'优化后预测准确性展示 (R²={r2:.4f})')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.savefig('prediction_accuracy_curve_optimized.png', dpi=300)

    # ================= 3. 特征重要性图 (🌟 补全这里) =================
    feature_importances = final_model.feature_importances_
    features = X_train.columns

    importance_df = pd.DataFrame({
        'Feature': features,
        'Importance': feature_importances
    }).sort_values(by='Importance', ascending=True)

    plt.figure(figsize=(10, 6))
    plt.barh(importance_df['Feature'], importance_df['Importance'], color='#36cfc9')
    plt.title('优化后 XGBoost 模型特征重要性分析 (销量驱动核心因素)')
    plt.xlabel('重要性得分 (Gain)')
    plt.tight_layout()
    plt.savefig('feature_importance_optimized.png', dpi=300)
    print("✅ 特征重要性图已保存为 'feature_importance_optimized.png'")

    # ================= 4. 保存最终模型 =================
    model_filename = 'xgboost_sales_model_optimized.pkl'
    joblib.dump(final_model, model_filename)
    print(f"✅ 模型已成功保存至: {model_filename}")


if __name__ == "__main__":
    tune_and_train_xgboost()