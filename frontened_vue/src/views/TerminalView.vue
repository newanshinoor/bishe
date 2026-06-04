<template>
  <div class="h-screen w-full">

    <div v-if="!showPaymentPage" class="terminal-container h-full">
      <div class="camera-section">
        <h2>智能果蔬识别区域</h2>
        <div
          ref="videoBoxRef"
          class="video-placeholder"
          @mousedown="startRoiDraw"
          @mousemove="updateRoiDraw"
          @mouseup="finishRoiDraw"
          @mouseleave="finishRoiDraw"
        >
          <img
            v-if="isRecognizing && currentImage"
            ref="videoImageRef"
            :src="'data:image/jpeg;base64,' + currentImage"
            class="ws-video"
            alt="Camera Feed"
            @load="syncVideoGeometry"
          />
          <div v-if="roiBox" class="roi-box" :style="roiBoxStyle"></div>
          <div v-if="roiDrawMode" class="roi-tip">ROI 标注模式：拖拽鼠标画框，按 2 保存</div>
          <div v-if="handOverlayEnabled" class="hand-overlay-tip">MediaPipe 手部关键点显示中，按 3 关闭</div>
          <div v-show="!isRecognizing" class="offline-msg">摄像头已关闭</div>
          <div v-show="isRecognizing && !currentImage" class="offline-msg">正在连接后端深度相机...</div>
        </div>

        <div class="current-item-panel multi-item-warning" v-if="isRecognizing && hasMultiItemError">
          <div>
            <h3>无法计价</h3>
            <p>{{ multiItemMessage }}</p>
          </div>
        </div>
        <div class="current-item-panel" v-else-if="isRecognizing && currentDetected">
          <div class="item-info">
            <h3>
              识别结果: {{ currentDetected.name }} ({{ currentDetected.freshness }})
              <span v-if="currentDetected.confidence">｜置信度: {{ (currentDetected.confidence * 100).toFixed(1) }}%</span>
            </h3>
            <div class="specs">
              <span class="spec-block">单价: <b>¥{{ currentDetected.unitPrice.toFixed(2) }}/kg</b></span>
              <span class="spec-block highlight">实时重量: <b>{{ currentDetected.weight.toFixed(2) }} kg</b></span>
            </div>
            <p class="calc-total">总计: <span>¥{{ currentDetected.totalPrice.toFixed(2) }}</span></p>
          </div>
          <button class="btn btn-primary add-btn" @click="addToCart" :disabled="currentDetected.weight <= 0">确认添加</button>
        </div>
        <div class="current-item-panel empty" v-else-if="isRecognizing && !currentDetected">
          <p>{{ recognitionHint }}</p>
        </div>

        <div class="controls">
          <button
            :class="['btn', isRecognizing ? 'btn-danger' : 'btn-success']"
            @click="toggleRecognition"
          >
            {{ isRecognizing ? '停止识别' : '开启识别' }}
          </button>
          <button
            :class="['btn', depthAssistEnabled ? 'btn-primary' : 'btn-secondary']"
            @click="toggleDepthAssist"
          >
            深度辅助：{{ depthAssistEnabled ? '开启' : '关闭' }}
          </button>
          <button class="btn btn-secondary" @click="manualTareScale">
            空秤清零
          </button>
          <span class="depth-assist-status">
            有效距离 ≤ {{ Number(maxObjectDepthMm || 1800).toFixed(0) }}mm
          </span>
        </div>
        <p v-if="depthAssistNotice" class="depth-assist-notice">{{ depthAssistNotice }}</p>
      </div>

      <div class="cart-section">
        <h2>购物车清单</h2>
        <ul class="item-list">
          <li v-for="(item, index) in cartItems" :key="index">
            <div class="cart-item-left">
              <span class="item-name">{{ item.name }} ({{ item.freshness }})</span>
              <span class="item-weight">{{ item.weight }} kg</span>
            </div>
            <div class="cart-item-right">
              <span class="item-price">¥{{ item.price }}</span>
              <button class="btn-remove" @click="removeFromCart(index)">删除</button>
            </div>
          </li>
        </ul>
        <div class="total-wrapper">
          <div class="mock-customer-box">
            <label>模拟扫码顾客</label>
            <select v-model="mockCustomerId">
              <option value="CUSTOMER_001">CUSTOMER_001</option>
              <option value="CUSTOMER_002">CUSTOMER_002</option>
              <option value="CUSTOMER_003">CUSTOMER_003</option>
            </select>
            <input v-model.trim="mockCustomerId" type="text" placeholder="或输入自定义顾客 ID" />
          </div>
          <div class="total">
            总计: <span>¥{{ cartTotalPrice }}</span>
          </div>
          <button class="btn btn-success checkout-btn" :disabled="cartItems.length === 0" @click="handleCheckout">
            确认支付
          </button>
        </div>
      </div>
    </div>

    <div v-else class="bg-gray-100 text-gray-800 font-sans h-screen w-full flex items-center justify-center relative overflow-hidden select-none">

      <div class="absolute top-4 left-6 text-gray-400 text-sm font-mono">
        NO.01 智能售卖终端 | 状态：在线 | 视觉引擎：运行中 | 订单号：{{ currentOrderId }}
      </div>

      <div class="bg-white w-full max-w-5xl rounded-3xl shadow-2xl overflow-hidden flex flex-row h-[600px] relative transition-all">

        <div class="w-1/2 bg-gray-50 p-8 flex flex-col border-r border-gray-200">
          <div class="flex items-center space-x-3 mb-6">
            <svg class="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"></path></svg>
            <h2 class="text-2xl font-bold text-gray-800">确认您的订单</h2>
          </div>

          <div class="flex-grow overflow-y-auto pr-2 space-y-4">
            <div v-for="(item, index) in cartItems" :key="index" class="bg-white p-4 rounded-xl shadow-sm border border-gray-100 flex justify-between items-center">
              <div>
                <h3 class="text-lg font-bold text-gray-800">
                  {{ item.name }}
                  <span :class="['text-xs px-2 py-0.5 rounded-full ml-1 font-normal', item.freshness === '新鲜' ? 'bg-green-100 text-green-600' : 'bg-yellow-100 text-yellow-600']">
                    {{ item.freshness }}
                  </span>
                </h3>
                <div class="text-sm text-gray-500 mt-1">智能计价: ¥ {{ item.unitPrice }} / kg</div>
              </div>
              <div class="text-right">
                <div class="text-lg font-bold text-gray-800">{{ item.weight }} kg</div>
                <div class="text-sm font-bold text-gray-800">¥ {{ item.price }}</div>
              </div>
            </div>
          </div>

          <div class="pt-6 border-t border-gray-200 mt-4">
            <div class="flex justify-between text-gray-500 mb-2">
              <span>商品总重</span>
              <span class="font-bold text-gray-700">{{ cartTotalWeight }} kg</span>
            </div>
            <div class="flex justify-between text-gray-500 mb-2" v-if="false">
              <span>AI 智能优惠</span>
              <span class="font-bold text-red-500">- ¥ 0.00</span>
            </div>
            <div class="flex justify-between items-end mt-4">
              <span class="text-gray-800 font-bold text-lg">应付总额</span>
              <div class="text-right">
                <span class="text-3xl font-black text-red-600">¥ {{ cartTotalPrice }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="w-1/2 bg-white p-8 flex flex-col relative">

          <div :class="['absolute top-6 right-6 px-3 py-1 rounded-full text-sm font-bold flex items-center shadow-sm', timeLeft > 0 ? 'bg-red-50 text-red-600' : 'bg-red-600 text-white animate-pulse']">
            <svg v-if="timeLeft > 0" class="w-4 h-4 mr-1 animate-spin-slow" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            支付倒计时: <span class="ml-1 w-8 text-center">{{ timeLeft }}</span> s
          </div>

          <h2 class="text-xl font-bold text-gray-800 mb-6 text-center mt-2">请选择支付方式</h2>

          <div class="flex space-x-4 mb-8">
            <button @click="paymentMethod = 'wechat'" :class="['flex-1 py-3 border-2 rounded-xl flex justify-center items-center space-x-2 transition cursor-pointer', paymentMethod === 'wechat' ? 'border-green-500 bg-green-50 shadow-md' : 'border-gray-200 bg-white hover:bg-green-50 opacity-60']">
              <div class="w-6 h-6 bg-green-500 rounded-full flex items-center justify-center text-white text-xs font-bold">微</div>
              <span :class="['font-bold', paymentMethod === 'wechat' ? 'text-green-700' : 'text-gray-600']">微信支付</span>
            </button>
            <button @click="paymentMethod = 'alipay'" :class="['flex-1 py-3 border-2 rounded-xl flex justify-center items-center space-x-2 transition cursor-pointer', paymentMethod === 'alipay' ? 'border-blue-500 bg-blue-50 shadow-md' : 'border-gray-200 bg-white hover:bg-blue-50 opacity-60']">
              <div class="w-6 h-6 bg-blue-500 rounded-sm flex items-center justify-center text-white text-xs font-bold">支</div>
              <span :class="['font-bold', paymentMethod === 'alipay' ? 'text-blue-700' : 'text-gray-600']">支付宝</span>
            </button>
          </div>

          <div class="flex-grow flex flex-col items-center justify-center">
            <div :class="['w-56 h-56 border-4 rounded-2xl p-3 relative bg-white shadow-xl transition-colors duration-300', paymentMethod === 'wechat' ? 'border-green-500' : 'border-blue-500']">

              <div :class="['scanner-line', paymentMethod === 'alipay' ? 'alipay' : '']"></div>

              <img v-if="qrCodeUrl" :src="qrCodeUrl" class="w-full h-full object-cover rounded-lg relative z-0" alt="二维码" />
              <div v-else class="w-full h-full grid grid-cols-5 grid-rows-5 gap-1 opacity-20 relative z-0">
                <div class="col-span-2 row-span-2 bg-black rounded-tl-lg border-2 border-white relative"><div class="absolute inset-1 bg-black border-2 border-white"></div></div>
                <div class="bg-black rounded-sm"></div><div class="bg-white"></div>
                <div class="col-span-2 row-span-2 bg-black rounded-tr-lg border-2 border-white relative"><div class="absolute inset-1 bg-black border-2 border-white"></div></div>
                <div class="bg-white"></div><div class="bg-black rounded-sm"></div><div class="bg-black rounded-sm"></div>
                <div class="col-span-3 row-span-1 bg-black rounded"></div><div class="bg-white"></div><div class="bg-black rounded"></div>
                <div class="col-span-2 row-span-2 bg-black rounded-bl-lg border-2 border-white relative"><div class="absolute inset-1 bg-black border-2 border-white"></div></div>
                <div class="bg-black"></div><div class="col-span-2 row-span-2 bg-black rounded-br-xl"></div>
                <div class="bg-white"></div><div class="bg-black rounded-full"></div>
              </div>

              <div :class="['absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-12 h-12 bg-white rounded-lg border-2 p-1 flex items-center justify-center transition-colors z-10', paymentMethod === 'wechat' ? 'border-green-500' : 'border-blue-500']">
                <div :class="['w-full h-full rounded flex items-center justify-center text-white font-bold text-lg', paymentMethod === 'wechat' ? 'bg-green-500' : 'bg-blue-500']">
                  {{ paymentMethod === 'wechat' ? '微' : '支' }}
                </div>
              </div>

              <div v-if="paymentStatus === 'success'" class="absolute inset-0 bg-white/95 flex flex-col justify-center items-center rounded-xl z-20 text-green-500">
                <div class="text-5xl mb-2 font-bold border-4 border-green-500 rounded-full w-16 h-16 flex items-center justify-center">✓</div>
                <div class="font-bold text-xl mt-2 text-gray-800">支付成功</div>
              </div>
            </div>

            <div class="mt-6 text-center">
              <p class="text-xl font-bold text-gray-800">打开{{ paymentMethod === 'wechat' ? '微信' : '支付宝' }}扫一扫</p>
              <p class="text-gray-500 mt-1">支付完成后将自动返回主页</p>
            </div>
          </div>

          <div class="mt-4 text-center">
            <button @click="cancelPayment" class="text-gray-400 hover:text-gray-600 underline text-sm transition bg-transparent border-none cursor-pointer">暂不购买，取消订单</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showTerminalCheatAlert" class="terminal-cheat-backdrop">
      <div class="terminal-cheat-panel">
        <div class="terminal-cheat-header">系统告警：交易已被终止</div>
        <div class="terminal-cheat-body">
          <p>检测到高风险异常动作，当前识别与结算流程已停止，请联系工作人员处理。</p>
          <div class="terminal-cheat-detail">
            <span>异常类型</span>
            <strong>{{ formatTerminalViolation(terminalCheatAlert.type) }}</strong>
          </div>
          <div class="terminal-cheat-detail">
            <span>LSTM 置信度</span>
            <strong>{{ Number(terminalCheatAlert.lstm_score || 0).toFixed(2) }}</strong>
          </div>
          <button class="terminal-cheat-button" @click="showTerminalCheatAlert = false">我已了解</button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

// === 原有状态 ===
const route = useRoute();
const router = useRouter();
const isRecognizing = ref(false);
const cartItems = ref([]);
const currentImage = ref('');
const currentDetected = ref(null);
const videoBoxRef = ref(null);
const videoImageRef = ref(null);
let ws = null;

// === LSTM 部分遮挡 ROI 标注状态 ===
const roiDrawMode = ref(false);
const roiBox = ref(null);
const roiDraftBox = ref(null);
const roiDraftStart = ref(null);
const isDrawingRoi = ref(false);
const videoGeometryVersion = ref(0);
const handOverlayEnabled = ref(false);
const depthAssistEnabled = ref(true);
const maxObjectDepthMm = ref(1800);
const depthAssistNotice = ref('已开启深度辅助，超过有效距离的目标不会计价');
const showTerminalCheatAlert = ref(false);
const terminalCheatAlert = ref({});
const hasMultiItemError = ref(false);
const multiItemMessage = ref('');
const recognitionStatus = ref('waiting');
const recognitionHint = ref('请将果蔬放置在摄像头下与秤台上...');
const roiBoxStyle = computed(() => {
  videoGeometryVersion.value;
  const activeBox = roiDraftBox.value || roiBox.value;
  const imageRect = getDisplayedImageRect();
  if (!activeBox || !imageRect) return {};

  return {
    left: `${imageRect.offsetX + activeBox.x * imageRect.width}px`,
    top: `${imageRect.offsetY + activeBox.y * imageRect.height}px`,
    width: `${activeBox.w * imageRect.width}px`,
    height: `${activeBox.h * imageRect.height}px`
  };
});

// === 新增：支付页状态控制 ===
const showPaymentPage = ref(route.meta.paymentPreview === true);
const currentOrderId = ref(localStorage.getItem('pending_payment_order_id') || '');
const qrCodeUrl = ref('');
const paymentStatus = ref('pending'); // pending, success, failed
const paymentMethod = ref(localStorage.getItem('pending_payment_channel') === 'mock_alipay' ? 'alipay' : 'wechat');
const mockCustomerId = ref('CUSTOMER_001');
const timeLeft = ref(5);
let pollingInterval = null;
let countdownInterval = null;
let mockPaymentTimer = null;
let paymentWs = null;

watch(
  () => route.path,
  () => {
    showPaymentPage.value = route.meta.paymentPreview === true;
  }
);

// 计算总价
const cartTotalPrice = computed(() => {
  return cartItems.value.reduce((sum, item) => sum + Number(item.price), 0).toFixed(2);
});

// 计算总重
const cartTotalWeight = computed(() => {
  return cartItems.value.reduce((sum, item) => sum + Number(item.weight), 0).toFixed(2);
});

// === 原有：摄像头与识别逻辑 ===
const sendDepthAssistState = () => {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({
    type: 'depth_assist',
    enabled: depthAssistEnabled.value
  }));
};

