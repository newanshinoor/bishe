<template>
  <div class="app-layout">
    <nav class="dev-nav" v-if="$route && $route.path !== '/login'">
      <span class="nav-title">果蔬系统导航：</span>
      <router-link to="/">💻 智能终端主页</router-link> |
      <router-link to="/admin">⚙️ 商家运营后台</router-link> |
      <a href="#" class="logout-btn" @click.prevent="handleLogout">🚪 退出登录</a>
    </nav>

    <div class="main-view">
      <router-view></router-view>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

const handleLogout = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  router.push('/login')
}
</script>

<style>
.app-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  width: 100vw;
}

body {
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.dev-nav {
  background-color: #2c3e50;
  padding: 15px 20px;
  color: white;
  flex-shrink: 0;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  z-index: 10;
  display: flex;
  align-items: center;
}

.dev-nav a {
  color: #42b983;
  text-decoration: none;
  font-weight: bold;
  padding: 0 15px;
  transition: 0.3s;
}

.dev-nav a:hover {
  color: #65dca3;
}

.dev-nav a.router-link-exact-active {
  color: #fff;
  text-decoration: underline;
}

.nav-title {
  color: #ccc;
  font-size: 14px;
  margin-right: 10px;
}

.logout-btn {
  margin-left: auto;
  color: #ff7875 !important;
}

.logout-btn:hover {
  color: #ff4d4f !important;
}

.main-view {
  flex: 1;
  display: flex;
  overflow: auto;
}
</style>