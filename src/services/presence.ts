// 终端标识与在线登记（presence）
//
// clientId 持久化在 localStorage，同一浏览器多次访问复用同一条终端记录；
// presence 连接只用于让管理后台看到「谁打开了页面」，不参与游戏。

const CLIENT_ID_KEY = 'guess_number_client_id';

export function getClientId(): string {
  try {
    let id = localStorage.getItem(CLIENT_ID_KEY);
    if (!id) {
      const rand =
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
          ? crypto.randomUUID()
          : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
      id = rand;
      localStorage.setItem(CLIENT_ID_KEY, id);
    }
    return id;
  } catch {
    return `anon-${Math.random().toString(36).slice(2, 10)}`;
  }
}

/**
 * 建立 presence 连接，返回清理函数。
 * 断线后每 5 秒重连一次，页面卸载时调用返回的函数即可停止。
 */
export function connectPresence(): () => void {
  let socket: WebSocket | null = null;
  let pingTimer: number | undefined;
  let retryTimer: number | undefined;
  let disposed = false;

  const cleanupSocket = () => {
    if (pingTimer !== undefined) {
      window.clearInterval(pingTimer);
      pingTimer = undefined;
    }
  };

  const open = () => {
    if (disposed) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/presence/${getClientId()}`;
    try {
      socket = new WebSocket(url);
    } catch {
      return;
    }

    socket.onopen = () => {
      cleanupSocket();
      pingTimer = window.setInterval(() => {
        if (socket && socket.readyState === WebSocket.OPEN) socket.send('ping');
      }, 20000);
    };

    socket.onclose = (event) => {
      cleanupSocket();
      socket = null;
      // 被 IP 黑名单拒绝（1008 / ip_banned）：停止重连，避免无谓请求
      if (event.reason === 'ip_banned') return;
      if (!disposed) {
        retryTimer = window.setTimeout(open, 5000);
      }
    };
  };

  open();

  return () => {
    disposed = true;
    cleanupSocket();
    if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    if (socket) {
      socket.onclose = null;
      socket.close(1000, 'leave_page');
      socket = null;
    }
  };
}
