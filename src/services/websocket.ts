import type { GameState, ClientCommand, ChatMessage } from '@/types/game';
import { useGameStore } from '@/stores/game';

type WSStatus = 'connecting' | 'open' | 'closing' | 'closed';

class WebSocketService {
  private ws: WebSocket | null = null;
  private url: string = '';
  private reconnectTimer: number | null = null;
  private accessToken: string | null = null;
  private roomId: string | null = null;
  private status: WSStatus = 'closed';
  
  // 回调函数
  private onStateUpdate?: (state: GameState) => void;
  private onGuessResult?: (result: any) => void;
  private onDisconnect?: (data: any) => void;
  private onGameOver?: (data: any) => void;
  private onRoomClosed?: () => void;
  private onError?: (error: string) => void;
  // 被管理员强制断开（close code 4001）
  private onKicked?: (reason: string) => void;
  // 致命错误（房间号被保留、服务端拒绝）：提示后不再重连
  private onFatal?: (message: string) => void;
  // 连接（重连）成功：语音引擎用它重新登记成员身份
  private onReopened?: () => void;
  // 聊天室
  private onChat?: (message: ChatMessage) => void;
  private onChatRejected?: (payload: { reason: string; word?: string }) => void;
  // 语音通话：所有 Event_Voice* 统一走这里，由语音引擎自行分发
  private onVoiceEvent?: (event: string, payload: any) => void;
  // 旁观者：审批 / 视角 / 禁言 / 只读拦截等事件统一走这里
  private onSpectatorEvent?: (event: string, payload: any) => void;
  private fatal = false;

  constructor() {
    // 默认开发环境地址，生产环境可配置
    const host = import.meta.env.VITE_WS_HOST || window.location.host;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.url = `${protocol}//${host}/ws`;
  }

  connect(roomId: string, token?: string) {
    if (this.status === 'open' || this.status === 'connecting') return;

    this.roomId = roomId;
    if (token) this.accessToken = token;
    this.fatal = false;

    this.status = 'connecting';
    const fullUrl = `${this.url}/${roomId}${token ? `?token=${token}` : ''}`;
    
    console.log('[WS] Connecting to:', fullUrl);
    this.ws = new WebSocket(fullUrl);

    this.ws.onopen = () => {
      this.status = 'open';
      console.log('[WS] Connected');
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
      this.onReopened?.();
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handleMessage(data);
      } catch (e) {
        console.error('[WS] Parse error:', e);
      }
    };

    this.ws.onclose = (event) => {
      this.status = 'closed';
      console.log('[WS] Closed', event.code, event.reason);
      this.ws = null;

      // 4001 = 管理员强制断开：提示后回首页，不自动重连
      if (event.code === 4001) {
        this.onKicked?.(event.reason || 'admin_kick');
        return;
      }

      // 房间号被保留 / 服务端策略拒绝（1008）：提示后不再重连
      if (this.fatal) return;
      if (event.code === 1008) {
        this.failFatal(event.reason === 'room_reserved' ? '该房间号已保留' : '连接被服务器拒绝');
        return;
      }

      // 如果不是正常关闭，尝试重连
      if (event.code !== 1000 && this.roomId) {
        this.attemptReconnect();
      }
    };

