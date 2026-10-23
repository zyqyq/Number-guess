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

    <!-- 访问口令（安全口令） -->
    <div class="panel">
      <h3 class="panel-title">
        访问口令 <span class="panel-note">管「进门」：开启后非本机设备必须持有效口令才能进站</span>
      </h3>

      <!-- 开关行：网页同款拨动开关 -->
      <div class="access-row">
        <div class="access-text">
          <p class="access-title">进站口令守卫</p>
          <p class="access-desc">
            {{ accessEnabled ? '已开启：外部设备必须持有效口令才能进站' : '已关闭：凡是能连到本服务的设备都可直接进站' }}
          </p>
        </div>
        <button
          type="button"
          class="switch"
          :class="{ on: accessEnabled }"
          role="switch"
          :aria-checked="accessEnabled"
          :aria-label="accessEnabled ? '关闭进站口令守卫' : '开启进站口令守卫'"
          @click="emit('setAccessEnabled', !accessEnabled)"
        >
          <span class="switch-knob"></span>
        </button>
      </div>

      <p v-if="accessEnabled && activeCount === 0" class="warn-tip">
        当前没有可用口令，外部设备会被挡在门外；请先生成一条，或先关闭守卫。
      </p>

      <p class="panel-note">
        开启后首页、游戏页、<code>/api/rooms</code> 与游戏 WebSocket 都要口令；管理后台、静态资源与本机
        <code>127.0.0.1</code> 豁免。首次用带口令的链接进站会种 7 天 Cookie，期间无需重复输入。
      </p>

      <div class="token-toolbar">
        <button class="primary-btn" type="button" @click="openModal">生成口令</button>
        <span class="panel-hint">
          共 {{ tokens.length }} 条 · 有效 {{ activeCount }} 条
        </span>
      </div>

      <table v-if="tokens.length" class="admin-table">
        <thead>
          <tr>
            <th>口令</th><th>备注</th><th>创建时间</th><th>过期时间</th>
            <th class="col-num">使用次数</th><th class="col-action"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in tokens" :key="item.id" :class="{ 'row-expired': item.expired }">
            <td class="mono">{{ item.masked }}</td>
            <td class="dim">{{ item.note || '—' }}</td>
            <td class="dim">{{ fmtDateTime(item.createdAt) }}</td>
            <td class="dim">
              {{ item.expiresAt ? fmtDateTime(item.expiresAt) : '永久' }}
              <span v-if="item.expired" class="expired-tag">已过期</span>
            </td>
            <td class="col-num">
              <span class="hit-badge" :class="{ zero: item.hits === 0 }">{{ item.hits }}</span>
            </td>
            <td class="col-action">
              <button class="danger-btn" @click="emit('removeAccessToken', item.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty-tip">
        还没有口令。开启守卫前请先生成至少一条，否则外部设备会被挡在门外（本机不受影响）。
      </p>
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

    <!-- 生成口令弹窗：填备注 / 过期时间 → 弹窗内回显完整口令 -->
    <Teleport to="body">
      <transition name="dlg">
        <div v-if="modalOpen" class="dlg-overlay" @click.self="onOverlayClick">
          <div class="dlg-card" role="dialog" aria-modal="true" aria-labelledby="token-dlg-title">
            <header class="dlg-head">
              <div>
                <h3 id="token-dlg-title" class="dlg-title">
                  {{ revealedToken ? '口令已生成' : '生成访问口令' }}
                </h3>
                <p class="dlg-sub">
                  {{
                    revealedToken
                      ? '完整口令只在此处显示一次，关闭弹窗后无法再次查看'
                      : '口令用于让外部设备通过进站校验，备注与有效期可留空'
                  }}
                </p>
              </div>
              <button class="dlg-x" type="button" aria-label="关闭弹窗" @click="closeModal">✕</button>
            </header>

            <!-- 步骤一：填写 -->
            <div v-if="!revealedToken" class="dlg-body">
              <label class="field">
                <span class="field-label">备注</span>
                <input
                  v-model="noteInput"
                  class="text-input"
                  type="text"
                  maxlength="40"
                  placeholder="给哪台设备用，如「客厅 iPad」（可留空）"
                  @keyup.enter="submitToken"
                />
              </label>

              <div class="field">
                <span class="field-label">过期时间</span>
                <div class="preset-row">
                  <button
                    v-for="p in presets"
                    :key="p.value"
                    type="button"
                    class="preset-chip"
                    :class="{ active: preset === p.value }"
                    @click="preset = p.value"
                  >
                    {{ p.label }}
                  </button>
                </div>
                <input
                  v-if="preset === 'custom'"
                  v-model="customDays"
                  class="text-input custom-days"
                  type="number"
                  min="1"
                  step="1"
                  placeholder="自定义天数，如 15"
                  @keyup.enter="submitToken"
                />
                <span class="field-hint" :class="{ 'hint-error': !!formError }">
                  {{ formError || expiryHint }}
                </span>
              </div>
            </div>

            <!-- 步骤二：回显 -->
            <div v-else class="dlg-body">
              <p class="reveal-warn">
                请立即复制或保存。关闭弹窗后，完整口令会从页面移除，口令列表里只剩脱敏值。
              </p>
              <span class="field-label">完整口令</span>
              <code class="tr-token">{{ revealedToken.token }}</code>
              <span class="field-label">带口令的进站链接</span>
              <code class="tr-link">{{ revealLink }}</code>
              <div class="tr-actions">
                <button class="primary-btn" type="button" @click="copy(revealedToken.token, 'token')">
                  {{ copied === 'token' ? '已复制口令' : '复制口令' }}
                </button>
                <button class="ghost-btn" type="button" @click="copy(revealLink, 'link')">
                  {{ copied === 'link' ? '已复制链接' : '复制完整链接' }}
                </button>
              </div>
              <p class="field-hint">
                {{
                  revealedToken.expiresAt
                    ? `有效期至 ${fmtDateTime(revealedToken.expiresAt)}，到期自动失效。`
                    : '永久有效，建议用完后在口令列表中删除。'
                }}
              </p>
            </div>

            <footer class="dlg-foot">
              <template v-if="!revealedToken">
                <button class="ghost-btn" type="button" @click="closeModal">取消</button>
                <button class="primary-btn" type="button" :disabled="submitting" @click="submitToken">
                  {{ submitting ? '生成中…' : '确认生成' }}
                </button>
              </template>
              <button v-else class="primary-btn dlg-wide" type="button" @click="closeModal">
                我已保存，关闭
              </button>
            </footer>
          </div>
        </div>
      </transition>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import type { AdminSecurity } from '@/types/admin';
