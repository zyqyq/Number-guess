import type { GameState, ClientCommand } from '@/types/game';
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
  private onError?: (error: string) => void;

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
      default:
        console.warn('[WS] Unknown event:', data.event);
    }
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
    if (this.ws) {
      this.ws.close(1000, 'User disconnected');
      this.ws = null;
    }
    this.status = 'closed';
  }

  // 设置回调
  setStateUpdateCallback(cb: (state: GameState) => void) { this.onStateUpdate = cb; }
  setGuessResultCallback(cb: (result: any) => void) { this.onGuessResult = cb; }
  setDisconnectCallback(cb: (data: any) => void) { this.onDisconnect = cb; }
  setGameOverCallback(cb: (data: any) => void) { this.onGameOver = cb; }
  setErrorCallback(cb: (error: string) => void) { this.onError = cb; }

  getStatus() { return this.status; }
}

export const wsService = new WebSocketService();