const toggleDepthAssist = () => {
  depthAssistEnabled.value = !depthAssistEnabled.value;
  depthAssistNotice.value = depthAssistEnabled.value
    ? '已开启深度辅助，超过有效距离的目标不会计价'
    : '已关闭深度距离过滤，仅按识别置信度判断';
  sendDepthAssistState();
};

const toggleRecognition = async () => {
  isRecognizing.value = !isRecognizing.value;

  if (isRecognizing.value) {
    showTerminalCheatAlert.value = false;
    terminalCheatAlert.value = {};
    const socket = new WebSocket('ws://localhost:8000/video/ws');
    ws = socket;
    socket.onopen = () => {
      console.log('已连接到后端相机流');
      sendDepthAssistState();
    };

    socket.onmessage = (event) => {
      // 旧连接关闭过程中可能仍有已排队消息，只处理当前活动 WebSocket。
      if (ws !== socket) return;

      const data = JSON.parse(event.data);
      currentImage.value = data.image;
      handOverlayEnabled.value = Boolean(data.hand_overlay_enabled);
      depthAssistEnabled.value = Boolean(data.depth_assist_enabled ?? depthAssistEnabled.value);
      maxObjectDepthMm.value = Number(data.max_object_depth_mm || maxObjectDepthMm.value || 1800);
      if (data.depth_filter_message) {
        depthAssistNotice.value = data.depth_filter_message;
      }

      let realWeight = Math.max(0, data.weight || 0);
      recognitionStatus.value = data.recognition_status || 'waiting';
      if (recognitionStatus.value === 'multi_item_error' || data.status === 'multi_item_error') {
        hasMultiItemError.value = true;
        multiItemMessage.value = data.message || '检测到多种果蔬，请一次仅放置一种商品称重';
        currentDetected.value = null;
      } else if (data.stable_result && data.stable_result.status === 'stable') {
        hasMultiItemError.value = false;
        multiItemMessage.value = '';
        recognitionHint.value = '';
        parseStableResult(data.stable_result, realWeight);
      } else {
        hasMultiItemError.value = false;
        multiItemMessage.value = '';
        currentDetected.value = null;
        recognitionHint.value = getRecognitionHint(data);
      }

      if (data.status === 'alert') {
        terminalCheatAlert.value = data;
        showTerminalCheatAlert.value = true;
        isRecognizing.value = false;
        currentDetected.value = null;
        if (ws === socket) {
          ws = null;
        }
        socket.close();
      }
    };

    socket.onerror = (error) => console.error('WebSocket 发生错误:', error);
    socket.onclose = () => {
      if (ws !== socket) return;
      ws = null;
      console.log('WebSocket 连接关闭');
      currentImage.value = '';
    };
  } else {
    if (ws) {
      const socket = ws;
      ws = null;
      socket.close();
    }
    currentImage.value = '';
    currentDetected.value = null;
    hasMultiItemError.value = false;
    multiItemMessage.value = '';
    recognitionStatus.value = 'waiting';
    recognitionHint.value = '请将果蔬放置在摄像头下与秤台上...';
  }
};