import { fmtDateTime } from '@/utils/admin';

const props = defineProps<{
  security?: AdminSecurity;
  /** 刚生成的口令（完整值只在生成这一次回传，关掉即丢失） */
  revealedToken?: { token: string; note?: string; expiresAt?: number | null } | null;
}>();

const emit = defineEmits<{
  (e: 'addIp', ip: string): void;
  (e: 'removeIp', ip: string): void;
  (e: 'addWord', word: string): void;
  (e: 'removeWord', word: string): void;
  (e: 'reloadConfig'): void;
  (e: 'setAccessEnabled', enabled: boolean): void;
  (e: 'addAccessToken', payload: { note: string; days: number | null }): void;
  (e: 'removeAccessToken', id: string): void;
  (e: 'dismissToken'): void;
}>();

type Preset = 'forever' | '7' | '30' | '90' | 'custom';

const presets: { value: Preset; label: string }[] = [
  { value: 'forever', label: '永久' },
  { value: '7', label: '7 天' },
  { value: '30', label: '30 天' },
  { value: '90', label: '90 天' },
  { value: 'custom', label: '自定义' },
];

const ipInput = ref('');
const wordInput = ref('');

// ---- 生成口令弹窗 ----
const modalOpen = ref(false);
const noteInput = ref('');
const preset = ref<Preset>('forever');
const customDays = ref('');
const submitting = ref(false);
const formError = ref('');
const copied = ref<'' | 'token' | 'link'>('');
let copyTimer: ReturnType<typeof setTimeout> | null = null;
let submitGuard: ReturnType<typeof setTimeout> | null = null;

