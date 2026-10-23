<template>
  <div class="entry-page">
    <div class="entry-shell">
    <div class="entry-container">
      <!-- 游戏大标题 -->
      <h1 class="game-title">数字迷踪 · 猜牌对决</h1>
      
      <!-- 房间号输入框（分享链接带入时只读，并提供「换个房间」清空） -->
      <div class="input-group">
        <label for="roomId">房间号</label>
        <div class="input-row">
          <input 
            id="roomId"
            type="text" 
            v-model="roomId" 
            :readonly="roomReadonly"
            placeholder="请输入房间号（4 位数字）"
            maxlength="4"
            @input="validateRoomId"
          />
          <button
            v-if="roomReadonly"
            type="button"
            class="clear-room-btn"
            title="换个房间"
            @click="clearSharedRoom"
          >✕</button>
        </div>
        <span v-if="shareHint" class="share-hint">{{ shareHint }}</span>
        <span v-if="roomIdError" class="error-msg">{{ roomIdError }}</span>
      </div>
      
      <!-- 昵称输入框 -->
      <div class="input-group">
        <label for="playerName">游戏昵称</label>
        <input 
          id="playerName"
          ref="nicknameInput"
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
        <!-- 加入房间：右侧小箭头纵向展开，露出「旁观加入」 -->
        <div class="join-split" :class="{ open: joinMenuOpen }">
          <button class="main-btn join-btn" @click="handleJoinRoom">🚪 加入房间</button>
          <button
            class="join-arrow"
            type="button"
            :aria-expanded="joinMenuOpen"
            aria-label="更多加入方式"
            title="更多加入方式"
            @click.stop="joinMenuOpen = !joinMenuOpen"
          >▾</button>
          <transition name="menu-fade">
            <div v-if="joinMenuOpen" class="join-menu" @click.stop>
              <button type="button" class="join-menu-item" @click="handleSpectateJoin">
                <span class="jmi-title">👁 旁观加入</span>
                <span class="jmi-sub">只观战不占名额；等人阶段直接进入，牌局中需房主同意</span>
              </button>
            </div>
          </transition>
        </div>
      </div>
      
      <!-- 功能反馈 -->
      <div v-if="feedbackMsg" class="feedback" :class="feedbackType">
        {{ feedbackMsg }}
      </div>
      </div>

      <!-- 右侧：公开房间列表（仅等人中 / 进行中，隐身房间不出现）
           管理员可在后台整体关闭：关闭后这里什么都不渲染，与加入该功能前一致 -->
      <aside v-if="roomListEnabled" class="room-panel">
        <div class="room-panel-head">
          <h2 class="room-panel-title">🎲 房间列表</h2>
          <span class="room-panel-count">{{ rooms.length }} 间可加入</span>
          <button class="room-refresh" type="button" title="立即刷新" @click="loadRooms">↻</button>
        </div>

        <div v-if="rooms.length" class="room-list">
          <div
            v-for="room in rooms"
            :key="room.roomId"
            class="room-item"
            :class="{
              playing: room.gamePhase === 'PLAYING',
              'room-full': room.playerCount >= (room.maxPlayers || 4)
            }"
            :data-room-id="room.roomId"
            role="button"
            tabindex="0"
            :title="roomJoinable(room) ? '点击加入这个房间' : '点击以旁观者身份进入'"
            @click="joinFromList(room)"
            @keydown.enter="joinFromList(room)"
          >
            <span class="room-item-top">
              <span class="room-item-id">{{ room.roomId }}</span>
              <span class="room-item-phase">{{ phaseLabel(room) }}</span>
            </span>
            <span class="room-item-meta">
              <span class="room-item-host">{{ room.hostName || '房主未知' }}</span>
              <span class="room-item-count">{{ room.playerCount }}/{{ room.maxPlayers || 4 }}</span>
            </span>
            <button
              class="room-spectate-btn"
              type="button"
              title="以旁观者身份进入（不影响牌局）"
              @click.stop="spectateFromList(room)"
            >👁</button>
          </div>
        </div>
        <p v-else class="room-empty">
          暂无公开房间<br />
          <small>创建一间等人，或让朋友把分享链接发给你</small>
        </p>

        <p class="room-panel-foot">每 4 秒自动刷新 · 隐身房间不显示</p>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { isValidRoomId, isValidPlayerName } from '@/utils/game';
