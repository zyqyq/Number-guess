<template>
  <section class="admin-section">
    <div class="section-head">
      <div>
        <h2>安全设置</h2>
        <p class="section-desc">
          口令与访问开关由配置文件决定，IP 黑名单与违禁词库可在此在线维护，即时写入并热生效。
        </p>
      </div>
      <span class="env-pill" :class="security?.localOnly ? 'pill-safe' : 'pill-risk'">
        {{ security?.localOnly ? '仅本机登录：开' : '仅本机登录：关' }}
      </span>
    </div>

    <div class="detail-grid">
      <!-- 口令与访问控制（只读，改配置文件） -->
      <div class="panel">
        <h3 class="panel-title">
          管理口令与访问控制 <span class="panel-note">只读 · 修改配置文件后需重启或重载</span>
        </h3>
        <dl class="kv">
          <div><dt>昵称口令</dt><dd>{{ security?.username || '—' }}</dd></div>
          <div><dt>房间号口令</dt><dd>{{ security?.room || '—' }}</dd></div>
          <div>
            <dt>仅本机登录</dt>
            <dd :class="security?.localOnly ? 'dd-safe' : 'dd-risk'">
              {{ security?.localOnly ? '开（推荐）' : '关（任何来源都可访问）' }}
            </dd>
          </div>
          <div><dt>配置文件</dt><dd class="dd-path">{{ security?.configPath || '—' }}</dd></div>
        </dl>
        <div class="panel-actions">
          <button class="ghost-btn" @click="emit('reloadConfig')">重载配置</button>
          <span class="panel-hint">改完 config.json 后点此热生效；口令字段同样适用</span>
        </div>
      </div>

      <!-- IP 黑名单 -->
      <div class="panel">
        <h3 class="panel-title">
          IP 黑名单 <span class="panel-note">命中即拒绝一切连入（游戏 / 登记 / 管理）</span>
        </h3>
        <div class="add-row">
          <input
            v-model="ipInput"
            class="text-input mono"
            type="text"
            placeholder="IP 或网段，如 192.168.2.7 / 10.0.0.0/8"
            @keyup.enter="submitIp"
          />
          <button class="primary-btn" :disabled="!ipInput.trim()" @click="submitIp">加入黑名单</button>
        </div>
        <table v-if="security?.ipBlacklist.length" class="admin-table">
          <thead>
            <tr><th>IP / 网段</th><th>加入时间</th><th class="col-num">拦截次数</th><th class="col-action"></th></tr>
          </thead>
          <tbody>
            <tr v-for="item in security.ipBlacklist" :key="item.ip">
              <td class="mono">{{ item.ip }}</td>
              <td class="dim">{{ fmtDateTime(item.addedAt) }}</td>
              <td class="col-num">
                <span class="hit-badge" :class="{ zero: item.hits === 0 }">{{ item.hits }}</span>
              </td>
              <td class="col-action">
                <button class="danger-btn" @click="emit('removeIp', item.ip)">移除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-tip">黑名单为空，所有来源按默认规则放行。</p>
      </div>
    </div>

    <!-- 违禁词库 -->
    <div class="panel">
      <h3 class="panel-title">
        违禁词库 <span class="panel-note">昵称必检；文字聊天功能落地后同一套词库复用</span>
      </h3>
      <div class="add-row">
        <input
          v-model="wordInput"
          class="text-input"
          type="text"
          placeholder="输入违禁词后回车添加，最多 50 个字符"
          @keyup.enter="submitWord"
        />
        <button class="primary-btn" :disabled="!wordInput.trim()" @click="submitWord">加入词库</button>
      </div>
      <table v-if="security?.bannedWords.length" class="admin-table">
        <thead>
          <tr><th>违禁词</th><th>加入时间</th><th class="col-num">命中次数</th><th class="col-action"></th></tr>
        </thead>
        <tbody>
          <tr v-for="item in security.bannedWords" :key="item.word">
            <td class="word-cell">{{ item.word }}</td>
            <td class="dim">{{ fmtDateTime(item.addedAt) }}</td>
            <td class="col-num">
              <span class="hit-badge" :class="{ zero: item.hits === 0 }">{{ item.hits }}</span>
            </td>
            <td class="col-action">
              <button class="danger-btn" @click="emit('removeWord', item.word)">移除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty-tip">词库为空，昵称暂不做内容限制。</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import type { AdminSecurity } from '@/types/admin';
