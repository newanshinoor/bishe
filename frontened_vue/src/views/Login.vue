<template>
  <div class="login-container">
    <div class="login-card">
      <div class="brand-section">
        <h1 class="logo-text">Fruit AI ERP</h1>
        <p class="slogan">智能无人果蔬系统</p>
        <div class="glass-decoration"></div>
      </div>

      <div class="form-section">
        <div v-if="mode === 'login'" class="fade-in">
          <h2>欢迎回来</h2>
          <p class="subtitle">请登录您的管理员账号</p>
          <div class="input-group">
            <input type="text" v-model="loginForm.username" placeholder="用户名" />
          </div>
          <div class="input-group">
            <input type="password" v-model="loginForm.password" placeholder="密码" />
          </div>
          <button class="btn-primary" @click="handleLogin">登 录</button>
          <div class="form-links">
            <span @click="mode = 'forgot'">忘记密码？(邮箱找回)</span>
            <span @click="mode = 'register'">立即注册</span>
          </div>
        </div>

        <div v-else-if="mode === 'register'" class="fade-in">
          <h2>创建新账号</h2>
          <p class="subtitle">注册系统运营权限</p>
          <div class="input-group">
            <input type="text" v-model="registerForm.username" placeholder="设置用户名" />
          </div>
          <div class="input-group">
            <input type="email" v-model="registerForm.email" placeholder="输入常用邮箱 (用于找回密码)" />
          </div>
          <div class="input-group">
            <input type="password" v-model="registerForm.password" placeholder="设置密码" />
          </div>
          <button class="btn-primary" @click="handleRegister">注 册</button>
          <div class="form-links center">
            <span @click="mode = 'login'">已有账号？返回登录</span>
          </div>
        </div>

        <div v-else-if="mode === 'forgot'" class="fade-in">
          <h2>找回密码</h2>
          <p class="subtitle">通过绑定的电子邮箱重置</p>
          <div class="input-group">
            <input type="email" v-model="forgotForm.email" placeholder="绑定的邮箱地址" />
          </div>
          <div class="input-group code-group">
            <input type="text" v-model="forgotForm.code" placeholder="6位数字验证码" />
            <button class="btn-send-code" :disabled="countdown > 0" @click="sendEmail">
              {{ countdown > 0 ? `${countdown}s 后重发` : '获取验证码' }}
            </button>
          </div>
          <div class="input-group">
            <input type="password" v-model="forgotForm.new_password" placeholder="输入新密码" />
          </div>
          <button class="btn-primary" @click="handleReset">重置密码</button>
          <div class="form-links center">
            <span @click="mode = 'login'">记起密码了？返回登录</span>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import api from '../utils/api';

const router = useRouter();

const mode = ref('login');

const loginForm = ref({ username: '', password: '' });
const registerForm = ref({ username: '', email: '', password: '' });
const forgotForm = ref({ email: '', code: '', new_password: '' });

const countdown = ref(0);

const handleLogin = async () => {
  if (!loginForm.value.username || !loginForm.value.password) return alert("请填写完整！");
  try {
    const res = await api.post('/login', loginForm.value);
    if (res.data.status === 'success') {
      alert("登录成功！");

      // 保存 Token 和用户名到 localStorage
      localStorage.setItem('token', res.data.token);
      localStorage.setItem('username', res.data.username);

      router.push('/admin');
    } else {
      alert(res.data.message);
    }
  } catch (error) {
    alert("网络错误，请检查后端运行状态");
  }
};

const handleRegister = async () => {
  if (!registerForm.value.username || !registerForm.value.email || !registerForm.value.password) return alert("请填写完整！");
  try {
    const res = await api.post('/register', registerForm.value);
    if (res.data.status === 'success') {
      alert("注册成功！去登录吧");
      mode.value = 'login';
    } else {
      alert(res.data.message);
    }
  } catch (error) {
    alert("网络错误");
  }
};

const sendEmail = async () => {
  if (!forgotForm.value.email) return alert("请先填写邮箱");
  try {
    const res = await api.post('/send_email', { email: forgotForm.value.email });
    if (res.data.status === 'success') {
      alert("邮件已发送！请查看运行后端的终端黑框。");
      countdown.value = 60;
      const timer = setInterval(() => {
        countdown.value--;
        if (countdown.value <= 0) clearInterval(timer);
      }, 1000);
    } else {
      alert(res.data.message);
    }
  } catch (error) {
    alert("网络错误");
  }
};

const handleReset = async () => {
  if (!forgotForm.value.email || !forgotForm.value.code || !forgotForm.value.new_password) return alert("请填写完整！");
  try {
    const res = await api.post('/reset_password', forgotForm.value);
    if (res.data.status === 'success') {
      alert("密码修改成功！请重新登录");
      mode.value = 'login';
    } else {
      alert(res.data.message);
    }
  } catch (error) {
    alert("网络错误");
  }
};
</script>

<style scoped>
/* 充满高级感的居中布局 */
.login-container { height: 100vh; width: 100vw; display: flex; justify-content: center; align-items: center; background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;}
.login-card { display: flex; width: 850px; height: 500px; background: white; border-radius: 20px; box-shadow: 0 20px 40px rgba(0,0,0,0.1); overflow: hidden;}

/* 左侧品牌区 */
.brand-section { flex: 1.2; background: linear-gradient(135deg, #1890ff 0%, #0050b3 100%); color: white; padding: 40px; display: flex; flex-direction: column; justify-content: center; position: relative; overflow: hidden;}
.logo-text { font-size: 42px; font-weight: 800; margin: 0; z-index: 2;}
.slogan { font-size: 18px; margin-top: 10px; opacity: 0.9; z-index: 2;}
.glass-decoration { position: absolute; width: 300px; height: 300px; background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); border-radius: 50%; bottom: -100px; right: -50px; transform: rotate(45deg);}

/* 右侧表单区 */
.form-section { flex: 1; padding: 50px 40px; display: flex; flex-direction: column; justify-content: center; background: white;}
h2 { margin: 0 0 5px 0; color: #333; font-size: 28px;}
.subtitle { color: #888; margin-bottom: 30px; font-size: 14px;}
.input-group { margin-bottom: 20px; position: relative;}
.input-group input { width: 100%; padding: 12px 15px; border: 1px solid #e0e0e0; border-radius: 8px; font-size: 15px; outline: none; transition: 0.3s; box-sizing: border-box; background: #fafafa;}
.input-group input:focus { border-color: #1890ff; background: white; box-shadow: 0 0 0 3px rgba(24,144,255,0.1);}
.code-group { display: flex; gap: 10px;}
.code-group input { flex: 1;}
.btn-send-code { padding: 0 15px; border: 1px solid #1890ff; background: transparent; color: #1890ff; border-radius: 8px; cursor: pointer; white-space: nowrap; transition: 0.3s;}
.btn-send-code:disabled { border-color: #ccc; color: #ccc; cursor: not-allowed;}
.btn-primary { width: 100%; padding: 12px; background: #1890ff; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; transition: 0.3s; margin-top: 10px; box-shadow: 0 4px 10px rgba(24,144,255,0.3);}
.btn-primary:hover { background: #40a9ff; transform: translateY(-1px);}

.form-links { display: flex; justify-content: space-between; margin-top: 20px; font-size: 14px;}
.form-links span { color: #666; cursor: pointer; transition: 0.3s;}
.form-links span:hover { color: #1890ff; text-decoration: underline;}
.form-links.center { justify-content: center;}

.fade-in { animation: fadeIn 0.4s ease-in-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
</style>