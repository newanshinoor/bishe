<template>
  <div class="admin-layout">
    <aside class="sidebar">
      <h2 class="logo">系统运营后台</h2>
      <ul class="nav-menu">
        <li :class="{ active: activeTab === 'dashboard' }" @click="switchTab('dashboard')">销量预测</li>
        <li :class="{ active: activeTab === 'commodities' }" @click="switchTab('commodities')">商品管理</li>
        <li :class="{ active: activeTab === 'orders' }" @click="switchTab('orders')">订单流水记录</li>
        <li :class="{ active: activeTab === 'alarms' }" @click="switchTab('alarms')">🚨 违规报警日志</li>
        <li :class="{ active: activeTab === 'monitor' }" @click="switchTab('monitor')">数字大屏(新)</li>
      </ul>
    </aside>

    <main class="content" :class="{ 'monitor-bg': activeTab === 'monitor' }">
      <header class="top-nav" v-if="activeTab !== 'monitor'">
        <h1>
          {{ activeTab === 'dashboard' ? '销售与运营仪表盘' :
             activeTab === 'commodities' ? '商品档案与库存管理' :
             activeTab === 'alarms' ? 'LSTM 监控报警中心' : '订单流水与异常行为检测' }}
        </h1>
        <div class="user-info">管理员：饶程</div>
      </header>

      <div v-show="activeTab === 'dashboard'" class="tab-content">
        <div class="dashboard-header-row">
          <h3 class="section-title">今日 AI 动态定价建议 (基于 XGBoost)</h3>
          <div class="fruit-tabs">
            <button v-for="item in pricingList" :key="item.name" :class="['tab-btn', { active: selectedFruit === item.name }]" @click="togglePricingCard(item.name)">
              {{ item.name }}
              <span v-if="item.status === 'up'" class="dot up"></span><span v-if="item.status === 'down'" class="dot down"></span>
            </button>
          </div>
        </div>
        <transition name="slide-fade" mode="out-in">
          <div v-if="selectedFruit && currentPricingItem" class="single-pricing-card" :key="selectedFruit">
            <div class="pricing-card">
              <div class="card-header">
                <h4>{{ currentPricingItem.name }} 定价策略</h4>
                <span :class="['status-badge', currentPricingItem.status]">{{ currentPricingItem.status === 'up' ? '↗ 建议涨价' : currentPricingItem.status === 'down' ? '↘ 建议降价' : '→ 维持原价' }}</span>
              </div>
              <div class="price-compare">
                <span class="old-price">当前价: ¥{{ currentPricingItem.base_price }}</span>
                <span class="new-price">AI建议价: ¥{{ currentPricingItem.suggested_price }}</span>
              </div>
              <p class="reason">{{ currentPricingItem.reason }}</p>
              <div class="price-adjust">
                <span class="currency">¥</span>
                <input type="number" v-model="currentPricingItem.manualPrice" step="0.1" class="price-input" />
                <button @click="applyPrice(currentPricingItem)" class="btn-apply">保存调价</button>
                <button @click="selectedFruit = null" class="btn-close">收起</button>
              </div>
            </div>
          </div>
        </transition>
        <div class="dashboard-panels">
          <div class="panel chart-panel">
            <h3 class="section-title">未来 24 小时逐小时销量预测 (XGBoost 实时反馈模拟)</h3>
            <div ref="chartRef" class="echarts-container"></div>
          </div>
        </div>
      </div>

      <div v-if="activeTab === 'commodities'" class="tab-content">
        <div class="table-card">
          <div class="table-header-actions">
            <h3>果蔬实时库存状态表</h3><button class="btn-success" @click="fetchCommodities">↻ 刷新数据</button>
          </div>
          <table class="styled-table">
            <thead>
              <tr><th>商品名称</th><th>基础定价 (¥/kg)</th><th>当前库存 (kg)</th><th>新鲜度 (0-1)</th><th>库存状态</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in commodityList" :key="item.item_name">
                <td style="font-weight: bold;">{{ item.item_name }}</td>
                <td>¥{{ item.price.toFixed(2) }}</td>
                <td>{{ item.inventory.toFixed(2) }} kg</td>
                <td><div class="progress-bar"><div class="progress-fill" :style="{ width: (item.freshness * 100) + '%', backgroundColor: item.freshness > 0.6 ? '#4CAF50' : '#f44336' }"></div></div>{{ item.freshness.toFixed(2) }}</td>
                <td><span class="stock-badge" :class="item.inventory > 20 ? 'stock-ok' : 'stock-low'">{{ item.inventory > 20 ? '库存充足' : '需尽快补货' }}</span></td>
                <td><button class="btn-edit" @click="openEditModal(item)">编辑 / 补货</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="activeTab === 'orders'" class="tab-content">
        <div class="table-card">
          <div class="table-header-actions">
            <h3>无人货柜交易流水记录</h3>
            <div class="filter-actions">
              <label style="margin-right: 10px; font-size: 14px; font-weight: bold;">防作弊行为筛选：</label>
              <select v-model="filterTag" @change="fetchOrders" class="tag-select">
                <option value="">全部流水</option><option value="0">✅ 正常交易</option><option value="1">⚠️ 换货作弊</option><option value="2">🚫 遮挡作弊</option>
              </select>
              <button class="btn-success" @click="fetchOrders">↻ 刷新</button>
            </div>
          </div>
          <table class="styled-table">
            <thead><tr><th>流水单号 (UUID)</th><th>商品名称</th><th>计费重量</th><th>顾客实付</th><th>预估利润</th><th>防作弊行为标签</th><th>入库时间</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="order in orderList" :key="order.transaction_id">
                <td class="font-mono text-xs">{{ order.transaction_id }}</td><td style="font-weight: bold;">{{ order.product_name }}</td><td class="text-weight">{{ order.total_amount.toFixed(2) }} kg</td><td class="text-price">¥{{ order.pay_amount.toFixed(2) }}</td><td style="color: #52c41a;">¥{{ order.profit.toFixed(2) }}</td>
                <td><span :class="['status-tag', getTagClass(order.tag)]">{{ getTagText(order.tag) }}</span></td>
                <td style="color: #888; font-size: 13px;">{{ order.creat_at }}</td>
                <td><div class="action-buttons"><button v-if="order.tag !== 0" class="btn-action success" @click="updateTag(order.transaction_id, 0)">复核正常</button><button v-if="order.tag === 0" class="btn-action warn" @click="updateTag(order.transaction_id, 1)">标异常</button><button class="btn-action danger" @click="deleteOrder(order.transaction_id)">删除</button></div></td>
              </tr>
              <tr v-if="orderList.length === 0"><td colspan="8" style="text-align: center; padding: 40px; color: #999;">暂无数据</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="activeTab === 'alarms'" class="tab-content">
        <div class="table-card border-t-4 border-red-500">
          <div class="table-header-actions">
            <div>
              <h3 style="color: #cf1322; display: flex; align-items: center; gap: 8px;">
                <span class="inline-block w-3 h-3 bg-red-500 rounded-full animate-pulse"></span>
                LSTM 模型违规动作报警日志
              </h3>
              <p style="font-size: 13px; color: #888; margin-top: 5px;">记录柜端所有的非正常换货、遮挡等行为及图像证据。</p>
            </div>
            <button class="btn-success" @click="fetchAlarms">↻ 刷新日志</button>
          </div>

          <table class="styled-table">
            <thead>
              <tr>
                <th>日志编号</th>
                <th>关联订单流水号</th>
                <th>违规异常类别</th>
                <th>LSTM 判定置信度</th>
                <th>发生时间</th>
                <th>证据操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="alarm in alarmList" :key="alarm.log_id">
                <td style="font-weight: bold;"># {{ alarm.log_id }}</td>
                <td class="font-mono text-xs">{{ alarm.transaction_id }}</td>
                <td>
                  <span :class="['status-tag', alarm.violation_type.includes('换货') ? 'anomaly-swap' : 'anomaly-occlusion']">
                    {{ alarm.violation_type }}
                  </span>
                </td>
                <td class="font-bold text-red-500">
                  {{ (alarm.lstm_score * 100).toFixed(1) }} %
                </td>
                <td style="color: #888; font-size: 13px;">{{ alarm.creat_at }}</td>
                <td>
                  <button class="btn-action warn" @click="viewEvidence(alarm)">📸 查看抓拍证据</button>
                </td>
              </tr>
              <tr v-if="alarmList.length === 0">
                <td colspan="6" style="text-align: center; padding: 40px; color: #999;">当前系统治安良好，暂无报警记录</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-show="activeTab === 'monitor'" class="w-full text-white font-sans p-6 rounded-lg min-h-full">
        <header class="flex justify-between items-center mb-6 border-b border-gray-700 pb-4">
          <h1 class="text-2xl font-bold text-blue-400 tracking-wider">数字监控中心 - 历史数据与动态定价 <span class="inline-block w-2 h-2 bg-green-500 rounded-full animate-pulse ml-2"></span></h1>
          <div class="text-gray-300 text-sm flex items-center">管理员：饶程</div>
        </header>

        <div class="grid grid-cols-4 gap-6">
          <div class="col-span-3 space-y-6">
            <div class="grid grid-cols-3 gap-6">
              <div class="bg-[#242731] p-5 rounded-lg shadow-lg border border-gray-700">
                <div class="text-gray-400 text-sm mb-2">今日销售总额 (正常单)</div>
                <div class="text-3xl font-bold text-[#10b981]">¥ {{ (monitorData.today_sales || 0).toFixed(2) }}</div>
              </div>
              <div class="bg-[#242731] p-5 rounded-lg shadow-lg border border-gray-700">
                <div class="text-gray-400 text-sm mb-2">今日完成订单数</div>
                <div class="text-3xl font-bold text-[#3b82f6]">{{ monitorData.today_orders || 0 }} <span class="text-sm font-normal text-gray-500">单</span></div>
              </div>
              <div class="bg-[#242731] p-5 rounded-lg shadow-lg border border-gray-700 flex flex-col justify-center">
                <div class="text-gray-400 text-sm mb-3">库存动态预警</div>
                <div class="space-y-3">
                  <div v-for="(alert, idx) in monitorData.alerts" :key="idx">
                    <div class="flex justify-between text-xs mb-1">
                      <span>{{ alert.name }} ({{ alert.status }})</span>
                      <span :class="`text-${alert.color}-400`">{{ alert.current }}/{{ alert.max }} kg</span>
                    </div>
                    <div class="w-full bg-gray-700 rounded-full h-1.5"><div :class="`bg-${alert.color}-500 h-1.5 rounded-full`" :style="`width: ${alert.percent}%`"></div></div>
                  </div>
                </div>
              </div>
            </div>

            <div class="bg-[#242731] p-5 rounded-lg shadow-lg border border-gray-700">
              <div class="flex flex-wrap gap-4 justify-between items-center mb-6">
                <div class="flex items-center space-x-3">
                  <div class="text-gray-300 text-sm font-bold whitespace-nowrap">真实历史销量统计</div>
                  <select v-model="currentFruitKey" @change="updateMonitorChart" class="bg-[#1a1c23] text-gray-300 text-sm rounded border border-gray-600 px-3 py-1 outline-none focus:border-blue-500 transition cursor-pointer">
                    <option value="all">全部品类</option>
                    <option v-for="fruit in availableFruits" :key="fruit" :value="fruit">{{ fruit }}</option>
                  </select>
                </div>
                <div class="flex space-x-1 bg-[#1a1c23] p-1 rounded-lg border border-gray-700">
                  <button @click="changeTimeType('hour')" :class="timeBtnClass('hour')">按小时</button>
                  <button @click="changeTimeType('day')" :class="timeBtnClass('day')">按天</button>
                  <button @click="changeTimeType('month')" :class="timeBtnClass('month')">按月</button>
                </div>
              </div>
              <div ref="monitorChartRef" style="width: 100%; height: 320px;"></div>
            </div>
          </div>

          <div class="col-span-1 bg-[#242731] p-5 rounded-lg shadow-lg border border-indigo-900/50 flex flex-col relative">
            <div class="flex items-center justify-between mb-4 border-b border-gray-700 pb-3">
              <h2 class="text-indigo-400 font-bold text-lg">智能动态定价建议</h2>
              <span class="text-xs bg-indigo-900 text-indigo-200 px-2 py-1 rounded">辅助运营</span>
            </div>
            <div v-for="(item, idx) in monitorData.pricing" :key="idx" class="bg-[#2a2d36] p-4 rounded-lg mb-4 border border-gray-700">
              <div class="flex justify-between items-center mb-2">
                <span class="text-white font-bold text-lg">{{ item.name }}</span>
                <span :class="`text-xs bg-${item.tag_color}-900/50 text-${item.tag_color}-400 px-2 py-1 rounded`">{{ item.tag }}</span>
              </div>
              <div class="text-sm text-gray-300 mb-3 border-b border-gray-700 pb-2">建议售价: <span class="text-red-400 font-bold line-through">¥ {{ item.old_price.toFixed(2) }}</span> ➔ <span class="text-[#10b981] font-bold text-xl ml-1">¥ {{ item.new_price.toFixed(2) }}</span> <span class="text-xs text-gray-500">({{ item.discount }})</span></div>
              <div class="text-xs text-gray-400 leading-relaxed"><span class="text-indigo-400">业务解释：</span>{{ item.reason }}</div>
              <button @click="applyNewPrice(item)" class="mt-4 w-full bg-indigo-600 hover:bg-indigo-500 text-white py-2 rounded text-sm transition shadow">一键下发新价格</button>
            </div>
            <div v-if="monitorData.pricing.length === 0" class="text-center text-gray-500 mt-10">当前库存健康，无辅助降价建议。</div>
          </div>
        </div>
      </div>
    </main>

    <div class="cheat-alert-backdrop" v-if="showCheatAlertModal && latestAlarm">
      <div class="cheat-alert-panel">
        <div class="cheat-alert-header">
          <svg class="cheat-alert-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
          </svg>
          <h2>系统告警：交易已被强行挂起</h2>
        </div>

        <div class="cheat-alert-body">
          <p class="cheat-alert-copy">WebSocket 防作弊总线监听到高危异常，已阻断当前结算。</p>

          <div class="cheat-alert-detail">
            <div class="cheat-alert-row">
              <span>交易流水单号</span>
              <strong class="mono-id">{{ latestAlarm.transaction_id }}</strong>
            </div>
            <div class="cheat-alert-row">
              <span>LSTM 判定违规</span>
              <strong class="violation-badge">{{ formatViolationType(latestAlarm.violation_type) }}</strong>
            </div>
            <div class="cheat-alert-row">
              <span>模型置信度</span>
              <strong class="score-text">{{ Number(latestAlarm.lstm_score || 0).toFixed(2) }} <em>(阈值: 0.85)</em></strong>
            </div>
          </div>

          <button class="cheat-alert-primary" @click="openLatestEvidence">
            <svg class="eye-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
            </svg>
            查看多模态证据（现场抓拍与重力波形）
          </button>

          <div class="cheat-alert-actions">
            <button class="cheat-alert-danger" @click="confirmCheatAlert">确认作弊拦截</button>
            <button class="cheat-alert-pass" @click="dismissCheatAlert">忽略并放行</button>
          </div>
        </div>
      </div>
    </div>

    <div class="modal-overlay" v-if="showEvidenceModal" @click.self="showEvidenceModal = false">
      <div class="modal-box evidence-box">
        <h3 style="color: #cf1322;">违规现场证据</h3>
        <div class="evidence-img-container">
          <video v-if="currentEvidenceType === 'video'" :key="currentEvidenceUrl" :src="currentEvidenceUrl" controls autoplay muted @loadedmetadata="currentEvidenceError = ''" @error="handleVideoError"></video>
          <img v-else :src="currentEvidenceUrl" :alt="currentEvidenceType === 'mjpeg' ? '兼容视频证据流' : '监控快照'" @error="handleImageError" />
        </div>
        <p v-if="currentEvidenceError" class="evidence-error">{{ currentEvidenceError }}</p>
        <p class="help-text text-center mt-2">证据地址：{{ currentEvidenceUrl || '暂无' }}</p>
        <p class="help-text text-center mt-2">点击弹窗外部或关闭按钮退出</p>
        <div class="modal-actions">
          <button class="btn-cancel" @click="showEvidenceModal = false">关闭</button>
        </div>
      </div>
    </div>

    <div class="modal-overlay" v-if="showEditModal">
      <div class="modal-box">
        <h3>管理商品：{{ editForm.item_name }}</h3>
        <div class="form-group"><label>基础售价 (¥/kg):</label><input type="number" v-model.number="editForm.price" step="0.5" /></div>
        <div class="form-group"><label>当前库存 (kg):</label><input type="number" v-model.number="editForm.inventory" step="5" /></div>
        <div class="form-group"><label>新鲜度 (0.00-1.00):</label><input type="number" v-model.number="editForm.freshness" step="0.05" /></div>
        <div class="modal-actions"><button class="btn-cancel" @click="showEditModal = false">取消</button><button class="btn-save" @click="saveCommodity">保存</button></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, shallowRef, nextTick, computed } from 'vue';