const getRecognitionHint = (data) => {
  const status = data.recognition_status || data.status || data.item_status;
  const hints = {
    low_confidence: '识别置信度低于后台阈值，请重新摆放商品',
    multi_item_error: '\u68c0\u6d4b\u5230\u591a\u79cd\u679c\u852c\uff0c\u8bf7\u4e00\u6b21\u4ec5\u653e\u7f6e\u4e00\u79cd\u5546\u54c1\u79f0\u91cd',
    occlusion_detected: '\u68c0\u6d4b\u5230\u906e\u6321\uff0c\u8bf7\u79fb\u5f00\u624b\u90e8\u6216\u906e\u6321\u7269',
    target_not_on_scale: '\u8bf7\u5c06\u5546\u54c1\u653e\u7f6e\u5230\u79e4\u9762\u4e2d\u592e',
    invalid_depth: '\u6df1\u5ea6\u6570\u636e\u4e0d\u53ef\u7528\uff0c\u8bf7\u68c0\u67e5\u6df1\u5ea6\u76f8\u673a',
    depth_too_far: '商品距离超过有效识别范围，请靠近秤面或调整位置',
    depth_out_of_range: '\u5546\u54c1\u8ddd\u79bb\u8d85\u51fa\u6709\u6548\u6df1\u5ea6\u8303\u56f4',
    no_object: '\u672a\u68c0\u6d4b\u5230\u5546\u54c1'
  };
  return hints[status] || data.recognition_message || data.message || '\u8bf7\u5c06\u679c\u852c\u653e\u7f6e\u5728\u6444\u50cf\u5934\u4e0b\u4e0e\u79e4\u53f0\u4e0a...';
};
const parseStableResult = (item, currentWeight) => {
  if (!item) {
    currentDetected.value = null;
    return;
  }

  const displayName = item.name_en || item.display_name || item.name || item.label || '未识别商品';
  const nameZh = item.name_zh || item.pricing_name || item.name || displayName;
  const pricingName = item.pricing_name || item.name_zh || nameZh;
  const freshness = item.freshness || '普通';
  const unitPrice = Number(item.unit_price ?? item.unitPrice ?? 0);
  const weight = Number(item.weight ?? item.weight_kg ?? currentWeight ?? 0);
  const totalPrice = Number(item.total_price ?? (unitPrice * weight));

  currentDetected.value = {
    name: displayName,
    nameEn: displayName,
    nameZh,
    pricingName,
    freshness: freshness,
    unitPrice: unitPrice,
    weight,
    totalPrice,
    confidence: Number(item.confidence ?? item.conf ?? 0)
  };
};