    this.ws.onerror = (error) => {
      console.error('[WS] Error:', error);
      this.onError?.('网络连接错误');
      this.status = 'closed';
    };
  }

  connectWithUrl(url: string) {
    if (this.status === 'open' || this.status === 'connecting') return;

    this.fatal = false;
    this.status = 'connecting';
    
    console.log('[WS] Connecting to:', url);
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.status = 'open';
      console.log('[WS] Connected');
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
      this.onReopened?.();
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handleMessage(data);
      } catch (e) {
        console.error('[WS] Parse error:', e);
      }
    };

    this.ws.onclose = (event) => {
      this.status = 'closed';
      console.log('[WS] Closed', event.code, event.reason);
      this.ws = null;

      // 4001 = 管理员强制断开：提示后回首页，不自动重连
      if (event.code === 4001) {
        this.onKicked?.(event.reason || 'admin_kick');
        return;
      }

      // 房间号被保留 / 服务端策略拒绝（1008）：提示后不再重连
      if (this.fatal) return;
      if (event.code === 1008) {
        this.failFatal(event.reason === 'room_reserved' ? '该房间号已保留' : '连接被服务器拒绝');
        return;
      }

      // 如果不是正常关闭，尝试重连
      if (event.code !== 1000) {
        this.attemptReconnect();
      }
    };

    this.ws.onerror = (error) => {
      console.error('[WS] Error:', error);
      this.onError?.('网络连接错误');
      this.status = 'closed';
    };
  }

  private handleMessage(data: { event?: string; payload?: any; players?: any; gamePhase?: string; hostId?: string }) {
    const store = useGameStore();

    // 服务端拒绝（如保留房间号）：标记为致命错误，不再重连
    if ((data as any).error) {
      this.failFatal(String((data as any).error));
      return;
    }

    // 处理 Lobby 页面的简单状态更新（没有 event 字段）
    if (!data.event && data.players) {
      store.updateGameState(data as any);
      this.onStateUpdate?.(data as any);
      return;
    }
    
    switch (data.event) {
      case 'Event_StateUpdate':
      case 'Event_SyncFullState':
        store.updateGameState(data.payload);
        this.onStateUpdate?.(data.payload);
        break;
      case 'Event_GuessResult':
        this.onGuessResult?.(data.payload);
        break;
      case 'Event_PlayerDisconnected':
        this.onDisconnect?.(data.payload);
        break;
      case 'Event_GameOver':
        this.onGameOver?.(data.payload);
        break;
      case 'Event_RoomClosed':
        this.onRoomClosed?.();
        break;
      case 'Event_AdminNotice':
        // 管理员操作的提示（如房间被关闭），不需要额外 UI 即可忽略
        break;
      // ---------------- 聊天室 ----------------
      case 'Event_Chat':
        this.onChat?.(data.payload);
        break;
      case 'Event_ChatRejected':
        this.onChatRejected?.(data.payload);
        break;
      // ---------------- 语音通话 ----------------
      case 'Event_VoicePeers':
      case 'Event_VoicePeerJoined':
      case 'Event_VoicePeerLeft':
      case 'Event_VoiceSignal':
      case 'Event_VoiceMuteState':
      case 'Event_VoiceHostMuted':
      case 'Event_VoiceKicked':
      case 'Event_VoiceClosed':
        this.onVoiceEvent?.(data.event, data.payload);
        break;
      // ---------------- 旁观者 ----------------
      case 'Event_SpectateReady':
      case 'Event_SpectatorWaiting':
      case 'Event_SpectatorAsk':
      case 'Event_SpectatorRejected':
      case 'Event_SpectateView':
      case 'Event_SpectatorMuted':
      case 'Event_SpectatorLeft':
      case 'Event_ActionRejected':
        this.onSpectatorEvent?.(data.event, data.payload);
        break;
      default:
        console.warn('[WS] Unknown event:', data.event);
    }
  }

  private failFatal(message: string) {
    this.fatal = true;
    this.onFatal?.(message);
  }

  private attemptReconnect() {
    if (this.reconnectTimer) return;
    console.log('[WS] Attempting reconnect in 3s...');
    this.reconnectTimer = setTimeout(() => {
      if (this.roomId && this.accessToken) {
        this.connect(this.roomId, this.accessToken);
      }
    }, 3000);
  }

  send(command: ClientCommand) {
    if (this.status !== 'open' || !this.ws) {
      console.warn('[WS] Cannot send, connection not open');
      return false;
    }
    
    // 自动附加 token 如果需要
    const payload = {
      ...command,
      accessToken: this.accessToken || undefined
    };
    
    console.log('[WS] Sending:', payload);
    this.ws.send(JSON.stringify(payload));
    return true;
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.fatal = false;
    if (this.ws) {
      this.ws.close(1000, 'User disconnected');
      this.ws = null;
    }
    this.status = 'closed';
  }

  getStatus(): WSStatus { return this.status; }

  // 设置回调
  setStateUpdateCallback(cb: (state: GameState) => void) { this.onStateUpdate = cb; }
  setGuessResultCallback(cb: (result: any) => void) { this.onGuessResult = cb; }
  setDisconnectCallback(cb: (data: any) => void) { this.onDisconnect = cb; }
  setGameOverCallback(cb: (data: any) => void) { this.onGameOver = cb; }
  setRoomClosedCallback(cb: () => void) { this.onRoomClosed = cb; }
  setErrorCallback(cb: (error: string) => void) { this.onError = cb; }
  setKickedCallback(cb: (reason: string) => void) { this.onKicked = cb; }
  setFatalCallback(cb: (message: string) => void) { this.onFatal = cb; }
  setReopenedCallback(cb: () => void) { this.onReopened = cb; }
  setChatCallback(cb: (message: ChatMessage) => void) { this.onChat = cb; }
  setChatRejectedCallback(cb: (payload: { reason: string; word?: string }) => void) { this.onChatRejected = cb; }
  setVoiceEventCallback(cb: (event: string, payload: any) => void) { this.onVoiceEvent = cb; }
  setSpectatorEventCallback(cb: (event: string, payload: any) => void) { this.onSpectatorEvent = cb; }
}

export const wsService = new WebSocketService();