import * as echarts from 'echarts';
import api from '../utils/api';

onMounted(() => {
  window.tailwind = { corePlugins: { preflight: false } };
  if (!document.getElementById('tailwind-cdn')) {
    const script = document.createElement('script');
    script.id = 'tailwind-cdn';
    script.src = 'https://cdn.tailwindcss.com';
    document.head.appendChild(script);
  }
});

const activeTab = ref('dashboard');

// ========== 原有状态 ==========
const chartRef = ref(null);
const chartInstance = shallowRef(null);
const pricingList = ref([]);
const selectedFruit = ref(null);
const commodityList = ref([]);
const showEditModal = ref(false);
const editForm = ref({ item_name: '', price: 0, inventory: 0, freshness: 0 });
const orderList = ref([]);
const filterTag = ref('');

// ========== 🌟 新增：报警日志状态 ==========
const alarmList = ref([]);
const showEvidenceModal = ref(false);
const currentEvidenceUrl = ref('');
const currentEvidenceType = ref('image');
const currentEvidenceError = ref('');
const currentEvidenceLogId = ref(null);
const showCheatAlertModal = ref(false);
const latestAlarm = ref(null);
const lastSeenAlarmLogId = ref(0);
const alarmBaselineReady = ref(false);
let alarmPollingTimer = null;

