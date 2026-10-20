<template>
  <div class="entry-page">
    <div class="entry-container">
      <!-- 游戏大标题 -->
      <h1 class="game-title">数字迷踪 · 猜牌对决</h1>
      
      <!-- 房间号输入框 -->
      <div class="input-group">
        <label for="roomId">房间号</label>
        <input 
          id="roomId"
          type="text" 
          v-model="roomId" 
          :readonly="roomReadonly"
          placeholder="请输入房间号（4 位数字）"
          maxlength="4"
          @input="validateRoomId"
        />
        <span v-if="roomIdError" class="error-msg">{{ roomIdError }}</span>
      </div>
      
      <!-- 昵称输入框 -->
      <div class="input-group">
        <label for="playerName">游戏昵称</label>
        <input 
          id="playerName"
          type="text" 
          v-model="playerName" 
          placeholder="请输入你的昵称（最多8 个字符）"
          maxlength="8"
          @input="validatePlayerName(); checkNicknameHint()"
        />
        <span v-if="playerNameError" class="error-msg">{{ playerNameError }}</span>
        <span v-else-if="nicknameWarn" class="warn-msg">{{ nicknameWarn }}</span>
      </div>
      
      <!-- 创建 / 加入 按钮（垂直排列） -->
      <div class="vertical-buttons">
        <button class="main-btn create-btn" @click="handleCreateRoom">✨ 创建房间</button>
        <button class="main-btn join-btn" @click="handleJoinRoom">🚪 加入房间</button>
      </div>
      
      <!-- 功能反馈 -->
      <div v-if="feedbackMsg" class="feedback" :class="feedbackType">
        {{ feedbackMsg }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { isValidRoomId, isValidPlayerName } from '@/utils/game';
import { useRouter, useRoute } from 'vue-router';
import { connectPresence } from '@/services/presence';

// 管理入口口令：默认值与后端一致，实际以 /api/admin/access 返回为准
// （口令已改由 config.json 决定，本机访问时可从后端同步）
const ADMIN_USERNAME = ref('adminzyq');
const ADMIN_ROOM = ref('6666');
const bannedWords = ref<string[]>([]);
const nicknameWarn = ref('');
let stopPresence: (() => void) | null = null;

const router = useRouter();

const roomId = ref('');
const playerName = ref('');
const roomReadonly = ref(false);
const roomIdError = ref('');
const playerNameError = ref('');
const shakeButton = ref(false);
const feedbackMsg = ref('');
const feedbackType = ref<'success' | 'error'>('success');

// 昵称违禁词本地预检（真正拦截在后端握手处）
const checkNicknameHint = () => {
  const name = playerName.value.trim();
  if (!name || bannedWords.value.length === 0) {
    nicknameWarn.value = '';
    return;
  }
  const squeezed = name.toLowerCase().replace(/\s+/g, '');
  const hit = bannedWords.value.find((word) => {
    const needle = word.toLowerCase().replace(/\s+/g, '');
    return needle.length > 0 && squeezed.includes(needle);
  });
  nicknameWarn.value = hit ? `昵称可能包含违禁内容：${hit}` : '';
};

const route = useRoute();

const validateRoomId = () => {
  const value = roomId.value.trim();
    if (value && !isValidRoomId(value)) {
      roomIdError.value = '房间号必须是 4 位数字';
    } else {
      roomIdError.value = '';
    }
};

const validatePlayerName = () => {
  const value = playerName.value.trim();
  if (value && !isValidPlayerName(value)) {
    playerNameError.value = '昵称只能是中文、英文或数字，最长 8 个字符';
  } else {
    playerNameError.value = '';
  }
};

const savePlayerName = (name: string) => {
  try {
    const payload = { name, ts: Date.now() };
    localStorage.setItem('guess_number_player', JSON.stringify(payload));
  } catch (e) {
    // ignore
  }
};

onMounted(async () => {
  // 在线登记：让管理后台能看到「谁打开了页面」（不参与游戏）
  stopPresence = connectPresence();

  // 从 URL 预置房间号
  const urlRoom = String(route.query.roomId || '').trim();
  if (urlRoom) {
    roomId.value = urlRoom;
    roomReadonly.value = true;
  }

  // 从本地缓存恢复昵称（7 天内）
  try {
    const raw = localStorage.getItem('guess_number_player');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.name && parsed.ts && Date.now() - parsed.ts < 7 * 24 * 3600 * 1000) {
        playerName.value = parsed.name;
      }
    }
  } catch (e) {}

  // 查询后端房间列表；若仅存在 1 个房间则自动预填（仍可编辑，方便输入管理入口房间号）
  try {
    const res = await fetch('/api/rooms');
    if (res.ok) {
      const data = await res.json();
      if (data.rooms && data.rooms.length === 1 && !roomId.value) {
        roomId.value = String(data.rooms[0].roomId || '');
      }
    }
  } catch (e) {
    // ignore network errors
  }

  // 同步管理入口口令与违禁词库（本机访问才拿得到口令；局域网设备 403 时保持默认值）
  try {
    const accessRes = await fetch('/api/admin/access', { cache: 'no-store' });
    if (accessRes.ok) {
      const access = await accessRes.json();
      if (access.adminUser) ADMIN_USERNAME.value = String(access.adminUser);
      if (access.adminRoom) ADMIN_ROOM.value = String(access.adminRoom);
    }
  } catch (e) {
    // ignore network errors
  }
  try {
    const wordsRes = await fetch('/api/banned-words', { cache: 'no-store' });
    if (wordsRes.ok) {
      const data = await wordsRes.json();
      bannedWords.value = Array.isArray(data.words) ? data.words.map(String) : [];
    }
  } catch (e) {
    // ignore network errors
  }
});