const accessEnabled = computed(() => !!props.security?.access?.enabled);
const tokens = computed(() => props.security?.access?.tokens || []);
const activeCount = computed(() => tokens.value.filter((t) => !t.expired).length);
const revealLink = computed(() =>
  props.revealedToken
    ? `${window.location.origin}/?key=${encodeURIComponent(props.revealedToken.token)}`
    : ''
);

const customDayCount = computed(() => {
  const raw = String(customDays.value ?? '').trim();
  const n = Number(raw);
  return raw && Number.isFinite(n) && n > 0 ? Math.floor(n) : null;
});

const expiryHint = computed(() => {
  if (preset.value === 'forever') return '永久有效，建议用完后在口令列表中删除。';
  if (preset.value === 'custom') {
    return customDayCount.value
      ? `签发后 ${customDayCount.value} 天内有效，到期自动失效。`
      : '请输入 1 以上的整数天数。';
  }
  return `签发后 ${preset.value} 天内有效，到期自动失效。`;
});

// 口令回来时清掉「生成中」并重置下一步的表单
watch(
  () => props.revealedToken,
  (token) => {
    if (token) {
      submitting.value = false;
      formError.value = '';
      if (submitGuard) {
        clearTimeout(submitGuard);
        submitGuard = null;
      }
    }
  }
);

const openModal = () => {
  // 上一次的口令如果还挂在父组件里，先清掉，避免重新打开时看到旧口令
  if (props.revealedToken) emit('dismissToken');
  noteInput.value = '';
  preset.value = 'forever';
  customDays.value = '';
  formError.value = '';
  submitting.value = false;
  copied.value = '';
  modalOpen.value = true;
};

const closeModal = () => {
  modalOpen.value = false;
  // 关闭即销毁完整口令：不留任何可再次查看的途径
  if (props.revealedToken) emit('dismissToken');
  submitting.value = false;
  formError.value = '';
  copied.value = '';
  if (submitGuard) {
    clearTimeout(submitGuard);
    submitGuard = null;
  }
};

// 回显阶段点遮罩不关闭，避免手抖丢掉唯一一次可见的口令
const onOverlayClick = () => {
  if (!props.revealedToken) closeModal();
};

const submitToken = () => {
  if (submitting.value || props.revealedToken) return;
  let days: number | null = null;
  if (preset.value === 'custom') {
    if (!customDayCount.value) {
      formError.value = '请输入 1 以上的整数天数。';
      return;
    }
    days = customDayCount.value;
  } else if (preset.value !== 'forever') {
    days = Number(preset.value);
  }
  formError.value = '';
  submitting.value = true;
  emit('addAccessToken', { note: noteInput.value.trim(), days });
  // 通道异常时不让按钮一直卡在「生成中」
  if (submitGuard) clearTimeout(submitGuard);
  submitGuard = setTimeout(() => {
    if (submitting.value) {
      submitting.value = false;
      formError.value = '生成请求超时，请检查后台连接后重试。';
    }
  }, 6000);
};

const onKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && modalOpen.value) {
    if (!props.revealedToken) closeModal();
  }
};

if (typeof window !== 'undefined') window.addEventListener('keydown', onKeydown);
onBeforeUnmount(() => {
  if (typeof window !== 'undefined') window.removeEventListener('keydown', onKeydown);
  if (copyTimer) clearTimeout(copyTimer);
  if (submitGuard) clearTimeout(submitGuard);
});

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

const copy = async (text: string, kind: 'token' | 'link') => {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // 非安全上下文下 Clipboard API 不可用，退回 textarea + execCommand
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
  copied.value = kind;
  if (copyTimer) clearTimeout(copyTimer);
  copyTimer = setTimeout(() => {
    copied.value = '';
  }, 2000);
};
</script>

<style scoped>
.admin-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* ---------- 访问口令：开关行 ---------- */
.access-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  margin-bottom: 10px;
  background: #f8fafc;
  border: 1px solid var(--admin-border);
  border-radius: 12px;
}

.access-title {
  margin: 0 0 3px;
  font-size: 13px;
  font-weight: 600;
  color: var(--admin-text);
}

.access-desc {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--admin-muted);
}