const addToCart = () => {
  if (hasMultiItemError.value) {
    alert('检测到多种果蔬，请一次仅放置一种商品称重');
    return;
  }

  if (currentDetected.value) {
    cartItems.value.push({
      name: currentDetected.value.name,
      name_en: currentDetected.value.nameEn,
      name_zh: currentDetected.value.nameZh,
      pricing_name: currentDetected.value.pricingName,
      freshness: currentDetected.value.freshness,
      weight: currentDetected.value.weight.toFixed(2),
      unitPrice: currentDetected.value.unitPrice.toFixed(2),
      price: currentDetected.value.totalPrice.toFixed(2)
    });
  }
};

const removeFromCart = (index) => {
  cartItems.value.splice(index, 1);
};

// === 结算与支付逻辑 ===
const handleCheckout = async () => {
  if (cartItems.value.length === 0) return;

  try {
    const customerIdentifier = (mockCustomerId.value || 'CUSTOMER_001').trim();
    const paymentNo = `PAY_${Date.now()}`;
    const scanAuthResponse = await fetch('http://localhost:8000/api/payment/scan-auth', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        payment_no: paymentNo,
        customer_platform: 'mock',
        customer_identifier: customerIdentifier
      })
    });
    const scanAuthData = await scanAuthResponse.json();
    if (scanAuthData.status === 'blocked') {
      alert(scanAuthData.message || '该顾客存在异常交易记录，请联系管理员');
      return;
    }
    if (scanAuthData.status !== 'ok') {
      throw new Error(scanAuthData.detail || scanAuthData.message || '扫码风控校验失败');
    }

    // 1. 模拟扫码授权，拿到包含 openid/customer_id/customer_id_hash 的 Token
    const authResponse = await fetch('http://localhost:8000/api/payment/mock-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scene: paymentNo,
        nickname: '无人售卖顾客',
        customer_platform: 'mock',
        mock_customer_id: customerIdentifier
      })
    });
    const authData = await authResponse.json();
    if (authData.status === 'blocked') {
      alert(authData.message || '该顾客存在异常交易记录，请联系管理员');
      return;
    }
    if (authData.status !== 'success') throw new Error('模拟授权失败');

    localStorage.setItem('token', authData.token);
    localStorage.setItem('customer_id', String(authData.customer_id));
    localStorage.setItem('openid', authData.openid);
    localStorage.setItem('customer_platform', authData.customer_platform || 'mock');
    localStorage.setItem('customer_id_hash', authData.customer_id_hash || scanAuthData.customer_id_hash || '');

    // 2. 请求后端生成订单，Authorization 中携带顾客身份
    const response = await fetch('http://localhost:8000/api/transaction/create', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authData.token}`
      },
      body: JSON.stringify({
        items: cartItems.value,
        total_amount: Number(cartTotalPrice.value),
        payment_channel: paymentMethod.value === 'alipay' ? 'mock_alipay' : 'mock_wechat'
      })
    });
    const resData = await response.json();
    if (!response.ok) throw new Error(resData.detail || '\u8ba2\u5355\u521b\u5efa\u5931\u8d25');

    currentOrderId.value = resData.order_id;
    qrCodeUrl.value = resData.qr_code_url;
    paymentStatus.value = 'pending';
    localStorage.setItem('pending_payment_order_id', resData.order_id);
    localStorage.setItem('pending_payment_amount', String(resData.total_amount || cartTotalPrice.value));
    localStorage.setItem('pending_payment_channel', paymentMethod.value === 'alipay' ? 'mock_alipay' : 'mock_wechat');
    showPaymentPage.value = true;
    await router.push('/payment');

    startCountdown();
    startMockPaymentSuccessTimer();
    startPaymentNotify();
    startPollingStatus();
  } catch (error) {
    console.error("订单创建失败", error);
    alert(error.message || "系统繁忙，请稍后再试");
  }
};

const startCountdown = () => {
  timeLeft.value = 5;
  if (countdownInterval) clearInterval(countdownInterval);
  countdownInterval = setInterval(() => {
    if (timeLeft.value > 0) {
      timeLeft.value--;
    } else {
      clearInterval(countdownInterval);
    }
  }, 1000);
};

const startMockPaymentSuccessTimer = () => {
  if (mockPaymentTimer) clearTimeout(mockPaymentTimer);
  mockPaymentTimer = setTimeout(() => {
    submitMockPaymentSuccess();
  }, 5000);
};

const submitMockPaymentSuccess = async () => {
  if (paymentStatus.value !== 'pending' || !showPaymentPage.value || !currentOrderId.value) return;

  try {
    const response = await fetch('http://localhost:8000/api/payment/mock-success', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        payment_no: currentOrderId.value,
        payment_channel: paymentMethod.value === 'alipay' ? 'mock_alipay' : 'mock_wechat',
        paid_amount: Number(cartTotalPrice.value) || Number(localStorage.getItem('pending_payment_amount') || 0)
      })
    });
    const data = await response.json();
    if (response.ok && data.status === 'success') {
      paymentSuccess();
      return;
    }

    paymentStatus.value = 'failed';
    alert(data.message || data.detail || '\u652f\u4ed8\u5931\u8d25\uff0c\u8bf7\u91cd\u65b0\u7ed3\u7b97');
  } catch (error) {
    paymentStatus.value = 'failed';
    alert('\u652f\u4ed8\u8bf7\u6c42\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u540e\u7aef\u670d\u52a1\u540e\u91cd\u8bd5');
  }
};

const getDisplayedImageRect = () => {
  const box = videoBoxRef.value;
  const image = videoImageRef.value;
  if (!box || !image) return null;

  const boxRect = box.getBoundingClientRect();
  const naturalWidth = image.naturalWidth || 640;
  const naturalHeight = image.naturalHeight || 640;
  const scale = Math.min(boxRect.width / naturalWidth, boxRect.height / naturalHeight);
  const width = naturalWidth * scale;
  const height = naturalHeight * scale;

  return {
    boxRect,
    offsetX: (boxRect.width - width) / 2,
    offsetY: (boxRect.height - height) / 2,
    width,
    height
  };
};

const syncVideoGeometry = () => {
  videoGeometryVersion.value++;
};

const pointToNormalized = (event, clampToImage = false) => {
  const imageRect = getDisplayedImageRect();
  if (!imageRect) return null;

  const relativeX = event.clientX - imageRect.boxRect.left - imageRect.offsetX;
  const relativeY = event.clientY - imageRect.boxRect.top - imageRect.offsetY;
  if (!clampToImage && (
    relativeX < 0 || relativeY < 0 ||
    relativeX > imageRect.width || relativeY > imageRect.height
  )) {
    return null;
  }

  const x = Math.min(1, Math.max(0, relativeX / imageRect.width));
  const y = Math.min(1, Math.max(0, relativeY / imageRect.height));
  return { x, y };
};

const startRoiDraw = (event) => {
  if (!roiDrawMode.value || !isRecognizing.value) return;
  const point = pointToNormalized(event);
  if (!point) return;

  isDrawingRoi.value = true;
  roiDraftStart.value = point;
  roiDraftBox.value = { x: point.x, y: point.y, w: 0, h: 0 };
};

const updateRoiDraw = (event) => {
  if (!roiDrawMode.value || !isDrawingRoi.value || !roiDraftStart.value) return;
  const point = pointToNormalized(event, true);
  if (!point) return;

  const x1 = Math.min(roiDraftStart.value.x, point.x);
  const y1 = Math.min(roiDraftStart.value.y, point.y);
  const x2 = Math.max(roiDraftStart.value.x, point.x);
  const y2 = Math.max(roiDraftStart.value.y, point.y);
  roiDraftBox.value = { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
};

const finishRoiDraw = () => {
  if (!isDrawingRoi.value) return;
  if (roiDraftBox.value && roiDraftBox.value.w >= 0.02 && roiDraftBox.value.h >= 0.02) {
    roiBox.value = roiDraftBox.value;
  }

  isDrawingRoi.value = false;
  roiDraftStart.value = null;
  roiDraftBox.value = null;
};

const loadRoi = async () => {
  try {
    const res = await fetch('http://localhost:8000/video/roi');
    const data = await res.json();
    if (data.status === 'success' && Array.isArray(data.roi) && data.roi.length === 4) {
      const [x1, y1, x2, y2] = data.roi.map(Number);
      roiBox.value = { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
    }
  } catch (error) {
    console.warn('读取 ROI 失败，将在保存新区域后同步:', error);
  }
};

const saveRoi = async () => {
  if (!roiBox.value || roiBox.value.w < 0.02 || roiBox.value.h < 0.02) {
    alert('请先按 1 后用鼠标拖拽出有效 ROI 区域');
    return;
  }

  const roi = [
    roiBox.value.x,
    roiBox.value.y,
    roiBox.value.x + roiBox.value.w,
    roiBox.value.y + roiBox.value.h
  ];

  try {
    const res = await fetch('http://localhost:8000/video/roi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roi })
    });
    const data = await res.json();
    if (data.status !== 'success') throw new Error(data.message || '保存 ROI 失败');

    roiDrawMode.value = false;
    alert(`ROI 已保存: [${data.roi.map(v => v.toFixed(3)).join(', ')}]`);
  } catch (error) {
    console.error('保存 ROI 失败:', error);
    alert('ROI 保存失败，请确认后端服务正在运行');
  }
};

const toggleHandOverlay = async () => {
  try {
    const res = await fetch('http://localhost:8000/video/hand-overlay', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !handOverlayEnabled.value })
    });
    const data = await res.json();
    if (data.status !== 'success') throw new Error(data.message || '切换手部关键点显示失败');
    handOverlayEnabled.value = Boolean(data.enabled);
  } catch (error) {
    console.error('切换 MediaPipe 手部关键点显示失败:', error);
    alert('切换手部关键点显示失败，请确认后端服务正在运行');
  }
};

const formatTerminalViolation = (type) => {
  const labels = {
    swap: '快速替换',
    occlusion: '部分遮挡',
    lift: '恶意托举'
  };
  return labels[type] || type || '未知异常';
};

const handleKeyDown = (event) => {
  if (event.key === '1') {
    roiDrawMode.value = true;
    alert('已进入 ROI 标注模式：在视频画面上拖拽鼠标画框，按 2 保存');
  } else if (event.key === '2') {
    saveRoi();
  } else if (event.key === '3') {
    toggleHandOverlay();
  }
};

const startPaymentNotify = () => {
  if (paymentWs) paymentWs.close();

  paymentWs = new WebSocket(`ws://localhost:8000/api/payment/ws/${currentOrderId.value}`);
  paymentWs.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.event === 'payment_success' || data.status === 'completed') {
      paymentSuccess();
    }
  };
  paymentWs.onerror = (error) => console.error("支付通知 WebSocket 异常", error);
};

