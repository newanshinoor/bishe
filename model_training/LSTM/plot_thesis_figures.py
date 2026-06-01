import matplotlib.pyplot as plt
import numpy as np


# 为了防止图表中的中文变方块，这里尽量使用英文标签，这在中文论文的配图中也是非常专业和常见的。
def plot_multimodal_effect(time_steps, weight_data, feature_data, feature_name,
                           title, alert_frame, alert_text, save_name):
    """
    绘制双 Y 轴的多模态特征图，专门用于论文排版
    """
    fig, ax1 = plt.subplots(figsize=(10, 4.5))  # 适合 Word 插入的宽扁比例

    # --- 左侧 Y 轴：物理重量曲线 (蓝色实线) ---
    color_w = '#1f77b4'
    ax1.set_xlabel('Time (Frames)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Physical Weight (g)', color=color_w, fontsize=12, fontweight='bold')
    ax1.plot(time_steps, weight_data, color=color_w, linewidth=2.5, label='Weight')
    ax1.tick_params(axis='y', labelcolor=color_w)
    ax1.grid(True, linestyle='--', alpha=0.6)

    # --- 右侧 Y 轴：视觉/次生特征曲线 (红色或绿色虚线) ---
    ax2 = ax1.twinx()
    color_f = '#d62728' if 'Diff' in feature_name else '#2ca02c'
    ax2.set_ylabel(feature_name, color=color_f, fontsize=12, fontweight='bold')
    ax2.plot(time_steps, feature_data, color=color_f, linestyle='-.', linewidth=2.5, label=feature_name)
    ax2.tick_params(axis='y', labelcolor=color_f)

    # --- 标注作弊判定点 (红色虚线框) ---
    if alert_frame:
        plt.axvline(x=alert_frame, color='red', linestyle='--', linewidth=2)
        # 根据特征数据的高度动态调整文本位置
        y_pos = max(feature_data) * 0.8 if max(feature_data) > 0 else min(feature_data) * 0.8
        if y_pos == 0: y_pos = 0.5
        plt.text(alert_frame + 1.5, y_pos, f'[{alert_text}]', color='red',
                 fontsize=11, fontweight='bold', bbox=dict(facecolor='white', alpha=0.7, edgecolor='none'))

    plt.title(title, fontsize=14, pad=15)
    fig.tight_layout()
    plt.savefig(f'{save_name}.png', dpi=300, bbox_inches='tight')  # 300dpi 高清打印级别
    print(f"✅ 成功生成论文配图: {save_name}.png")
    plt.close()


# ==================== 1. 快速替换 (Rapid Swap) ====================
def generate_swap_plot():
    time = np.arange(60)
    # 模拟重量: 初始 1000g -> 瞬间抽走变 200g -> 砸下替换物冲到 800g -> 稳定在 600g
    weight = np.full(60, 1000.0)
    weight[20:25] = np.linspace(1000, 200, 5)  # 抽走
    weight[25:30] = np.linspace(200, 800, 5)  # 砸下冲击
    weight[30:] = 600.0 + np.random.normal(0, 2, 30)

    # 增加底层底噪
    weight += np.random.normal(0, 1.5, 60)

    # 计算重量变化率 (Weight Diff)
    weight_diff = np.diff(weight, prepend=weight[0])

    plot_multimodal_effect(time, weight, weight_diff, 'Weight Diff (g/frame)',
                           'Fig 5-20: Multimodal Features of Rapid Swap',
                           alert_frame=26, alert_text='Warning: Swap Impact!',
                           save_name='thesis_fig_swap')


# ==================== 2. 部分遮挡 (Partial Occlusion) ====================
def generate_occlusion_plot():
    time = np.arange(60)
    # 模拟重量: 1000g，由于手部压迫，出现不规则轻微波动，但没有大幅下降
    weight = np.full(60, 1000.0)
    weight[15:50] += np.random.normal(0, 15, 35)  # 遮挡期间手压秤盘的噪音
    weight[50:] = 850.0 + np.random.normal(0, 2, 10)
    weight += np.random.normal(0, 1.5, 60)

    # 模拟视觉特征 (遮挡比例): 从 0 迅速攀升至高位平台期
    occlusion = np.zeros(60)
    occlusion[12:18] = np.linspace(0, 0.88, 6)
    occlusion[18:50] = np.random.uniform(0.85, 0.95, 32)  # 高位平台期
    occlusion[50:55] = np.linspace(0.88, 0, 5)

    plot_multimodal_effect(time, weight, occlusion, 'Occlusion Ratio (0-1)',
                           'Fig 5-21: Multimodal Features of Partial Occlusion',
                           alert_frame=30, alert_text='Warning: High Occlusion!',
                           save_name='thesis_fig_occlusion')


# ==================== 3. 恶意托底 (Malicious Bottom-Dragging) ====================
def generate_drag_plot():
    time = np.arange(60)
    # 模拟重量: 初始 1000g，顾客用手托底导致重量减轻，伴随【肌肉高频震颤】
    weight = np.full(60, 1000.0)
    weight[20:55] = 600.0  # 托举使得重量减轻 400g
    # 模拟肌肉震颤：使用高频的正弦波加上白噪声
    tremor = np.sin(np.linspace(0, 50, 35)) * 25 + np.random.normal(0, 5, 35)
    weight[20:55] += tremor
    weight += np.random.normal(0, 1.5, 60)

    # 模拟视觉特征 (模拟深度 dist): 手部贴近秤盘边缘，距离极近
    dist = np.full(60, 0.8)  # 正常距离
    dist[15:20] = np.linspace(0.8, 0.1, 5)
    dist[20:55] = np.random.uniform(0.05, 0.15, 35)  # 极近的贴合距离
    dist[55:60] = np.linspace(0.1, 0.8, 5)

    plot_multimodal_effect(time, weight, dist, 'Hand Distance (Normalized)',
                           'Fig 5-22: Multimodal Features of Bottom-Dragging',
                           alert_frame=35, alert_text='Warning: Tremor Force Detected!',
                           save_name='thesis_fig_drag')


if __name__ == "__main__":
    print("🚀 正在生成论文高清配图...")
    generate_swap_plot()
    generate_occlusion_plot()
    generate_drag_plot()
    print("🎉 全部完成！请查看当前目录下的 .png 文件。")