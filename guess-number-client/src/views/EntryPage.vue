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
          placeholder="请输入房间号（4 位字母/数字）"
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
          placeholder="请输入你的昵称（2~8 个字符）"
          maxlength="8"
          @input="validatePlayerName"
        />
        <span v-if="playerNameError" class="error-msg">{{ playerNameError }}</span>
      </div>
      
      <!-- 主按钮（动态切换） -->
      <button 
        class="main-btn"
        :class="{ 'shake': shakeButton }"
        @click="handleMainAction"
      >
        {{ mainButtonText }}
      </button>
      
      <!-- 功能反馈 -->
      <div v-if="feedbackMsg" class="feedback" :class="feedbackType">
        {{ feedbackMsg }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { isValidRoomId, isValidPlayerName } from '@/utils/game';
import { useRouter } from 'vue-router';

const router = useRouter();

const roomId = ref('');
const playerName = ref('');
const roomIdError = ref('');
const playerNameError = ref('');
const shakeButton = ref(false);
const feedbackMsg = ref('');
const feedbackType = ref<'success' | 'error'>('success');

const mainButtonText = computed(() => {
  return roomId.value.trim() ? '🚪 加入房间' : '✨ 新建房间';
});

const validateRoomId = () => {
  const value = roomId.value.trim();
  if (value && !isValidRoomId(value)) {
    roomIdError.value = '房间号必须是 4 位字母或数字';
  } else {
    roomIdError.value = '';
  }
};

const validatePlayerName = () => {
  const value = playerName.value.trim();
  if (value && !isValidPlayerName(value)) {
    playerNameError.value = '昵称只能是中文、英文或数字（2-8 个字符）';
  } else {
    playerNameError.value = '';
  }
};

const handleMainAction = async () => {
  // 验证昵称（必填）
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
  
  let targetRoomId = roomId.value.trim().toUpperCase();
  
  if (!targetRoomId) {
    // 新建房间：生成随机房间号
    targetRoomId = generateRoomId();
    roomId.value = targetRoomId;
    
    // 复制到剪贴板
    try {
      await navigator.clipboard.writeText(targetRoomId);
      showFeedback(`房间已创建！房间号 ${targetRoomId} 已复制到剪贴板`, 'success');
    } catch (err) {
      showFeedback(`房间已创建！房间号：${targetRoomId}`, 'success');
    }
    
    // 跳转到等待大厅
    setTimeout(() => {
      router.push({ 
        path: '/lobby', 
        query: { roomId: targetRoomId, playerName: playerName.value.trim(), isHost: 'true' }
      });
    }, 1500);
  } else {
    // 加入房间
    if (!isValidRoomId(targetRoomId)) {
      roomIdError.value = '房间号格式不正确';
      triggerShake();
      return;
    }
    
    // 模拟加入房间（实际应调用后端 API）
    showFeedback('正在加入房间...', 'success');
    setTimeout(() => {
      router.push({ 
        path: '/lobby', 
        query: { roomId: targetRoomId, playerName: playerName.value.trim(), isHost: 'false' }
      });
    }, 1000);
  }
};

const generateRoomId = (): string => {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let result = '';
  for (let i = 0; i < 4; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
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
</script>

<style scoped>
.entry-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.entry-container {
  background: white;
  padding: 40px;
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  width: 100%;
  max-width: 400px;
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

.input-group input::placeholder {
  color: #aaa;
}

.error-msg {
  display: block;
  color: #f44336;
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
