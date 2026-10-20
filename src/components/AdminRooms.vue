<template>
  <section class="admin-section">
    <div class="section-head">
      <div>
        <h2>房间管理</h2>
        <p class="section-desc">
          共 {{ rooms.length }} 个房间：游戏中 {{ counts.PLAYING }} · 等待中 {{ counts.WAITING }} · 已结束
          {{ counts.GAME_OVER }}
        </p>
      </div>
      <p class="hint">重置会清空手牌与线索并回到等待阶段；关闭房间会断开房内所有连接。</p>
    </div>

    <div v-if="!rooms.length" class="empty-state">
      <div class="empty-icon">🃏</div>
      <p>当前没有房间。玩家在首页创建房间后会出现在这里。</p>
    </div>

    <div v-else class="room-grid">
      <article v-for="room in rooms" :key="room.roomId" class="room-card" :class="`phase-${room.gamePhase}`">
        <header class="room-head">
          <div class="room-title">
            <span class="room-label">房间</span>
            <strong class="room-no">{{ room.roomId }}</strong>
          </div>
          <span class="phase-badge">{{ phaseLabel(room.gamePhase) }}</span>
        </header>

        <dl class="room-meta">
          <div><dt>轮次</dt><dd>{{ room.roundNumber }}</dd></div>
          <div><dt>时长</dt><dd>{{ fmtDuration(room.durationSeconds) }}</dd></div>
          <div><dt>存活</dt><dd>{{ room.aliveCount }}/{{ room.playerCount }}</dd></div>
          <div><dt>阶段</dt><dd>{{ subPhaseLabel(room.subPhase) }}</dd></div>
        </dl>

        <ul class="member-list">
          <li v-for="player in room.players" :key="player.playerId" class="member">
            <span class="member-dot" :class="{ offline: !player.isOnline && !player.isBot, turn: player.playerId === room.currentTurnPlayerId }"></span>
            <span class="member-name" :class="{ dead: !player.isAlive }">{{ player.playerName }}</span>
            <span v-if="player.isHost" class="tag host">房主</span>
            <span v-if="player.isBot" class="tag bot">机器人</span>
            <span v-else-if="!player.isOnline" class="tag offline">离线</span>
            <span v-if="player.playerId === room.currentTurnPlayerId" class="tag turn">回合</span>
            <button v-if="!player.isBot" class="mini-btn" title="把该玩家移出房间" @click="kickPlayer(room, player)">
              移出
            </button>
          </li>
          <li v-if="!room.players.length" class="member empty">房间内暂无玩家</li>
        </ul>

        <footer class="room-actions">
          <span class="room-created">创建于 {{ fmtDateTime(room.createdAt) }}</span>
          <div class="action-group">
            <button class="ghost-btn" @click="act('AdminResetRoom', room)">重置牌局</button>
            <button class="danger-btn" @click="closeRoom(room)">关闭房间</button>
          </div>
        </footer>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { AdminRoom, AdminRoomPlayer } from '@/types/admin';
import { fmtDateTime, fmtDuration, phaseLabel, subPhaseLabel } from '@/utils/admin';

const props = defineProps<{ rooms: AdminRoom[] }>();

const emit = defineEmits<{
  (e: 'action', payload: { cmd: string; roomId: string; playerId?: string }): void;
}>();

const counts = computed(() => ({
  PLAYING: props.rooms.filter((r) => r.gamePhase === 'PLAYING').length,
  WAITING: props.rooms.filter((r) => r.gamePhase === 'WAITING').length,
  GAME_OVER: props.rooms.filter((r) => r.gamePhase === 'GAME_OVER').length,
}));

const act = (cmd: string, room: AdminRoom, playerId?: string) => {
  emit('action', { cmd, roomId: room.roomId, playerId });
};

const closeRoom = (room: AdminRoom) => {
  if (!window.confirm(`确定关闭房间 ${room.roomId} 吗？房内所有玩家会被断开连接。`)) return;
  act('AdminCloseRoom', room);
};

const kickPlayer = (room: AdminRoom, player: AdminRoomPlayer) => {
  if (!window.confirm(`确定把「${player.playerName}」移出房间 ${room.roomId} 吗？`)) return;
  act('AdminKickPlayer', room, player.playerId);
};
</script>

