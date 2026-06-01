import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import joblib
import matplotlib.pyplot as plt

# 解决 matplotlib 中文显示问题 (针对 Windows)
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


def train_and_evaluate_xgboost():
    print("1. 正在加载训练集和测试集...")
    try:
        train_df = pd.read_csv('xgboost_train_80.csv')
        test_df = pd.read_csv('xgboost_test_20.csv')
    except FileNotFoundError:
        print("错误：找不到数据集，请确保 csv 文件与本脚本在同一目录下。")
        return

    # 2. 数据预处理
    train_df['item_name'] = train_df['item_name'].astype('category')
    test_df['item_name'] = test_df['item_name'].astype('category')

    target_col = 'sales_next_hour'

    X_train = train_df.drop(columns=[target_col])
    y_train = train_df[target_col]
    X_test = test_df.drop(columns=[target_col])
    y_test = test_df[target_col]

    print(f"训练集特征维度: {X_train.shape}")
    print(f"测试集特征维度: {X_test.shape}")

    # 3. 初始化 XGBoost 模型
    print("\n2. 正在初始化并训练 XGBoost 模型...")
    model = xgb.XGBRegressor(
        enable_categorical=True,
        tree_method='hist',
        n_estimators=200,
        learning_rate=0.05,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_train, y_train), (X_test, y_test)],
        verbose=50
    )
    print("模型训练完成！")

    # 4. 生成并保存训练误差下降曲线图 (Loss Curve)
    print("\n3. 正在生成训练误差 (Loss) 下降曲线图...")
    results = model.evals_result()
    epochs = len(results['validation_0']['rmse'])
    x_axis = range(0, epochs)

    plt.figure(figsize=(10, 5))
    plt.plot(x_axis, results['validation_0']['rmse'], label='Train RMSE (训练集误差)', color='#1890ff', linewidth=2)
    plt.plot(x_axis, results['validation_1']['rmse'], label='Test RMSE (测试集误差)', color='#f5222d', linewidth=2,
             linestyle='--')
    plt.legend()
    plt.title('XGBoost 模型训练误差 (RMSE) 下降曲线')
    plt.xlabel('迭代次数 (Boosting Rounds)')
    plt.ylabel('均方根误差 RMSE')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig('training_loss_curve.png', dpi=300)
    print("✅ 训练误差图已保存为 'training_loss_curve.png'")

    # 5. 模型量化评估
    print("\n4. 正在评估模型最终性能...")
    y_pred = model.predict(X_test)
    y_pred = np.maximum(0, y_pred)  # 防止预测出现负数

    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)  # 🌟 新增：决定系数（代表准确性拟合优度）

    print("-" * 40)
    print(f"测试集 RMSE (均方根误差): {rmse:.4f} kg")
    print(f"测试集 MAE  (平均绝对误差): {mae:.4f} kg")
    print(f"测试集 R²   (模型准确性/拟合优度): {r2:.4f} (越接近1越准确)")
    print("-" * 40)

    # ==========================================
    # 🌟 新增核心：生成“预测准确性拟合对比图”
    # 这是回归模型论文中最核心的“准确性”图表
    # ==========================================
    print("\n5. 正在生成模型预测准确性拟合对比图...")
    # 为了图表展示清晰，我们随机截取测试集中的 120 个连续时序样本
    sample_size = 120
    y_test_sample = y_test.values[:sample_size]
    y_pred_sample = y_pred[:sample_size]

    plt.figure(figsize=(14, 6))
    plt.plot(y_test_sample, label='真实销量 (Actual Sales)', color='#a0d911', marker='o', markersize=4, linewidth=2,
             alpha=0.8)
    plt.plot(y_pred_sample, label='AI 预测销量 (Predicted Sales)', color='#722ed1', marker='x', markersize=4,
             linewidth=2, alpha=0.8)

    plt.fill_between(range(sample_size), y_test_sample, y_pred_sample, color='gray', alpha=0.1,
                     label='误差区间 (Error Margin)')

    plt.title(f'XGBoost 模型销量预测准确性展示 (局部时序样本, R²={r2:.4f})')
    plt.xlabel('测试集时序样本点 (Time Series Samples)')
    plt.ylabel('果蔬销量 (kg)')
    plt.legend(loc='upper right')
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig('prediction_accuracy_curve.png', dpi=300)
    print("✅ 准确性拟合对比图已保存为 'prediction_accuracy_curve.png'")
    # ==========================================

    # 6. 特征重要性分析
    print("\n6. 正在生成特征重要性图表...")
    feature_importances = model.feature_importances_
    features = X_train.columns

    importance_df = pd.DataFrame({
        'Feature': features,
        'Importance': feature_importances
    }).sort_values(by='Importance', ascending=True)

    plt.figure(figsize=(10, 6))
    plt.barh(importance_df['Feature'], importance_df['Importance'], color='#36cfc9')
    plt.title('XGBoost 模型特征重要性分析 (销量预测驱动因素)')
    plt.xlabel('重要性得分 (Gain)')
    plt.tight_layout()
    plt.savefig('feature_importance.png', dpi=300)
    print("✅ 特征重要性图表已保存为 'feature_importance.png'")

    # 7. 保存训练好的模型
    model_filename = 'xgboost_sales_model.pkl'
    joblib.dump(model, model_filename)
    print(f"\n7. 模型已成功保存至: {model_filename}")


if __name__ == "__main__":
    train_and_evaluate_xgboost()