const handleCreateRoom = async () => {
  if (!playerName.value.trim()) {
    playerNameError.value = '昵称不能为空';
    triggerShake();
    return;
  }
  if (!isValidPlayerName(playerName.value.trim())) {
    playerNameError.value = '昵称格式不正确';
    triggerShake();
    return;
  }
  const targetRoomId = generateRoomId();
  roomId.value = targetRoomId;
  roomReadonly.value = true;
  savePlayerName(playerName.value.trim());
  try { await navigator.clipboard.writeText(targetRoomId); showFeedback(`房间已创建：${targetRoomId}（已复制）`, 'success'); } catch(e) { showFeedback(`房间已创建：${targetRoomId}`, 'success'); }
  setTimeout(() => {
    router.push({ path: '/lobby', query: { roomId: targetRoomId, playerName: playerName.value.trim(), isHost: 'true' } });
  }, 800);
};

const handleJoinRoom = async () => {
  if (!playerName.value.trim()) {
    playerNameError.value = '昵称不能为空';
    triggerShake();
    return;
  }
  if (!isValidPlayerName(playerName.value.trim())) {
    playerNameError.value = '昵称格式不正确';
    triggerShake();
    return;
  }
  const targetRoomId = roomId.value.trim();
  if (!isValidRoomId(targetRoomId)) {
    roomIdError.value = '房间号必须是 4 位数字';
    triggerShake();
    return;
  }

  // 管理入口：昵称 + 保留房间号同时匹配时进入管理后台，不建立游戏连接
  if (targetRoomId === ADMIN_ROOM.value && playerName.value.trim() === ADMIN_USERNAME.value) {
    savePlayerName(playerName.value.trim());
    showFeedback('正在进入管理后台…', 'success');
    stopPresence?.();
    stopPresence = null;
    setTimeout(() => {
      router.push({ path: '/admin' });
    }, 300);
    return;
  }

  // 保留房间号（管理入口）不允许普通昵称占用
  if (targetRoomId === ADMIN_ROOM.value) {
    roomIdError.value = '该房间号已保留';
    showFeedback('该房间号为管理入口，无法加入', 'error');
    triggerShake();
    return;
  }

  savePlayerName(playerName.value.trim());
  showFeedback('正在加入房间...', 'success');
  setTimeout(() => {
    router.push({ path: '/lobby', query: { roomId: targetRoomId, playerName: playerName.value.trim(), isHost: 'false' } });
  }, 600);
};

const generateRoomId = (): string => {
  // 管理入口保留号，随机生成时跳过
  let id = String(Math.floor(1000 + Math.random() * 9000));
  while (id === ADMIN_ROOM.value) {
    id = String(Math.floor(1000 + Math.random() * 9000));
  }
  return id;
};

const triggerShake = () => {
  shakeButton.value = true;
  setTimeout(() => {
    shakeButton.value = false;
  }, 500);
};

const showFeedback = (msg: string, type: 'success' | 'error') => {
  feedbackMsg.value = msg;
  feedbackType.value = type;
  setTimeout(() => {
    feedbackMsg.value = '';
  }, 3000);
};

onUnmounted(() => {
  stopPresence?.();
  stopPresence = null;
});
</script>

<style scoped>
.entry-page {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 0 20px;
}

.entry-container {
  background: white;
  padding: 40px;
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  width: 100%;
  max-width: 420px;
}

.vertical-buttons {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.create-btn {
  background: linear-gradient(45deg, #43a047, #66bb6a);
}

.join-btn {
  background: linear-gradient(45deg, #667eea, #764ba2);
}

.game-title {
  text-align: center;
  font-size: 28px;
  font-weight: bold;
  color: #333;
  margin-bottom: 32px;
  background: linear-gradient(45deg, #667eea, #764ba2);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.input-group {
  margin-bottom: 24px;
}

.input-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: bold;
  color: #555;
  font-size: 14px;
}

.input-group input {
  width: 100%;
  padding: 12px 16px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  font-size: 16px;
  transition: border-color 0.2s ease;
  box-sizing: border-box;
}

.input-group input:focus {
  outline: none;
  border-color: #667eea;
}

.input-group input[readonly] {
  background: #f2f2f2;
  color: #666;
  cursor: not-allowed;
}

.input-group input::placeholder {
  color: #aaa;
}

.error-msg {
  display: block;
  color: #f44336;
  font-size: 12px;
  margin-top: 4px;
}

.warn-msg {
  display: block;
  color: #b45309;
  font-size: 12px;
  margin-top: 4px;
}

.main-btn {
  width: 100%;
  padding: 14px;
  background: linear-gradient(45deg, #667eea, #764ba2);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 18px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-bottom: 16px;
}

.main-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.main-btn:active {
  transform: translateY(0);
}

.main-btn.shake {
  animation: shake 0.5s ease-in-out;
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-10px); }
  50% { transform: translateX(10px); }
  75% { transform: translateX(-10px); }
}

.feedback {
  padding: 12px;
  border-radius: 8px;
  text-align: center;
  font-size: 14px;
  animation: fadeIn 0.3s ease;
}

.feedback.success {
  background: #e8f5e9;
  color: #2e7d32;
}

.feedback.error {
  background: #ffebee;
  color: #c62828;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