/* 拨动开关：与站内控件同一套圆角 / 主题色 */
.switch {
  position: relative;
  flex: 0 0 auto;
  width: 46px;
  height: 26px;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: #cbd5e1;
  cursor: pointer;
  transition: background 0.22s ease, box-shadow 0.22s ease;
}

.switch.on {
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.32);
}

.switch:focus-visible {
  outline: 2px solid #6366f1;
  outline-offset: 2px;
}

.switch-knob {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.28);
  transition: transform 0.22s cubic-bezier(0.4, 0, 0.2, 1);
}

.switch.on .switch-knob {
  transform: translateX(20px);
}

.warn-tip {
  margin: 0 0 8px;
  padding: 8px 12px;
  font-size: 11.5px;
  line-height: 1.6;
  color: #b45309;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
}

.token-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0;
}

.expired-tag {
  margin-left: 6px;
  padding: 0 6px;
  font-size: 10.5px;
  color: #b91c1c;
  background: #fee2e2;
  border-radius: 999px;
}

.row-expired td {
  opacity: 0.55;
}

/* ---------- 生成口令弹窗 ---------- */
.dlg-overlay {
  /* 弹窗被 Teleport 到 body，脱离了 .admin-page 的作用域，这里补一套管理端变量 */
  --admin-text: #1e293b;
  --admin-muted: #64748b;
  --admin-border: #e2e8f0;
  --admin-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 8px 20px rgba(15, 23, 42, 0.04);
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.48);
  backdrop-filter: blur(2px);
  box-sizing: border-box;
}

.dlg-card {
  width: min(480px, 100%);
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.28);
  overflow: hidden;
  text-align: left;
}

.dlg-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid #f1f5f9;
}

.dlg-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
  color: var(--admin-text);
}

.dlg-sub {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--admin-muted);
}

.dlg-x {
  flex: 0 0 auto;
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  font-size: 12px;
  color: var(--admin-muted);
  background: transparent;
  border: none;
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.dlg-x:hover {
  color: var(--admin-text);
  background: #f1f5f9;
}

.dlg-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px 20px;
  overflow-y: auto;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.field-label {
  font-size: 12px;
  font-weight: 500;
  color: #475569;
}

.field-hint {
  font-size: 11px;
  line-height: 1.6;
  color: var(--admin-muted);
}

.hint-error {
  color: #b91c1c;
}

.preset-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.preset-chip {
  padding: 6px 14px;
  font-size: 12px;
  color: #475569;
  background: #f8fafc;
  border: 1px solid var(--admin-border);
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.preset-chip:hover {
  border-color: #c7d2fe;
  color: #4338ca;
}

.preset-chip.active {
  color: #fff;
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  border-color: transparent;
  box-shadow: 0 3px 10px rgba(79, 70, 229, 0.28);
}

.custom-days {
  /* 弹窗内是纵向 flex，禁用 .text-input 的 flex:1（否则会被拉高） */
  flex: 0 0 auto;
  width: 220px;
  max-width: 100%;
}

.dlg-body .text-input {
  flex: 0 0 auto;
}

.reveal-warn {
  margin: 0;
  padding: 10px 12px;
  font-size: 11.5px;
  line-height: 1.7;
  color: #92400e;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 9px;
}

.tr-token,
.tr-link {
  display: block;
  padding: 10px 12px;
  border-radius: 9px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 12.5px;
  color: #0f172a;
  word-break: break-all;
  user-select: all;
}

.tr-link {
  color: #4f46e5;
}

.tr-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.dlg-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  background: #fafbfd;
  border-top: 1px solid #f1f5f9;
}

.dlg-wide {
  flex: 1;
}

.dlg-enter-active,
.dlg-leave-active {
  transition: opacity 0.18s ease;
}

.dlg-enter-active .dlg-card,
.dlg-leave-active .dlg-card {
  transition: transform 0.18s ease, opacity 0.18s ease;
}

.dlg-enter-from,
.dlg-leave-to {
  opacity: 0;
}

.dlg-enter-from .dlg-card,
.dlg-leave-to .dlg-card {
  opacity: 0;
  transform: translateY(10px) scale(0.98);
}

/* ---------- 通用 ---------- */
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