const startPollingStatus = () => {
  if (pollingInterval) clearInterval(pollingInterval);
  pollingInterval = setInterval(async () => {
    if (paymentStatus.value !== 'pending' || !showPaymentPage.value) return;

    try {
      const response = await fetch(`http://localhost:8000/api/transaction/status/${currentOrderId.value}`);
      const resData = await response.json();

      if (resData.status === 'completed') {
        paymentSuccess();
      }
    } catch (error) {
      console.error("查询支付状态异常", error);
    }
  }, 2000);
};

const paymentSuccess = () => {
  clearInterval(pollingInterval);
  clearInterval(countdownInterval);
  if (mockPaymentTimer) {
    clearTimeout(mockPaymentTimer);
    mockPaymentTimer = null;
  }
  if (paymentWs) {
    paymentWs.close();
    paymentWs = null;
  }
  paymentStatus.value = 'success';
  localStorage.removeItem('pending_payment_order_id');
  localStorage.removeItem('pending_payment_amount');
  localStorage.removeItem('pending_payment_channel');

  setTimeout(() => {
    returnToTerminal();
    cartItems.value = [];
  }, 2500);
};

const returnToTerminal = () => {
  showPaymentPage.value = false;
  if (route.path === '/payment') {
    router.push('/terminal');
  }
};

