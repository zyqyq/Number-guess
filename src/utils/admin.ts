// 管理后台格式化工具：时间统一按东八区渲染

const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

const timeFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

/** epoch 秒 → MM-DD HH:mm:ss */
export function fmtDateTime(ts?: number | null): string {
  if (!ts) return '—';
  return dateTimeFormatter.format(new Date(ts * 1000));
}

/** epoch 秒 → HH:mm:ss */
export function fmtTime(ts?: number | null): string {
  if (!ts) return '—';
  return timeFormatter.format(new Date(ts * 1000));
}

/** 秒 → 1天2时3分 / 2时3分4秒 / 3分4秒 */
export function fmtDuration(seconds?: number | null): string {
  const total = Math.max(0, Math.floor(seconds || 0));
  const d = Math.floor(total / 86400);
  const h = Math.floor((total % 86400) / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (d > 0) return `${d} 天 ${h} 时`;
  if (h > 0) return `${h} 时 ${m} 分`;
  if (m > 0) return `${m} 分 ${s} 秒`;
  return `${s} 秒`;
}

export function phaseLabel(phase: string): string {
  if (phase === 'PLAYING') return '游戏中';
  if (phase === 'GAME_OVER') return '已结束';
  return '等待加入';
}

export function subPhaseLabel(subPhase?: string | null): string {
  switch (subPhase) {
    case 'DRAW_PHASE':
      return '抽牌阶段';
    case 'ACTION_PHASE':
      return '选牌判定';
    case 'JUDGE_RESULT':
      return '判定中';
    case 'PAUSED':
      return '已暂停';
    default:
      return '—';
  }
}

export function kindLabel(kind: string): string {
  if (kind === 'admin') return '管理端';
  if (kind === 'player') return '玩家';
  return '访客';
}

export function levelLabel(level: string): string {
  if (level === 'warn') return '警告';
  if (level === 'error') return '错误';
  return '信息';
}