// ========== 大屏状态 ==========
const monitorData = ref({ today_sales: 0, today_orders: 0, alerts: [], pricing: [], history_chart: null });
const monitorChartRef = ref(null);
let monitorChartInstance = null;
const currentTimeType = ref('hour');
const currentFruitKey = ref('all');
const currentPricingItem = computed(() => pricingList.value.find(item => item.name === selectedFruit.value));
const availableFruits = computed(() => {
  if (!monitorData.value.history_chart) return [];
  return Object.keys(monitorData.value.history_chart).filter(k => k !== 'all');
});

// ========== TAB 切换主干 ==========
const switchTab = async (tabName) => {
  activeTab.value = tabName;
  if (tabName === 'dashboard') {
    await nextTick(); fetchDashboardData();
  } else if (tabName === 'commodities') {
    fetchCommodities();
  } else if (tabName === 'orders') {
    fetchOrders();
  } else if (tabName === 'alarms') {
    // 🌟 触发获取报警日志
    fetchAlarms();
  } else if (tabName === 'monitor') {
    await nextTick(); fetchMonitorData();
  }
};

// ================= 🌟 报警日志获取、实时弹窗与证据预览逻辑 =================
const formatViolationType = (type = '') => {
  const value = String(type || '').toLowerCase();
  if (value.includes('swap') || value.includes('换货')) return '恶意换货';
  if (value.includes('occlusion') || value.includes('遮挡')) return '遮挡作弊';
  if (value.includes('lift') || value.includes('托')) return '恶意托举（托底）';
  return type || '未知违规';
};