import { fmtDateTime } from '@/utils/admin';

const props = defineProps<{ security?: AdminSecurity }>();

const emit = defineEmits<{
  (e: 'addIp', ip: string): void;
  (e: 'removeIp', ip: string): void;
  (e: 'addWord', word: string): void;
  (e: 'removeWord', word: string): void;
  (e: 'reloadConfig'): void;
}>();

const ipInput = ref('');
const wordInput = ref('');

const submitIp = () => {
  const value = ipInput.value.trim();
  if (!value) return;
  emit('addIp', value);
  ipInput.value = '';
};

const submitWord = () => {
  const value = wordInput.value.trim();
  if (!value) return;
  emit('addWord', value);
  wordInput.value = '';
};
</script>

<style scoped>
.admin-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
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
  border-radius: 999px;
}

.pill-safe {
  color: #15803d;
  background: #dcfce7;
}

.pill-risk {
  color: #b91c1c;
  background: #fee2e2;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
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
  flex-wrap: wrap;
}

.panel-note {
  font-size: 11px;
  font-weight: 400;
  color: var(--admin-muted);
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.panel-hint {
  font-size: 11px;
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
  white-space: nowrap;
}

.kv dd {
  margin: 0;
  font-size: 12px;
  color: var(--admin-text);
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  text-align: right;
}

.dd-safe {
  color: #15803d;
  font-weight: 600;
}

.dd-risk {
  color: #b91c1c;
  font-weight: 600;
}

.dd-path {
  font-size: 11px !important;
  word-break: break-all;
}

.add-row {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.text-input {
  flex: 1;
  min-width: 0;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--admin-text);
  background: #f8fafc;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  outline: none;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.text-input:focus {
  background: #fff;
  border-color: #6366f1;
}

.primary-btn {
  padding: 8px 16px;
  font-size: 12px;
  color: #fff;
  background: #4f46e5;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s ease;
}

.primary-btn:hover:not(:disabled) {
  background: #4338ca;
}

.primary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ghost-btn {
  padding: 7px 14px;
  font-size: 12px;
  color: #334155;
  background: #fff;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.ghost-btn:hover {
  border-color: #94a3b8;
  background: #f8fafc;
}

.admin-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.admin-table th {
  padding: 8px 10px;
  text-align: left;
  font-weight: 500;
  color: var(--admin-muted);
  background: #f8fafc;
  border-bottom: 1px solid var(--admin-border);
}

.admin-table td {
  padding: 9px 10px;
  color: var(--admin-text);
  border-bottom: 1px solid #f1f5f9;
}

.admin-table tbody tr:last-child td {
  border-bottom: none;
}

.admin-table tbody tr:hover {
  background: #fafbfd;
}

.col-num {
  text-align: center;
  width: 90px;
}

.col-action {
  text-align: right;
  width: 80px;
}

.dim {
  color: var(--admin-muted);
}

.mono {
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

.word-cell {
  font-weight: 600;
  color: #b91c1c;
  word-break: break-all;
}

.hit-badge {
  display: inline-block;
  min-width: 26px;
  padding: 1px 7px;
  font-size: 11px;
  font-weight: 600;
  color: #b45309;
  background: #fef3c7;
  border-radius: 999px;
}

.hit-badge.zero {
  color: #94a3b8;
  background: #f1f5f9;
}

.danger-btn {
  padding: 5px 12px;
  font-size: 11px;
  color: #b91c1c;
  background: #fff;
  border: 1px solid #fecaca;
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.danger-btn:hover {
  background: #fef2f2;
  border-color: #f87171;
}

.empty-tip {
  margin: 4px 0 0;
  padding: 18px 0;
  font-size: 12px;
  color: var(--admin-muted);
  text-align: center;
  background: #fafbfd;
  border-radius: 10px;
}
</style>