const cancelPayment = () => {
  if (pollingInterval) clearInterval(pollingInterval);
  if (countdownInterval) clearInterval(countdownInterval);
  if (mockPaymentTimer) {
    clearTimeout(mockPaymentTimer);
    mockPaymentTimer = null;
  }
  if (paymentWs) {
    paymentWs.close();
    paymentWs = null;
  }
  localStorage.removeItem('pending_payment_order_id');
  localStorage.removeItem('pending_payment_amount');
  localStorage.removeItem('pending_payment_channel');
  returnToTerminal();
};

// === 生命周期清理 ===
onMounted(() => {
  window.addEventListener('keydown', handleKeyDown);
  window.addEventListener('resize', syncVideoGeometry);
  loadRoi();
  if (showPaymentPage.value && currentOrderId.value) {
    startCountdown();
    startMockPaymentSuccessTimer();
    startPaymentNotify();
    startPollingStatus();
  }
});

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeyDown);
  window.removeEventListener('resize', syncVideoGeometry);
  if (ws) ws.close();
  if (paymentWs) paymentWs.close();
  if (pollingInterval) clearInterval(pollingInterval);
  if (countdownInterval) clearInterval(countdownInterval);
  if (mockPaymentTimer) clearTimeout(mockPaymentTimer);
});
</script>

