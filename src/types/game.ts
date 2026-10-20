// 游戏核心数据类型定义

export type Color = '红' | '蓝' | '绿' | '橙' | '粉';

export interface Card {
  id: string;
  color: Color;
  number: number;
  isSelected?: boolean;
}

export interface PositionResult {
  position: number;       // 0=最左, 1-4=之间, 5=最右
  leftColor: Color | null;
  rightColor: Color | null;
}

export interface Clue {
  id: string;
  type: 'position' | 'point';
  publicCardId: string;
  publicCardNumber?: number;
  targetColor?: Color;
  result: PositionResult | boolean; // position: {position,leftColor,rightColor}, point: true/false
  timestamp: number;
}

export interface Player {
  playerId: string;
  playerName: string;
  isAlive: boolean;
  isOnline: boolean;
  isBot?: boolean;
  hand: Card[]; // 包含真实数字
  clues: Clue[];
}

export interface DeckRemainingCount {
  红: number;
  蓝: number;
  绿: number;
  橙: number;
  粉: number;
}

export type GamePhase = 'WAITING' | 'PLAYING' | 'GAME_OVER';
export type SubPhase = 'DRAW_PHASE' | 'ACTION_PHASE' | 'JUDGE_RESULT' | 'PAUSED';

export interface PendingJudgement {
  selectedPublicCardId: string;
  judgeType: 'position' | 'point';
  targetColor?: Color;
  result?: PositionResult | boolean;
}

export interface GameOverInfo {
  winnerId: string | null; // null = 平局
  winnerName: string | null;
  correctGuess?: number[];
  reason: 'correct_guess' | 'deck_exhausted';
}

export interface GameState {
  roomId: string;
  hostId?: string;
  gamePhase: GamePhase;
  subPhase: SubPhase | null;
  roundNumber: number;
  currentTurnPlayerId: string | null;
  turnOrder?: string[];
  deckRemainingCount: DeckRemainingCount;
  publicCards: Card[];
  players: Record<string, Player>;
  pendingJudgement: PendingJudgement | null;
  gameOverInfo: GameOverInfo | null;
  seed?: string;
  usedCardNumbers?: Array<{ color: Color; number: number }>;
  /** 聊天室：最近 50 条消息（含系统消息） */
  chat?: ChatMessage[];
  /** 语音通话成员表 */
  voice?: VoiceState;
}

/** 一条聊天消息；system 为 true 时是加入/离开/语音动态等系统提示 */
export interface ChatMessage {
  id: string;
  from: string;
  fromName: string;
  text: string;
  ts: number;
  system?: boolean;
}

/** 语音通话状态（随游戏快照下发） */
export interface VoiceState {
  participants: string[];
  hostMuted: string[];
}

/** WebRTC 信令数据：SDP 描述或 ICE 候选 */
export interface VoiceSignalData {
  description?: RTCSessionDescriptionInit;
  candidate?: RTCIceCandidateInit;
}

/** 语音成员在 UI 上的展示态 */
export interface VoiceMember {
  playerId: string;
  playerName: string;
  isBot: boolean;
  hostMuted: boolean;
  selfMuted: boolean;
  speaking: boolean;
  connected: boolean;
}

export interface FullStateSnapshot extends GameState {
  // 与 GameState 相同，用于类型明确
}

// WebSocket 客户端指令
export type ClientCommand = 
  | { cmd: 'JoinRoom'; roomId: string; playerName: string }
  | { cmd: 'Reconnect'; roomId: string; playerId: string; accessToken?: string }
  | { cmd: 'StartGame' }
  | { cmd: 'SelectColorToDraw'; color: Color }
  | { cmd: 'SelectPublicCard'; publicCardId: string }
  | { cmd: 'DeselectPublicCard' }
  | { cmd: 'JudgeByPosition'; publicCardId: string }
  | { cmd: 'JudgeByPoint'; publicCardId: string; targetColor: Color }
  | { cmd: 'SkipTurn' }
  | { cmd: 'SubmitGuess'; guesses: number[] }
  | { cmd: 'ResetGame' }
  | { cmd: 'DissolveRoom' }
  | { cmd: 'KickPlayer'; playerId: string }
  | { cmd: 'AddBot' }
  | { cmd: 'RemoveBot'; playerId: string }
  // 聊天室
  | { cmd: 'SendChat'; text: string }
  // 语音通话
  | { cmd: 'VoiceJoin' }
  | { cmd: 'VoiceLeave' }
  | { cmd: 'VoiceSignal'; to: string; data: VoiceSignalData }
  | { cmd: 'VoiceSetMute'; muted: boolean }
  | { cmd: 'VoiceMuteAll'; muted: boolean }
  | { cmd: 'VoiceKick'; playerId: string }
  | { cmd: 'VoiceClose' };

// WebSocket 服务端事件
export type ServerEvent =
  | { event: 'Event_StateUpdate'; payload: GameState }
  | { event: 'Event_SyncFullState'; payload: FullStateSnapshot }
  | { event: 'Event_GuessResult'; payload: { correct: boolean; correctNumbers?: number[] } }
  | { event: 'Event_PlayerDisconnected'; payload: { playerId: string; isCurrentTurnPlayer: boolean; paused: boolean } }
  | { event: 'Event_GameOver'; payload: GameOverInfo }
  // 聊天室
  | { event: 'Event_Chat'; payload: ChatMessage }
  | { event: 'Event_ChatRejected'; payload: { reason: string; word?: string } }
  // 语音通话
  | { event: 'Event_VoicePeers'; payload: { peers: string[] } }
  | { event: 'Event_VoicePeerJoined'; payload: { playerId: string; playerName: string } }
  | { event: 'Event_VoicePeerLeft'; payload: { playerId: string; playerName: string } }
  | { event: 'Event_VoiceSignal'; payload: { from: string; data: VoiceSignalData } }
  | { event: 'Event_VoiceMuteState'; payload: { playerId: string; muted: boolean } }
  | { event: 'Event_VoiceHostMuted'; payload: { muted: boolean } }
  | { event: 'Event_VoiceKicked'; payload: { by: string } }
  | { event: 'Event_VoiceClosed'; payload: { by: string } };