import { useRouter, useRoute } from 'vue-router';
import { connectPresence } from '@/services/presence';
import { useGameStore } from '@/stores/game';

// 管理入口口令：默认值与后端一致，实际以 /api/admin/access 返回为准
// （口令已改由 config.json 决定，本机访问时可从后端同步）
const ADMIN_USERNAME = ref('adminzyq');
const ADMIN_ROOM = ref('6666');
const bannedWords = ref<string[]>([]);
const nicknameWarn = ref('');
let stopPresence: (() => void) | null = null;

const router = useRouter();
const gameStore = useGameStore();

// 公开房间列表项（与后端 /api/rooms 对齐）
interface PublicRoom {
  roomId: string;
  playerCount: number;
  maxPlayers?: number;
  gamePhase: string;
  hostName?: string | null;
  spectatorCount?: number;
  createdAt?: number;
}

const roomId = ref('');
const playerName = ref('');
const roomReadonly = ref(false);
const roomIdError = ref('');
const playerNameError = ref('');
const joinMenuOpen = ref(false);
const shakeButton = ref(false);
const feedbackMsg = ref('');
const feedbackType = ref<'success' | 'error'>('success');

// 房间列表：4 秒轮询；是否展示由管理员在后台开关（关闭时后端直接返回空列表，
// 前端连占位都不渲染）。默认关闭，避免首帧闪出一个「暂无房间」的面板。
const rooms = ref<PublicRoom[]>([]);
const roomListEnabled = ref(false);
const roomsLoading = ref(false);
let roomPollTimer: number | undefined;
const shareHint = ref('');
const nicknameInput = ref<HTMLInputElement | null>(null);

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

  // 从 URL 预置房间号（同时支持 ?roomId= 与更短的 ?room=）
  const urlRoom = String(route.query.roomId || route.query.room || '').trim();
  if (urlRoom) {
    roomId.value = urlRoom;
    roomReadonly.value = true;
    shareHint.value = `已从分享链接带入房间 ${urlRoom}`;
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

  // 公开房间列表：首屏加载 + 每 4 秒轮询（页面隐藏时跳过，避免无意义请求）
  await loadRooms();
  roomPollTimer = window.setInterval(() => {
    if (!document.hidden) void loadRooms();
  }, 4000);

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

const loadRooms = async () => {
  if (roomsLoading.value) return;
  roomsLoading.value = true;
  try {
    const res = await fetch('/api/rooms', { cache: 'no-store' });
    if (!res.ok) return;
    const data = await res.json();
    roomListEnabled.value = data.enabled !== false;
    rooms.value = roomListEnabled.value && Array.isArray(data.rooms) ? (data.rooms as PublicRoom[]) : [];
  } catch (e) {
    // 网络异常时保留上一次结果，避免列表闪空
  } finally {
    roomsLoading.value = false;
  }
};

const phaseLabel = (room: PublicRoom) => {
  if (room.gamePhase === 'PLAYING') return '游戏中';
  return room.playerCount >= (room.maxPlayers || 4) ? '已满' : '等人中';
};

// 只有「等人中且未满员」的房间能直接加入；已开局 / 满员改为以旁观者身份进入（D2）
const roomJoinable = (room: PublicRoom) =>
  room.gamePhase === 'WAITING' && room.playerCount < (room.maxPlayers || 4);

const joinFromList = async (room: PublicRoom) => {
  if (!roomJoinable(room)) {
    // D2：满员或已开局不再拦人，直接落地成旁观看牌
    spectateFromList(room);
    return;
  }
  roomId.value = room.roomId;
  roomReadonly.value = false;
  roomIdError.value = '';
  shareHint.value = '';
  if (!playerName.value.trim()) {
    nicknameInput.value?.focus();
    showFeedback(`已填入房间号 ${room.roomId}，输入昵称后点「加入房间」`, 'success');
    return;
  }
  await handleJoinRoom();
};

/** 房间号 + 昵称的统一校验；通过时返回规整后的值 */
const prepareEntry = (): { roomId: string; name: string } | null => {
  const name = playerName.value.trim();
  if (!name) {
    playerNameError.value = '昵称不能为空';
    triggerShake();
    return null;
  }
  if (!isValidPlayerName(name)) {
    playerNameError.value = '昵称格式不正确';
    triggerShake();
    return null;
  }
  const target = roomId.value.trim();
  if (!isValidRoomId(target)) {
    roomIdError.value = '房间号必须是 4 位数字';
    triggerShake();
    return null;
  }
  return { roomId: target, name };
};

/** 统一入口：旁观一律先进 /game，房间若还没开局，游戏页会立刻把人转去等待界面 */
const goSpectate = (targetRoomId: string, name: string) => {
  savePlayerName(name);
  // 换房间先清空上一间的残留（聊天记录 / 手牌 / 旁观身份）
  gameStore.resetState();
  router.push({
    path: '/game',
    query: { roomId: targetRoomId, playerName: name, spectate: '1' }
  });
};

/** 房间列表里点「👁」：直接旁观某个房间 */
const spectateFromList = (room: PublicRoom) => {
  const name = playerName.value.trim();
  if (!name) {
    nicknameInput.value?.focus();
    showFeedback('先输入昵称，才能以旁观者身份进入', 'error');
    return;
  }
  if (!isValidPlayerName(name)) {
    playerNameError.value = '昵称格式不正确';
    triggerShake();
    return;
  }
  goSpectate(room.roomId, name);
};

/** 「加入房间」旁的小箭头展开的「旁观加入」：用输入框里的房间号旁观 */
const handleSpectateJoin = () => {
  joinMenuOpen.value = false;
  const value = prepareEntry();
  if (!value) return;
  if (value.roomId === ADMIN_ROOM.value) {
    roomIdError.value = '该房间号已保留';
    showFeedback('该房间号为管理入口，无法旁观', 'error');
    triggerShake();
    return;
  }
  goSpectate(value.roomId, value.name);
};

const clearSharedRoom = () => {
  roomId.value = '';
  roomReadonly.value = false;
  roomIdError.value = '';
  shareHint.value = '';
};

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
  // 新建房间：清掉上一间残留的状态，新房间聊天室从空开始
  gameStore.resetState();
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
  gameStore.resetState();
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

// 点空白处收起「旁观加入」菜单
const onDocumentClick = (e: MouseEvent) => {
  if (!joinMenuOpen.value) return;
  const el = e.target as HTMLElement | null;
  if (el && el.closest('.join-split')) return;
  joinMenuOpen.value = false;
};

onMounted(() => document.addEventListener('click', onDocumentClick));

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick);
  stopPresence?.();
  stopPresence = null;
  if (roomPollTimer !== undefined) {
    window.clearInterval(roomPollTimer);
    roomPollTimer = undefined;
  }
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
  padding: 24px 20px;
  overflow-y: auto;
  box-sizing: border-box;
}