<style scoped>
/* 隐藏原生滚动条 */
::-webkit-scrollbar { display: none; }

/* 收银台样式 */
.terminal-container { display: flex; gap: 20px; padding: 20px; background-color: #fff; }
.camera-section { flex: 2; display: flex; flex-direction: column; border: 1px solid #ddd; padding: 20px; border-radius: 8px; }
.cart-section { flex: 1; display: flex; flex-direction: column; border: 1px solid #ddd; padding: 20px; border-radius: 8px; background-color: #f9f9f9; }
.mock-customer-box { display: grid; grid-template-columns: 1fr; gap: 8px; margin-bottom: 14px; padding: 12px; border: 1px dashed #b7d7ff; border-radius: 8px; background: #f0f7ff; }
.mock-customer-box label { font-size: 13px; font-weight: 700; color: #1d4ed8; }
.mock-customer-box select, .mock-customer-box input { width: 100%; padding: 8px 10px; border: 1px solid #bfdbfe; border-radius: 5px; background: #fff; outline: none; }
.mock-customer-box select:focus, .mock-customer-box input:focus { border-color: #2563eb; box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12); }
.video-placeholder { flex: 1; width: 100%; background: #222; display: flex; justify-content: center; align-items: center; color: white; margin: 15px 0; border-radius: 8px; overflow: hidden; position: relative; user-select: none; }
.ws-video { width: 100%; height: 100%; object-fit: contain; }
.roi-box { position: absolute; border: 2px solid #22d3ee; background: rgba(34, 211, 238, 0.18); box-shadow: 0 0 0 9999px rgba(0,0,0,0.12); pointer-events: none; z-index: 4; }
.roi-tip { position: absolute; top: 12px; left: 12px; z-index: 5; background: rgba(2, 6, 23, 0.78); color: #e0f2fe; border: 1px solid #0ea5e9; padding: 6px 10px; border-radius: 6px; font-size: 13px; font-weight: bold; pointer-events: none; }
.hand-overlay-tip { position: absolute; top: 12px; right: 12px; z-index: 5; background: rgba(6, 78, 59, 0.88); color: #d1fae5; border: 1px solid #10b981; padding: 6px 10px; border-radius: 6px; font-size: 13px; font-weight: bold; pointer-events: none; }

.terminal-cheat-backdrop { position: fixed; inset: 0; z-index: 3000; display: flex; align-items: center; justify-content: center; background: rgba(0, 0, 0, 0.7); backdrop-filter: blur(2px); }
.terminal-cheat-panel { width: 520px; max-width: calc(100vw - 32px); overflow: hidden; border: 2px solid #dc2626; border-radius: 10px; background: #1f2937; color: #fff; box-shadow: 0 0 30px rgba(220, 38, 38, 0.65); }
.terminal-cheat-header { padding: 18px 22px; background: #dc2626; font-size: 22px; font-weight: 900; }
.terminal-cheat-body { padding: 22px; }
.terminal-cheat-body p { margin: 0 0 18px; color: #e5e7eb; line-height: 1.65; }
.terminal-cheat-detail { display: flex; justify-content: space-between; gap: 16px; padding: 11px 0; border-top: 1px solid #374151; color: #9ca3af; }
.terminal-cheat-detail strong { color: #fca5a5; }
.terminal-cheat-button { width: 100%; margin-top: 20px; padding: 12px; border: 0; border-radius: 5px; background: #dc2626; color: #fff; cursor: pointer; font-size: 16px; font-weight: 900; }

.current-item-panel {
  background-color: #e3f2fd; border: 2px solid #2196F3; border-radius: 8px;
  padding: 15px; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center;
}
.current-item-panel.empty { background-color: #f5f5f5; border: 2px dashed #ccc; justify-content: center; color: #666; }
.current-item-panel.multi-item-warning { background: #fff1f0; border-color: #ff4d4f; color: #cf1322; }
.current-item-panel.multi-item-warning h3 { margin: 0 0 8px; color: #cf1322; }
.current-item-panel.multi-item-warning p { margin: 0; color: #cf1322; font-weight: 700; }
.item-info h3 { margin: 0 0 10px 0; color: #333; }
.specs { margin-bottom: 8px; }
.spec-block { margin-right: 20px; font-size: 16px; color: #555; }
.spec-block.highlight { color: #d32f2f; }
.calc-total { font-size: 18px; font-weight: bold; margin: 0; color: #2196F3; }
.calc-total span { font-size: 24px; color: #f44336; }
.add-btn { padding: 15px 30px; font-size: 18px; }

.btn { padding: 12px 24px; border: none; border-radius: 6px; cursor: pointer; color: white; font-size: 16px; font-weight: bold; transition: opacity 0.2s; }
.btn:active { opacity: 0.8; }
.btn:disabled { background-color: #9e9e9e; cursor: not-allowed; }
.btn-success { background-color: #4CAF50; }
.btn-danger { background-color: #f44336; }
.btn-primary { background-color: #2196F3; }
.btn-secondary { background-color: #6b7280; }
.controls { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.depth-assist-status { color: #374151; font-weight: 700; font-size: 14px; }
.depth-assist-notice { margin: 8px 0 0; color: #4b5563; font-size: 13px; }
.checkout-btn { width: 100%; margin-top: 15px; font-size: 18px; padding: 15px; }
.btn-remove { background-color: #ff5252; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; margin-left: 10px;}

.item-list { list-style: none; padding: 0; flex: 1; overflow-y: auto; margin: 0; }
.item-list li { display: flex; justify-content: space-between; align-items: center; padding: 15px 0; border-bottom: 1px solid #eee; }
.cart-item-left { display: flex; flex-direction: column; gap: 5px; }
.cart-item-right { display: flex; align-items: center; }
.item-name { font-weight: bold; font-size: 16px; color: #333;}
.item-weight { color: #666; font-size: 14px; }
.item-price { font-size: 18px; font-weight: bold; color: #f44336; }
.total-wrapper { margin-top: auto; padding-top: 20px; border-top: 2px dashed #ddd;}
.total { font-size: 24px; font-weight: bold; text-align: right; color: #f44336; }

/* ================================= */
/* 全屏支付页专有的动画与辅助样式  */
/* ================================= */
@keyframes scan-line {
  0% { top: 0; opacity: 0; }
  10% { opacity: 1; }
  90% { opacity: 1; }
  100% { top: 100%; opacity: 0; }
}
.scanner-line {
  position: absolute; width: 100%; height: 2px; z-index: 10;
  background: #10b981; box-shadow: 0 0 10px #10b981;
  animation: scan-line 2.5s linear infinite;
}
.scanner-line.alipay {
  background: #3b82f6; box-shadow: 0 0 10px #3b82f6;
}
.animate-spin-slow {
  animation: spin 3s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
