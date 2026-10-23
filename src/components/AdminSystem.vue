<template>
  <section class="admin-section">
    <div class="section-head">
      <div>
        <h2>系统概况</h2>
        <p class="section-desc">进程启动于 {{ fmtDateTime(system?.startedAt) }}，以下数据每 2 秒刷新。</p>
      </div>
      <span class="env-pill">{{ system?.platform || '—' }} · Python {{ system?.pythonVersion || '—' }}</span>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <span class="stat-label">运行时长</span>
        <strong class="stat-value">{{ fmtDuration(system?.uptimeSeconds) }}</strong>
        <span class="stat-foot">进程已连续服务</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">在线终端</span>
        <strong class="stat-value">{{ system?.onlineTerminals ?? 0 }}</strong>
        <span class="stat-foot">累计登记 {{ system?.totalTerminals ?? 0 }} 台</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">房间总数</span>
        <strong class="stat-value">{{ system?.roomCount ?? 0 }}</strong>
        <span class="stat-foot">等待 {{ system?.waitingRooms ?? 0 }} · 游戏中 {{ system?.activeGames ?? 0 }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">峰值内存</span>
        <strong class="stat-value">{{ system?.rssMb ?? 0 }} <small>MB</small></strong>
        <span class="stat-foot">RSS · {{ system?.cpuCount ?? 0 }} 核</span>
      </div>
    </div>

    <div class="detail-grid">
      <div class="panel">
        <h3 class="panel-title">运行环境</h3>
        <dl class="kv">
          <div><dt>后端框架</dt><dd>FastAPI {{ system?.fastapiVersion || '—' }}</dd></div>
          <div><dt>Python</dt><dd>{{ system?.pythonVersion || '—' }}</dd></div>
          <div><dt>系统平台</dt><dd>{{ system?.platform || '—' }}</dd></div>
          <div><dt>进程 PID</dt><dd>{{ system?.pid ?? '—' }}</dd></div>
          <div><dt>服务器时间</dt><dd>{{ fmtDateTime(serverTime) }}</dd></div>
          <div><dt>负载 1/5/15 分钟</dt><dd>{{ loadText }}</dd></div>
        </dl>
      </div>

      <div class="panel">
        <h3 class="panel-title">资源占用</h3>
        <div class="meter-block">
          <div class="meter-head">
            <span>磁盘（项目所在卷）</span>
            <span class="meter-value">{{ system?.diskUsedPct ?? 0 }}%</span>
          </div>
          <div class="meter"><div class="meter-fill" :class="diskClass" :style="{ width: `${system?.diskUsedPct ?? 0}%` }"></div></div>
          <p class="meter-foot">剩余 {{ system?.diskFreeGb ?? 0 }} GB / 共 {{ system?.diskTotalGb ?? 0 }} GB</p>
        </div>

        <div class="meter-block">
          <div class="meter-head">
            <span>CPU 负载（1 分钟，按核心数归一）</span>
            <span class="meter-value">{{ cpuLoadPct }}%</span>
          </div>
          <div class="meter"><div class="meter-fill" :class="cpuClass" :style="{ width: `${cpuLoadPct}%` }"></div></div>
          <p class="meter-foot">负载值 {{ system?.load1 ?? '—' }} / {{ system?.cpuCount ?? 1 }} 核</p>
        </div>

        <div class="meter-block">
          <div class="meter-head">
            <span>内存峰值</span>
            <span class="meter-value">{{ system?.rssMb ?? 0 }} MB</span>
          </div>
          <div class="meter"><div class="meter-fill low" :style="{ width: `${memPct}%` }"></div></div>
          <p class="meter-foot">当前进程常驻内存，仅供参考</p>
        </div>
      </div>
    </div>

    <div class="panel">
      <h3 class="panel-title">首页房间列表</h3>
      <p class="panel-note">关闭后首页完全不展示房间列表（连占位都没有），玩家只能靠房间号或分享链接进入。保存在 config.json 的 roomList.enabled。</p>
      <div class="mode-switch">
        <button
          class="mode-btn"
          :class="{ active: roomListEnabled !== false }"
          @click="emit('set-room-list-enabled', true)"
        >开启</button>
        <button
          class="mode-btn"
          :class="{ active: roomListEnabled === false }"
          @click="emit('set-room-list-enabled', false)"
        >关闭</button>
      </div>
      <p class="panel-note">当前：{{ roomListEnabled === false ? '已关闭，首页不显示房间列表' : '已开启，首页右侧显示紧凑房间列表' }}</p>
    </div>

    <div class="panel events">
      <h3 class="panel-title">最近事件 <span class="panel-note">服务端环形缓冲，最多 120 条</span></h3>
      <ul v-if="events.length" class="event-list">
        <li v-for="(event, index) in events" :key="`${event.ts}-${index}`" class="event-item" :class="`level-${event.level}`">
          <span class="event-time mono">{{ fmtTime(event.ts) }}</span>
          <span class="event-level">{{ levelLabel(event.level) }}</span>
          <span class="event-text">{{ event.text }}</span>
        </li>
      </ul>
      <p v-else class="event-empty">暂无事件记录</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { AdminEvent, AdminRoom, AdminSystem } from '@/types/admin';
import { fmtDateTime, fmtDuration, fmtTime, levelLabel } from '@/utils/admin';

const props = defineProps<{
  system?: AdminSystem;
  events: AdminEvent[];
  rooms: AdminRoom[];
  serverTime?: number;
  // 首页房间列表是否开启（关闭后首页完全看不到该面板）
  roomListEnabled?: boolean;
}>();

const emit = defineEmits<{ (e: 'set-room-list-enabled', enabled: boolean): void }>();

const loadText = computed(() => {
  const s = props.system;
  if (!s || s.load1 === null) return '不可用（该平台不支持）';
  return `${s.load1} / ${s.load5} / ${s.load15}`;
});

const cpuLoadPct = computed(() => {
  const s = props.system;
  if (!s || s.load1 === null) return 0;
  return Math.min(100, Math.round((s.load1 / Math.max(1, s.cpuCount)) * 100));
});

const memPct = computed(() => {
  const s = props.system;
  if (!s) return 0;
  // 以 2GB 作为参考上限绘制进度条，仅作视觉参考
  return Math.min(100, Math.round((s.rssMb / 2048) * 100));
});

const diskClass = computed(() => {
  const pct = props.system?.diskUsedPct ?? 0;
  if (pct >= 90) return 'high';
  if (pct >= 75) return 'mid';
  return 'low';
});

const cpuClass = computed(() => {
  if (cpuLoadPct.value >= 80) return 'high';
  if (cpuLoadPct.value >= 50) return 'mid';
  return 'low';
});
</script>

<style scoped>
.admin-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.mode-switch {
  display: inline-flex;
  gap: 6px;
  margin-top: 10px;
  padding: 4px;
  background: #f1f3f8;
  border-radius: 10px;
}

.mode-btn {
  padding: 7px 16px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #5b6478;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.mode-btn:hover {
  color: #334155;
}

.mode-btn.active {
  background: #fff;
  color: #4a4fa2;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.12);
}

.section-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  background: #fff;
  border: 1px solid var(--admin-border);
  border-radius: 14px;
  box-shadow: var(--admin-shadow);
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

.env-pill {
  padding: 5px 12px;
  font-size: 12px;
  color: #3730a3;
  background: #eef2ff;
  border-radius: 999px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 16px 18px;
  background: #fff;
  border: 1px solid var(--admin-border);
  border-radius: 14px;
  box-shadow: var(--admin-shadow);
}

.stat-label {
  font-size: 12px;
  color: var(--admin-muted);
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--admin-text);
  font-variant-numeric: tabular-nums;
}

