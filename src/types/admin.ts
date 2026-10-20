// 管理后台数据类型（与 backend/admin.py 的 build_snapshot 对应）

export type TerminalKind = 'guest' | 'player' | 'admin';

export interface AdminTerminal {
  clientId: string;
  ip: string;
  userAgent: string;
  kind: TerminalKind;
  nickname: string | null;
  roomId: string | null;
  connectedAt: number; // epoch 秒
  lastSeen: number;
  online: boolean;
  channels: string[];
}

export interface AdminRoomPlayer {
  playerId: string;
  playerName: string;
  isBot: boolean;
  isOnline: boolean;
  isAlive: boolean;
  isHost: boolean;
  clientId: string | null;
}

export interface AdminRoom {
  roomId: string;
  gamePhase: 'WAITING' | 'PLAYING' | 'GAME_OVER';
  subPhase: string | null;
  roundNumber: number;
  hostName: string | null;
  createdAt: number;
  gameStartedAt: number | null;
  gameEndedAt: number | null;
  durationSeconds: number;
  playerCount: number;
  aliveCount: number;
  currentTurnPlayerId: string | null;
  players: AdminRoomPlayer[];
}

export interface AdminSystem {
  startedAt: number;
  now: number;
  uptimeSeconds: number;
  pythonVersion: string;
  fastapiVersion: string;
  platform: string;
  pid: number;
  cpuCount: number;
  load1: number | null;
  load5: number | null;
  load15: number | null;
  rssMb: number;
  diskTotalGb: number;
  diskFreeGb: number;
  diskUsedPct: number;
  roomCount: number;
  activeGames: number;
  waitingRooms: number;
  onlineTerminals: number;
  totalTerminals: number;
}

export interface AdminEvent {
  ts: number;
  level: 'info' | 'warn' | 'error';
  text: string;
}

export interface AdminBlacklistItem {
  ip: string; // 单个 IP 或 CIDR 网段
  addedAt: number; // epoch 秒
  hits: number; // 命中拦截次数
}

export interface AdminBannedWord {
  word: string;
  addedAt: number;
  hits: number;
}

export interface AdminSecurity {
  localOnly: boolean;
  username: string;
  room: string;
  configPath: string;
  ipBlacklist: AdminBlacklistItem[];
  bannedWords: AdminBannedWord[];
}

export interface AdminSnapshot {
  serverTime: number;
  terminals: AdminTerminal[];
  rooms: AdminRoom[];
  system: AdminSystem;
  events: AdminEvent[];
  security: AdminSecurity;
}

export interface AdminAccessInfo {
  ok: boolean;
  adminUser: string;
  adminRoom: string;
  localOnly?: boolean;
  serverTime: number;
}
