<template>
  <section class="admin-section">
    <div class="section-head">
      <div>
        <h2>连入终端</h2>
        <p class="section-desc">
          共 {{ terminals.length }} 条记录，在线 {{ onlineCount }} 台。列表每 2 秒自动刷新。
        </p>
      </div>
      <div class="section-tools">
        <div class="chips">
          <button
            v-for="f in filters"
            :key="f.key"
            class="chip"
            :class="{ active: activeFilter === f.key }"
            @click="activeFilter = f.key"
          >
            {{ f.label }}
            <span class="chip-count">{{ countOf(f.key) }}</span>
          </button>
        </div>
        <input v-model="keyword" class="search-input" type="text" placeholder="搜索昵称 / IP / 房间号" />
      </div>
    </div>

    <div class="table-wrap">
      <table class="admin-table">
        <thead>
          <tr>
            <th class="col-status">状态</th>
            <th>昵称</th>
            <th>IP 地址</th>
            <th>类型</th>
            <th>房间号</th>
            <th>连入时间</th>
            <th>在线时长</th>
            <th class="col-action">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in visibleTerminals" :key="item.clientId" :class="{ offline: !item.online }">
            <td class="col-status">
              <span class="status-dot" :class="item.online ? 'online' : 'offline'"></span>
              <span class="status-text">{{ item.online ? '在线' : '已断开' }}</span>
            </td>
            <td>
              <div class="nick">{{ displayName(item) }}</div>
              <div class="mono dim">{{ shortId(item.clientId) }}</div>
            </td>
            <td class="mono">{{ item.ip || '—' }}</td>
            <td>
              <span class="kind-badge" :class="`kind-${item.kind}`">{{ kindLabel(item.kind) }}</span>
            </td>
            <td class="mono">{{ item.roomId || '—' }}</td>
            <td class="mono">{{ fmtDateTime(item.connectedAt) }}</td>
            <td class="mono">{{ fmtDuration((serverTime || item.connectedAt) - item.connectedAt) }}</td>
            <td class="col-action">
              <button
                class="danger-btn"
                :disabled="!item.online || item.kind === 'admin'"
                :title="item.kind === 'admin' ? '管理端自身连接不可断开' : '强制断开该终端'"
                @click="handleKick(item)"
              >
                强制断开
              </button>
            </td>
          </tr>
          <tr v-if="!visibleTerminals.length">
            <td colspan="8" class="empty-row">
              {{ terminals.length ? '没有匹配的终端' : '当前没有终端连入' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import type { AdminTerminal } from '@/types/admin';
import { fmtDateTime, fmtDuration, kindLabel } from '@/utils/admin';

const props = defineProps<{
  terminals: AdminTerminal[];
  serverTime?: number;
}>();

const emit = defineEmits<{ (e: 'kick', payload: { clientId: string; nickname: string }): void }>();

type FilterKey = 'all' | 'online' | 'player' | 'guest';
const filters: Array<{ key: FilterKey; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'online', label: '在线' },
  { key: 'player', label: '玩家' },
  { key: 'guest', label: '访客' },
];

const activeFilter = ref<FilterKey>('all');
const keyword = ref('');

const onlineCount = computed(() => props.terminals.filter((t) => t.online).length);

const countOf = (key: FilterKey) => {
  if (key === 'online') return onlineCount.value;
  if (key === 'player') return props.terminals.filter((t) => t.kind === 'player').length;
  if (key === 'guest') return props.terminals.filter((t) => t.kind === 'guest').length;
  return props.terminals.length;
};

const visibleTerminals = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  return props.terminals.filter((t) => {
    if (activeFilter.value === 'online' && !t.online) return false;
    if (activeFilter.value === 'player' && t.kind !== 'player') return false;
    if (activeFilter.value === 'guest' && t.kind !== 'guest') return false;
    if (!kw) return true;
    return [t.nickname || '', t.ip, t.roomId || '', t.clientId].join(' ').toLowerCase().includes(kw);
  });
});

const shortId = (id: string) => (id.length > 12 ? `${id.slice(0, 8)}…` : id);

const displayName = (item: AdminTerminal) => {
  if (item.nickname) return item.nickname;
  return item.kind === 'admin' ? '管理员控制台' : '未设定昵称';
};

const handleKick = (item: AdminTerminal) => {
  const name = item.nickname || item.ip || '该终端';
  if (!window.confirm(`确定强制断开「${name}」吗？对方会立即掉线并回到首页。`)) return;
  emit('kick', { clientId: item.clientId, nickname: item.nickname || '' });
};
</script>

<style scoped>
.admin-section {
  background: #fff;
  border: 1px solid var(--admin-border);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: var(--admin-shadow);
}

.section-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--admin-border);
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

.section-tools {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.chips {
  display: flex;
  gap: 6px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12px;
  color: var(--admin-muted);
  background: #f1f5f9;
  border: 1px solid transparent;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.chip:hover {
  background: #e2e8f0;
}

.chip.active {
  color: #fff;
  background: linear-gradient(45deg, #4f46e5, #7c3aed);
  box-shadow: 0 2px 8px rgba(79, 70, 229, 0.3);
}

.chip-count {
  font-variant-numeric: tabular-nums;
  opacity: 0.85;
}

.search-input {
  width: 200px;
  padding: 7px 12px;
  font-size: 13px;
  color: var(--admin-text);
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.search-input:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}

.table-wrap {
  overflow-x: auto;
}

.admin-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 880px;
}

.admin-table th {
  padding: 10px 16px;
  font-size: 12px;
  font-weight: 600;
  color: var(--admin-muted);
  text-align: left;
  white-space: nowrap;
  background: #f8fafc;
  border-bottom: 1px solid var(--admin-border);
}

.admin-table td {
  padding: 12px 16px;
  font-size: 13px;
  color: var(--admin-text);
  border-bottom: 1px solid #eef2f7;
  vertical-align: middle;
}

.admin-table tbody tr:hover {
  background: #f8fafc;
}

.admin-table tr.offline td {
  color: #94a3b8;
}

.col-status {
  width: 92px;
  white-space: nowrap;
}

.col-action {
  width: 120px;
  text-align: right;
}

.status-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-right: 6px;
  border-radius: 50%;
  vertical-align: middle;
}

.status-dot.online {
  background: #16a34a;
  box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.14);
}

.status-dot.offline {
  background: #cbd5e1;
}

.status-text {
  font-size: 12px;
  color: var(--admin-muted);
}

.nick {
  font-weight: 600;
  color: var(--admin-text);
}

.offline .nick {
  color: #94a3b8;
}

.mono {
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.dim {
  color: var(--admin-muted);
}

.kind-badge {
  display: inline-block;
  padding: 2px 8px;
  font-size: 12px;
  border-radius: 6px;
  white-space: nowrap;
}

.kind-player {
  color: #3730a3;
  background: #eef2ff;
}

.kind-admin {
  color: #92400e;
  background: #fef3c7;
}

.kind-guest {
  color: #475569;
  background: #f1f5f9;
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

.danger-btn:hover:not(:disabled) {
  color: #fff;
  background: #dc2626;
  border-color: #dc2626;
}

.danger-btn:disabled {
  color: #cbd5e1;
  background: #f8fafc;
  border-color: #e2e8f0;
  cursor: not-allowed;
}

.empty-row {
  padding: 36px 16px;
  color: var(--admin-muted);
  text-align: center;
}
</style>
