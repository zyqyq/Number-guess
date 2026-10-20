<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { wsService } from '@/services/websocket';

const router = useRouter();

onMounted(() => {
  // 管理员强制断开（close code 4001）：全局统一提示并回首页
  wsService.setKickedCallback(() => {
    window.alert('你已被管理员断开连接，请重新进入房间。');
    if (router.currentRoute.value.path !== '/') {
      router.push('/');
    }
  });
});
</script>

<style scoped>
/* 全局样式可在 style.css 中定义 */
</style>