const fetchAlarms = async (options = {}) => {
  const notifyNew = Boolean(options.notifyNew);

  try {
    const res = await api.get('/transaction/alarms'); // 修改为如果写在别处请改路径
    if (res.data.status === 'success') {
      const data = res.data.data || [];
      alarmList.value = data;

      const newestAlarm = data[0];
      const newestId = Number(newestAlarm?.log_id || 0);

      if (!alarmBaselineReady.value) {
        lastSeenAlarmLogId.value = newestId;
        alarmBaselineReady.value = true;
        return;
      }

      if (notifyNew && newestAlarm && newestId > lastSeenAlarmLogId.value) {
        latestAlarm.value = newestAlarm;
        showCheatAlertModal.value = true;
      }

      if (newestId > lastSeenAlarmLogId.value) {
        lastSeenAlarmLogId.value = newestId;
      }
    }
  } catch (error) {
    console.error("获取报警日志失败:", error);
  }
};

const buildEvidenceUrl = (evidence) => {
  // 优先使用后端 evidence 接口。它会根据 log_id 去数据库读取 shot_path，
  // 并兼容 Windows 绝对路径、static 相对路径等多种存储形式。
  if (evidence && typeof evidence === 'object' && evidence.log_id) {
    return `http://localhost:8000/api/transaction/evidence/${evidence.log_id}?t=${Date.now()}`;
  }

  // 兜底：如果调用方只传入了路径，则尽量转成 /static 可访问地址。
  const rawPath = String(evidence || '');
  const normalizedPath = rawPath.replace(/\\/g, '/').trim();
  if (!normalizedPath) return '';
  if (/^https?:\/\//i.test(normalizedPath)) return normalizedPath;

  const staticIndex = normalizedPath.toLowerCase().indexOf('static/');
  if (staticIndex >= 0) {
    return `http://localhost:8000/${normalizedPath.slice(staticIndex)}`;
  }

  return `http://localhost:8000/${normalizedPath.replace(/^\/+/, '')}`;
};

const detectEvidenceType = (evidence, url) => {
  const rawPath = typeof evidence === 'object' ? evidence?.shot_path : evidence;
  const value = `${rawPath || ''} ${url || ''}`;

  if (/\.(jpg|jpeg|png|gif|bmp|webp)(\?|$)/i.test(value)) {
    return 'image';
  }

  // alarm_log 的证据主体是视频。若 shot_path 是目录、无扩展名，或前端使用
  // /api/transaction/evidence/{log_id} 代理接口，URL 本身看不出扩展名，此时默认用 video。
  if (typeof evidence === 'object' && evidence?.log_id) {
    return 'video';
  }

  return /\.(mp4|avi|mov|webm|m4v)(\?|$)/i.test(value) ? 'video' : 'image';
};

const viewEvidence = (evidence) => {
  const url = buildEvidenceUrl(evidence);
  currentEvidenceError.value = '';
  currentEvidenceLogId.value = evidence && typeof evidence === 'object' ? evidence.log_id : null;
  currentEvidenceUrl.value = url;
  currentEvidenceType.value = detectEvidenceType(evidence, url);
  showEvidenceModal.value = true;
};

const openLatestEvidence = () => {
  if (!latestAlarm.value?.shot_path) return;
  showCheatAlertModal.value = false;
  viewEvidence(latestAlarm.value);
};

const confirmCheatAlert = () => {
  showCheatAlertModal.value = false;
  switchTab('alarms');
};

const dismissCheatAlert = () => {
  showCheatAlertModal.value = false;
};

const startAlarmPolling = () => {
  if (alarmPollingTimer) clearInterval(alarmPollingTimer);
  alarmPollingTimer = setInterval(() => {
    fetchAlarms({ notifyNew: true });
  }, 2000);
};

// 如果图片加载失败的兜底处理
const handleImageError = (e) => {
  e.target.src = 'https://via.placeholder.com/600x400?text=Image+Not+Found+or+Path+Error';
};

const handleVideoError = () => {
  console.error("视频证据加载失败:", currentEvidenceUrl.value);
  if (currentEvidenceLogId.value) {
    currentEvidenceType.value = 'mjpeg';
    currentEvidenceUrl.value = `http://localhost:8000/api/transaction/evidence-mjpeg/${currentEvidenceLogId.value}?t=${Date.now()}`;
    currentEvidenceError.value = "原始视频使用了浏览器不支持的编码，已自动切换为兼容证据流播放。";
    return;
  }
  currentEvidenceError.value = "视频无法播放：请确认 shot_path 是真实文件路径，且文件可以被后端读取。";
};


// ================= 其他逻辑保持原样 =================
const fetchMonitorData = async () => { try { const res = await api.get('/dashboard/advanced_monitor'); if (res.data.status === 'success') { monitorData.value = res.data.data; initMonitorChart(); } } catch (e) {} };
const initMonitorChart = () => { if (monitorChartRef.value && !monitorChartInstance) { monitorChartInstance = echarts.init(monitorChartRef.value); monitorChartInstance.setOption({ backgroundColor: 'transparent', tooltip: { trigger: 'axis' }, grid: { left: '3%', right: '4%', top: '15%', bottom: '5%', containLabel: true }, xAxis: { type: 'category', axisLabel: { color: '#9ca3af' } }, yAxis: { type: 'value', name: '销量 (kg)', splitLine: { lineStyle: { color: '#374151' } } }, series: [{ type: 'bar', itemStyle: { color: '#3b82f6', borderRadius: [4, 4, 0, 0] }, barMaxWidth: 50 }] }); } updateMonitorChart(); };
const updateMonitorChart = () => { if (!monitorChartInstance || !monitorData.value.history_chart) return; const chartData = monitorData.value.history_chart[currentFruitKey.value][currentTimeType.value]; const fName = currentFruitKey.value === 'all' ? '全部品类' : currentFruitKey.value; monitorChartInstance.setOption({ xAxis: { data: chartData.x }, legend: { data: [fName + ' 历史真实销量(kg)'], textStyle: { color: '#9ca3af' }, top: 0 }, series: [{ name: fName + ' 历史真实销量(kg)', data: chartData.y }] }); };
const changeTimeType = (type) => { currentTimeType.value = type; updateMonitorChart(); };
const timeBtnClass = (type) => type === currentTimeType.value ? 'px-3 py-1 bg-blue-600 text-white rounded text-xs transition' : 'px-3 py-1 bg-transparent text-gray-400 hover:text-white rounded text-xs transition';
const applyNewPrice = (item) => { alert(`成功干预！${item.name} 价格已下放至秤端系统：¥${item.new_price}`); };

const togglePricingCard = (n) => { selectedFruit.value = selectedFruit.value === n ? null : n; };
const renderChart = (dates, predictions) => { if (!chartRef.value) return; if (!chartInstance.value) chartInstance.value = echarts.init(chartRef.value); const seriesData = Object.keys(predictions).map(f => ({ name: f, type: 'line', smooth: true, data: predictions[f], itemStyle: { borderWidth: 2 } })); chartInstance.value.setOption({ tooltip: { trigger: 'axis' }, legend: { data: Object.keys(predictions), top: 0 }, grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true }, dataZoom: [ { type: 'inside', start: 0, end: 100 }, { type: 'slider', start: 0, end: 100, bottom: 5 } ], xAxis: { type: 'category', boundaryGap: false, data: dates }, yAxis: { type: 'value', name: '预测销量 (kg)' }, series: seriesData }); };
const fetchDashboardData = async () => { try { const r = await api.get('/dashboard/sales_and_pricing'); pricingList.value = r.data.pricing_strategy.map(i => ({ ...i, manualPrice: i.suggested_price })); renderChart(r.data.dates, r.data.sales_predictions); } catch(e){} };
const applyPrice = async (item) => { try { await api.post('/update_price', { item_name: item.name, new_price: parseFloat(item.manualPrice) }); fetchDashboardData(); selectedFruit.value = null; } catch(e){} };
const fetchCommodities = async () => { try { const r = await api.get('/commodities'); if (r.data.status === 'success') commodityList.value = r.data.data; } catch(e){} };
const openEditModal = (item) => { editForm.value = { ...item }; showEditModal.value = true; };
const saveCommodity = async () => { try { const r = await api.post('/update_commodity', editForm.value); if (r.data.status === 'success') { showEditModal.value = false; fetchCommodities(); } } catch(e){} };
const getTagText = (tag) => tag === 0 ? '✅ 正常' : tag === 1 ? '⚠️ 换货' : '🚫 遮挡';
const getTagClass = (tag) => tag === 0 ? 'normal' : tag === 1 ? 'anomaly-swap' : 'anomaly-occlusion';
const fetchOrders = async () => { try { const url = filterTag.value !== '' ? `/transaction/list?tag=${filterTag.value}` : '/transaction/list'; const r = await api.get(url); if (r.data.status === 'success') orderList.value = r.data.data; } catch (e) {} };
const updateTag = async (id, newTag) => { try { await api.put(`/transaction/${id}/tag`, { tag: newTag }); fetchOrders(); } catch(e){} };
const deleteOrder = async (id) => { if (!confirm("删除不可恢复？")) return; try { await api.delete(`/transaction/${id}`); fetchOrders(); } catch(e){} };