<style scoped>
.admin-section {
  background: #fff;
  border: 1px solid var(--admin-border);
  border-radius: 14px;
  padding: 18px 20px 20px;
  box-shadow: var(--admin-shadow);
}

.section-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.section-head h2 {
  margin: 0 0 4px;
  font-size: 16px;
  color: var(--admin-text);
}

.section-desc {
  margin: 0;
  font-size: 12px;
  color: var(--admin-muted);
}

.hint {
  margin: 0;
  font-size: 12px;
  color: var(--admin-muted);
}

.empty-state {
  padding: 56px 20px;
  text-align: center;
  color: var(--admin-muted);
  border: 1px dashed var(--admin-border);
  border-radius: 12px;
  background: #fafbfd;
}

.empty-icon {
  font-size: 28px;
  margin-bottom: 8px;
}

.room-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}

.room-card {
  flex: 1 1 400px;
  max-width: 560px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background: #fff;
  border: 1px solid var(--admin-border);
  border-left: 3px solid #cbd5e1;
  border-radius: 12px;
  transition: box-shadow 0.15s ease, transform 0.15s ease;
}

.room-card:hover {
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08);
  transform: translateY(-1px);
}

.room-card.phase-PLAYING {
  border-left-color: #4f46e5;
}

.room-card.phase-WAITING {
  border-left-color: #0ea5e9;
}

.room-card.phase-GAME_OVER {
  border-left-color: #94a3b8;
}

.room-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.room-title {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.room-label {
  font-size: 12px;
  color: var(--admin-muted);
}

.room-no {
  font-size: 20px;
  letter-spacing: 0.5px;
  color: var(--admin-text);
  font-variant-numeric: tabular-nums;
}

.phase-badge {
  padding: 3px 10px;
  font-size: 12px;
  border-radius: 999px;
  color: #3730a3;
  background: #eef2ff;
}

.phase-WAITING .phase-badge {
  color: #0369a1;
  background: #e0f2fe;
}

.phase-GAME_OVER .phase-badge {
  color: #475569;
  background: #f1f5f9;
}

.room-meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
  padding: 10px 12px;
  background: #f8fafc;
  border-radius: 9px;
}

.room-meta div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.room-meta dt {
  font-size: 11px;
  color: var(--admin-muted);
}

.room-meta dd {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--admin-text);
  font-variant-numeric: tabular-nums;
}

.member-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.member {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 8px;
  font-size: 13px;
  border-radius: 8px;
  background: #fbfcfe;
}

.member.empty {
  justify-content: center;
  color: var(--admin-muted);
  font-size: 12px;
}

.member-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #16a34a;
  flex: none;
}

.member-dot.offline {
  background: #cbd5e1;
}

.member-dot.turn {
  background: #f59e0b;
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.18);
}

.member-name {
  color: var(--admin-text);
  font-weight: 500;
}

.member-name.dead {
  color: #94a3b8;
  text-decoration: line-through;
}

.tag {
  padding: 1px 6px;
  font-size: 11px;
  border-radius: 5px;
  line-height: 1.6;
}

.tag.host {
  color: #92400e;
  background: #fef3c7;
}

.tag.bot {
  color: #5b21b6;
  background: #ede9fe;
}

.tag.offline {
  color: #64748b;
  background: #f1f5f9;
}

.tag.turn {
  color: #b45309;
  background: #ffedd5;
}

.mini-btn {
  margin-left: auto;
  padding: 3px 8px;
  font-size: 11px;
  color: #64748b;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  cursor: pointer;
  opacity: 0;
  transition: all 0.15s ease;
}

.member:hover .mini-btn {
  opacity: 1;
}

.mini-btn:hover {
  color: #b91c1c;
  border-color: #fecaca;
  background: #fef2f2;
}

.room-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--admin-border);
}

.room-created {
  font-size: 11px;
  color: var(--admin-muted);
}

.action-group {
  display: flex;
  gap: 8px;
}

.ghost-btn {
  padding: 6px 12px;
  font-size: 12px;
  color: #334155;
  background: #fff;
  border: 1px solid var(--admin-border);
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.ghost-btn:hover {
  border-color: #94a3b8;
  background: #f8fafc;
}

.danger-btn {
  padding: 6px 12px;
  font-size: 12px;
  color: #b91c1c;
  background: #fff;
  border: 1px solid #fecaca;
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.danger-btn:hover {
  color: #fff;
  background: #dc2626;
  border-color: #dc2626;
}
</style>