.stat-value small {
  font-size: 13px;
  font-weight: 500;
  color: var(--admin-muted);
}

.stat-foot {
  font-size: 11px;
  color: var(--admin-muted);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
}

.panel {
  padding: 16px 18px;
  background: #fff;
  border: 1px solid var(--admin-border);
  border-radius: 14px;
  box-shadow: var(--admin-shadow);
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 12px;
  font-size: 14px;
  color: var(--admin-text);
}

.panel-note {
  font-size: 11px;
  font-weight: 400;
  color: var(--admin-muted);
}

.kv {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
}

.kv div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #eef2f7;
}

.kv div:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.kv dt {
  font-size: 12px;
  color: var(--admin-muted);
}

.kv dd {
  margin: 0;
  font-size: 12px;
  color: var(--admin-text);
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  text-align: right;
}

.meter-block + .meter-block {
  margin-top: 16px;
}

.meter-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--admin-muted);
}

.meter-value {
  font-weight: 600;
  color: var(--admin-text);
  font-variant-numeric: tabular-nums;
}

.meter {
  height: 7px;
  overflow: hidden;
  background: #eef2f7;
  border-radius: 999px;
}

.meter-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.4s ease;
}

.meter-fill.low {
  background: linear-gradient(90deg, #34d399, #10b981);
}

.meter-fill.mid {
  background: linear-gradient(90deg, #fbbf24, #f59e0b);
}

.meter-fill.high {
  background: linear-gradient(90deg, #fb7185, #dc2626);
}

.meter-foot {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--admin-muted);
}

.events {
  padding-bottom: 8px;
}

.event-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 320px;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
}

.event-item {
  display: grid;
  grid-template-columns: 74px 52px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  padding: 7px 8px;
  font-size: 12px;
  border-radius: 7px;
}

.event-item:nth-child(odd) {
  background: #fafbfd;
}

.event-time {
  color: var(--admin-muted);
}

.mono {
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

.event-level {
  font-size: 11px;
  text-align: center;
  color: #0369a1;
  background: #e0f2fe;
  border-radius: 5px;
  padding: 1px 0;
}

.level-warn .event-level {
  color: #b45309;
  background: #fef3c7;
}

.level-error .event-level {
  color: #b91c1c;
  background: #fee2e2;
}

.event-text {
  color: var(--admin-text);
  word-break: break-all;
}

.event-empty {
  margin: 0;
  padding: 24px 0;
  font-size: 12px;
  color: var(--admin-muted);
  text-align: center;
}
</style>
