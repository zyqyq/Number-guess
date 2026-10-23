<template>
  <div v-if="ask" class="ask-overlay">
    <div class="ask-card">
      <h2 class="ask-title">👁 旁观申请</h2>
      <p class="ask-name"><b>{{ ask.playerName }}</b> 请求旁观本局</p>
      <label class="ask-opt">
        <input v-model="allowChat" type="checkbox" />
        允许参与聊天
      </label>
      <label class="ask-opt">
        <input v-model="allowVoice" type="checkbox" />
        允许加入语音
      </label>
      <p class="ask-hint">60 秒无响应将自动拒绝</p>
      <div class="ask-actions">
        <button class="ask-deny" type="button" @click="respond(false)">拒绝</button>
        <button class="ask-allow" type="button" @click="respond(true)">允许旁观</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';

interface SpectatorAsk {
  playerId: string;
  playerName: string;
}

const props = defineProps<{ ask: SpectatorAsk | null }>();
const emit = defineEmits<{
  (e: 'respond', payload: { allow: boolean; allowChat: boolean; allowVoice: boolean }): void;
}>();

const allowChat = ref(true);
const allowVoice = ref(true);

// 每来一条新申请都重置为「都允许」，避免沿用上一次的勾选
watch(
  () => props.ask?.playerId,
  (id) => {
    if (id) {
      allowChat.value = true;
      allowVoice.value = true;
    }
  }
);

const respond = (allow: boolean) => {
  emit('respond', { allow, allowChat: allowChat.value, allowVoice: allowVoice.value });
};
</script>

<style scoped>
.ask-overlay {
  position: fixed;
  inset: 0;
  z-index: 150;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(18, 20, 36, 0.55);
}

.ask-card {
  width: min(400px, 90vw);
  padding: 26px 24px 22px;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 20px 52px rgba(0, 0, 0, 0.3);
  text-align: left;
}

.ask-title {
  margin: 0 0 10px;
  font-size: 19px;
  color: #2f3380;
}

.ask-name {
  margin: 0 0 16px;
  font-size: 14px;
  color: #4b4f63;
}

.ask-name b {
  color: #2f3380;
}

.ask-opt {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 14px;
  color: #4b4f63;
  cursor: pointer;
}

.ask-opt input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.ask-hint {
  margin: 4px 0 18px;
  font-size: 12px;
  color: #9096ad;
}

.ask-actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}

.ask-deny,
.ask-allow {
  padding: 11px 10px;
  border-radius: 9px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
}

.ask-deny {
  background: #fff;
  border-color: #d7dbe8;
  color: #6b7189;
}

.ask-deny:hover {
  border-color: #b9c0d6;
  background: #f6f7fb;
}

.ask-allow {
  background: #667eea;
  color: #fff;
}

.ask-allow:hover {
  background: #5568d3;
}
</style>