/* 左：登录卡；右：公开房间列表 */
.entry-shell {
  display: flex;
  align-items: stretch;
  justify-content: center;
  gap: 18px;
  width: 100%;
  max-width: 840px;
}

.entry-container {
  flex: 0 0 420px;
  background: white;
  padding: 40px;
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  width: 100%;
  max-width: 420px;
  box-sizing: border-box;
}

/* ---- 房间列表 ---- */
.room-panel {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: rgba(255, 255, 255, 0.94);
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  padding: 20px;
  box-sizing: border-box;
}

.room-panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.room-panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #333;
}

.room-panel-count {
  font-size: 12px;
  color: #8b8b9a;
}

.room-refresh {
  margin-left: auto;
  width: 28px;
  height: 28px;
  border: 1px solid #dcdce6;
  border-radius: 8px;
  background: #fff;
  color: #666;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.room-refresh:hover {
  border-color: #667eea;
  color: #667eea;
}

.room-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 340px;
  overflow-y: auto;
}

/* 紧凑列表：一行一间（唯一的展示形式） */
.room-item {
  position: relative;
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid #e6e6f0;
  border-radius: 10px;
  background: #fff;
  text-align: left;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
}

/* 每行右侧的「旁观」入口：不占额外高度，悬浮在行内 */
.room-spectate-btn {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #dfe3f7;
  border-radius: 7px;
  background: #f6f7ff;
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  transition: all 0.15s;
}