const handleResize = () => {
  if (chartInstance.value && activeTab.value === 'dashboard') chartInstance.value.resize();
  if (monitorChartInstance && activeTab.value === 'monitor') monitorChartInstance.resize();
};

onMounted(() => {
  fetchDashboardData();
  fetchAlarms();
  startAlarmPolling();
  window.addEventListener('resize', handleResize);
});

onBeforeUnmount(() => {
  if (alarmPollingTimer) clearInterval(alarmPollingTimer);
  window.removeEventListener('resize', handleResize);
});
</script>

<style scoped>
/* ========== 原有所有 CSS 保留 ========== */
.admin-layout { display: flex; flex: 1; height: 100vh; background-color: #f0f2f5; font-family: system-ui, sans-serif;}
.sidebar { width: 250px; background-color: #001529; color: white; padding: 20px 0; display: flex; flex-direction: column; }
.logo { text-align: center; font-size: 1.2rem; margin-bottom: 30px; letter-spacing: 1px; color: #fff;}
.nav-menu { list-style: none; padding: 0; margin: 0; }
.nav-menu li { padding: 15px 20px; cursor: pointer; color: #a6adb4; transition: 0.3s; border-left: 4px solid transparent;}
.nav-menu li:hover { color: white; background: rgba(255,255,255,0.05);}
.nav-menu li.active { background-color: #e6f7ff; color: #1890ff; border-left-color: #1890ff;}
.content { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; transition: background-color 0.3s ease; }
.content.monitor-bg { padding: 0 !important; background-color: #1a1c23;}
.top-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; background: white; padding: 15px 20px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,21,41,0.08); }
.top-nav h1 { margin: 0; font-size: 20px; color: #333;}
.user-info { font-weight: bold; color: #1890ff; }
.tab-content { display: flex; flex-direction: column; flex: 1;}

/* 🌟 新增：违规监控弹窗专属样式 */
.evidence-box {
  width: 700px !important;
  max-width: 90vw;
}
.evidence-img-container {
  width: 100%;
  background: #f5f5f5;
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
  border: 1px solid #e8e8e8;
}
.evidence-img-container img {
  max-width: 100%;
  max-height: 60vh;
  object-fit: contain;
}
.evidence-img-container video {
  width: 100%;
  max-height: 60vh;
  background: #111827;
  border-radius: 6px;
}
.evidence-error {
  margin: 10px 0 0;
  padding: 10px 12px;
  border: 1px solid #ffa39e;
  border-radius: 6px;
  background: #fff1f0;
  color: #cf1322;
  font-size: 13px;
  line-height: 1.5;
}
.text-red-500 { color: #ef4444; }

@keyframes modal-flash {
  0%, 100% { box-shadow: 0 0 15px rgba(220, 38, 38, 0.4); border-color: rgba(220, 38, 38, 0.6); }
  50% { box-shadow: 0 0 35px rgba(220, 38, 38, 0.9); border-color: rgba(239, 68, 68, 1); }
}

.cheat-alert-backdrop {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.62);
  backdrop-filter: blur(2px);
}

.cheat-alert-panel {
  width: 648px;
  max-width: calc(100vw - 32px);
  background: #1e2028;
  border: 2px solid #dc2626;
  border-radius: 14px;
  overflow: hidden;
  color: #fff;
  animation: modal-flash 1.5s infinite;
}

.cheat-alert-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 22px 30px;
  background: #dc2626;
}

.cheat-alert-header h2 {
  margin: 0;
  color: #fff;
  font-size: 24px;
  font-weight: 900;
  letter-spacing: 0.02em;
}

.cheat-alert-icon {
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  color: #fff;
}

.cheat-alert-body {
  padding: 30px 32px 32px;
}

.cheat-alert-copy {
  margin: 0 0 22px;
  color: #d1d5db;
  font-size: 20px;
  line-height: 1.5;
}

.cheat-alert-detail {
  padding: 18px 22px;
  border: 1px solid #374151;
  border-radius: 6px;
  background: #2a2d36;
}

.cheat-alert-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  min-height: 46px;
  color: #6b7280;
  font-size: 20px;
}

.cheat-alert-row strong {
  text-align: right;
}

.mono-id {
  color: #d1d5db;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 18px;
}

.violation-badge {
  padding: 5px 10px;
  border: 1px solid #991b1b;
  border-radius: 6px;
  background: rgba(127, 29, 29, 0.55);
  color: #f87171;
  font-size: 18px;
  font-weight: 900;
}

.score-text {
  color: #eab308;
  font-size: 22px;
  font-weight: 900;
}

.score-text em {
  color: #6b7280;
  font-size: 15px;
  font-style: normal;
  font-weight: 500;
}

.cheat-alert-primary {
  width: 100%;
  margin-top: 32px;
  padding: 16px;
  border: 0;
  border-radius: 5px;
  background: #2563eb;
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 900;
  transition: background 0.2s ease, transform 0.2s ease;
}

.cheat-alert-primary:hover {
  background: #3b82f6;
  transform: translateY(-1px);
}

.eye-icon {
  width: 21px;
  height: 21px;
  margin-right: 12px;
}

.cheat-alert-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #374151;
}

.cheat-alert-actions button {
  min-height: 50px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 20px;
  font-weight: 900;
  transition: background 0.2s ease;
}

.cheat-alert-danger {
  border: 1px solid #b91c1c;
  background: rgba(127, 29, 29, 0.58);
  color: #f87171;
}

.cheat-alert-danger:hover {
  background: rgba(185, 28, 28, 0.42);
}

.cheat-alert-pass {
  border: 0;
  background: #374151;
  color: #d1d5db;
}

.cheat-alert-pass:hover {
  background: #4b5563;
}

.section-title { font-size: 16px; margin-bottom: 0; color: #333; }
.dashboard-header-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.fruit-tabs { display: flex; gap: 10px; flex-wrap: wrap; }
.tab-btn { background: white; border: 1px solid #d9d9d9; padding: 6px 16px; border-radius: 20px; cursor: pointer; font-size: 14px; font-weight: bold; color: #555; transition: all 0.3s ease; position: relative; outline: none; }
.tab-btn:hover { border-color: #1890ff; color: #1890ff; }
.tab-btn.active { background: #1890ff; color: white; border-color: #1890ff; box-shadow: 0 4px 10px rgba(24,144,255,0.3); }
.dot { position: absolute; top: -2px; right: -2px; width: 10px; height: 10px; border-radius: 50%; border: 2px solid white; }
.dot.up { background-color: #f5222d; }
.dot.down { background-color: #52c41a; }
.single-pricing-card { margin-bottom: 20px; }
.pricing-card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border-left: 5px solid #1890ff; max-width: 500px; }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;}
.card-header h4 { margin: 0; font-size: 18px; color: #333; }
.status-badge { font-size: 13px; padding: 4px 10px; border-radius: 12px; font-weight: bold;}
.status-badge.up { background-color: #fff1f0; color: #cf1322; border: 1px solid #ffa39e;}
.status-badge.down { background-color: #f6ffed; color: #389e0d; border: 1px solid #b7eb8f;}
.status-badge.normal { background-color: #f0f5ff; color: #096dd9; border: 1px solid #adc6ff;}
.price-compare { display: flex; gap: 20px; margin-bottom: 12px; font-size: 16px;}
.old-price { color: #888; text-decoration: line-through; }
.new-price { color: #f5222d; font-weight: 900; font-size: 18px;}
.reason { margin: 0 0 15px 0; font-size: 14px; color: #666; background: #fafafa; padding: 12px; border-radius: 6px; border: 1px solid #eee; line-height: 1.5; }
.price-adjust { display: flex; align-items: center; gap: 10px; }
.currency { color: #666; font-weight: bold; font-size: 16px;}
.price-input { width: 100px; padding: 8px 12px; border: 1px solid #d9d9d9; border-radius: 6px; font-size: 16px; outline: none; transition: 0.3s;}
.price-input:focus { border-color: #1890ff; box-shadow: 0 0 0 2px rgba(24,144,255,0.2);}
.btn-apply { padding: 8px 20px; background: #1890ff; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: bold; transition: 0.3s;}
.btn-apply:hover { background: #40a9ff; transform: translateY(-1px); }
.btn-close { padding: 8px 15px; background: white; color: #888; border: 1px solid #ddd; border-radius: 6px; cursor: pointer; font-size: 14px; transition: 0.3s;}
.btn-close:hover { background: #f5f5f5; color: #333; }
.slide-fade-enter-active { transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); }
.slide-fade-leave-active { transition: all 0.2s cubic-bezier(0.25, 0.8, 0.25, 1); }
.slide-fade-enter-from { opacity: 0; transform: translateY(-15px) scale(0.98); }
.slide-fade-leave-to { opacity: 0; transform: translateY(-10px) scale(0.98); }
.dashboard-panels { display: flex; gap: 20px; flex: 1; min-height: 400px;}
.panel { flex: 1; display: flex; flex-direction: column; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,21,41,0.08); }
.echarts-container { flex: 1; width: 100%; min-height: 350px; }
.table-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.05); }
.table-header-actions { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;}
.table-header-actions h3 { margin: 0; color: #333;}
.btn-success { background: #52c41a; color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; font-weight: bold;}
.btn-success:hover { background: #73d13d;}
.styled-table { width: 100%; border-collapse: collapse; font-size: 14px; text-align: left;}
.styled-table thead tr { background-color: #fafafa; border-bottom: 1px solid #f0f0f0; }
.styled-table th, .styled-table td { padding: 12px 15px; border-bottom: 1px solid #f0f0f0;}
.styled-table tbody tr:hover { background-color: #f9f9f9; }
.progress-bar { width: 80px; height: 8px; background: #eee; border-radius: 4px; display: inline-block; margin-right: 10px; overflow: hidden;}
.progress-fill { height: 100%; transition: width 0.3s; }
.stock-badge { padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;}
.stock-ok { background: #f6ffed; color: #389e0d; border: 1px solid #b7eb8f;}
.stock-low { background: #fff1f0; color: #cf1322; border: 1px solid #ffa39e;}
.btn-edit { background: white; border: 1px solid #1890ff; color: #1890ff; padding: 5px 10px; border-radius: 4px; cursor: pointer; transition: 0.3s;}
.btn-edit:hover { background: #1890ff; color: white;}
.modal-overlay { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.5); display: flex; justify-content: center; align-items: center; z-index: 1000;}
.modal-box { background: white; padding: 30px; border-radius: 8px; width: 400px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);}
.modal-box h3 { margin-top: 0; margin-bottom: 20px; border-bottom: 1px solid #eee; padding-bottom: 10px;}
.form-group { margin-bottom: 15px; }
.form-group label { display: block; margin-bottom: 5px; font-weight: bold; color: #555;}
.form-group input { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; outline: none;}
.form-group input:focus { border-color: #1890ff;}
.help-text { font-size: 12px; color: #999; margin-top: 5px;}
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 25px;}
.btn-cancel { padding: 8px 15px; border: 1px solid #d9d9d9; background: white; border-radius: 4px; cursor: pointer;}
.btn-save { padding: 8px 15px; border: none; background: #1890ff; color: white; border-radius: 4px; cursor: pointer; font-weight: bold;}
.btn-save:hover { background: #40a9ff;}
.filter-actions { display: flex; align-items: center;}
.tag-select { padding: 6px 12px; border: 1px solid #d9d9d9; border-radius: 4px; outline: none; margin-right: 15px; font-size: 14px;}
.font-mono { font-family: monospace; color: #888;}
.text-weight { color: #fa8c16; font-weight: bold;}
.text-price { color: #cf1322; font-weight: bold;}
.status-tag { padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: bold; display: inline-block; }
.status-tag.normal { background: #f6ffed; border: 1px solid #b7eb8f; color: #52c41a; }
.status-tag.anomaly-swap { background: #fffbe6; border: 1px solid #ffe58f; color: #faad14; }
.status-tag.anomaly-occlusion { background: #fff1f0; border: 1px solid #ffa39e; color: #f5222d; }
.action-buttons { display: flex; gap: 8px; }
.btn-action { padding: 5px 10px; border: none; border-radius: 4px; font-size: 12px; cursor: pointer; transition: 0.2s; font-weight: bold; }
.btn-action.success { background: #52c41a; color: white; }
.btn-action.success:hover { background: #73d13d; }
.btn-action.warn { background: #fa8c16; color: white; }
.btn-action.warn:hover { background: #ffc069; }
.btn-action.danger { background: #ff4d4f; color: white; }
.btn-action.danger:hover { background: #ff7875; }
</style>