.room-spectate-btn:hover {
  border-color: #667eea;
  background: #eef0ff;
}

.room-item:hover {
  border-color: #667eea;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.18);
  transform: translateY(-1px);
}

.room-item.playing {
  background: #fafafa;
}

.room-item-top {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  flex: 1 1 auto;
  min-width: 0;
}

.room-item-id {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: #4a4fa2;
}

.room-item.playing .room-item-id {
  color: #8a8f9c;
}

.room-item-phase {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 999px;
  background: #eef0ff;
  color: #5b62d0;
  white-space: nowrap;
}

.room-item.playing .room-item-phase {
  background: #f1f1f5;
  color: #8a8f9c;
}

.room-item.room-full .room-item-phase {
  background: #fff2e6;
  color: #c2751b;
}

.room-item-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  flex: 0 0 auto;
  font-size: 11px;
  color: #8b8b9a;
}

.room-item-host {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 72px;
}

.room-empty {
  margin: 0;
  padding: 26px 8px;
  text-align: center;
  font-size: 13px;
  line-height: 1.8;
  color: #8b8b9a;
}

.room-panel-foot {
  margin: 0;
  text-align: center;
  font-size: 11px;
  color: #9a9aa8;
}

/* ---- 输入行：只读房间号 + 清除按钮 ---- */
.input-row {
  display: flex;
  gap: 8px;
}

.input-row input {
  flex: 1 1 auto;
  min-width: 0;
}

.clear-room-btn {
  flex: 0 0 auto;
  width: 44px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  background: #fff;
  color: #888;
  font-size: 15px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.clear-room-btn:hover {
  border-color: #ef5350;
  color: #ef5350;
}

.share-hint {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: #5b62d0;
}

@media (max-width: 900px) {
  .entry-page {
    align-items: flex-start;
  }

  .entry-shell {
    flex-direction: column;
  }

  .entry-container {
    flex: 0 0 auto;
    max-width: none;
    padding: 28px 24px;
  }

  .room-list {
    max-height: none;
  }
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

/* ---- 加入房间 / 旁观加入（右侧小箭头纵向展开） ---- */
.join-split {
  position: relative;
  display: flex;
  align-items: stretch;
  margin-bottom: 16px;
}

.join-split .join-btn {
  flex: 1 1 auto;
  width: auto;
  margin-bottom: 0;
  border-radius: 8px 0 0 8px;
}

.join-arrow {
  flex: 0 0 46px;
  border: none;
  border-left: 1px solid rgba(255, 255, 255, 0.35);
  border-radius: 0 8px 8px 0;
  background: linear-gradient(45deg, #667eea, #764ba2);
  color: #fff;
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  transition: filter 0.2s ease;
}

.join-arrow:hover {
  filter: brightness(1.12);
}

.join-split.open .join-arrow {
  filter: brightness(0.9);
  transform: rotate(180deg);
}

.join-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  z-index: 30;
  padding: 6px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  box-shadow: 0 10px 28px rgba(38, 45, 80, 0.18);
}

.join-menu-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 9px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  text-align: left;
  font-family: inherit;
  cursor: pointer;
}

.join-menu-item:hover {
  background: #eef2ff;
}

.jmi-title {
  font-size: 14px;
  font-weight: 700;
  color: #312e81;
}

.jmi-sub {
  font-size: 11px;
  line-height: 1.5;
  color: #64748b;
}

.menu-fade-enter-active,
.menu-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.menu-fade-enter-from,
.menu-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
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
