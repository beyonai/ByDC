// ui/openclaw/src/controllers/chat.ts
import { gateway } from '../gateway.js';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  isStreaming?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
}

export type ChatState = {
  messages: ChatMessage[];
  sessions: ChatSession[];
  currentSessionId: string | null;
  isLoading: boolean;
  error: string | null;
};

// Simple state object (not using Signals)
export const chatState: ChatState = {
  messages: [],
  sessions: [],
  currentSessionId: null,
  isLoading: false,
  error: null,
};

// Callback to trigger re-render
let updateCallback: (() => void) | null = null;

export function setUpdateCallback(callback: () => void) {
  updateCallback = callback;
}

function notifyUpdate() {
  if (updateCallback) {
    updateCallback();
  }
}

// Set up event listener
gateway.onEvent = (evt) => {
  console.log('[ChatController] Received event:', evt.event, evt.payload);
  if (evt.event === 'chat.chunk') {
    handleChunk(evt.payload as { sessionId: string; content: string; isLast: boolean });
  } else if (evt.event === 'chat.complete') {
    chatState.isLoading = false;
    notifyUpdate();
  } else if (evt.event === 'chat.error') {
    chatState.error = (evt.payload as { message: string }).message;
    chatState.isLoading = false;
    notifyUpdate();
  }
};

function handleChunk(payload: { sessionId: string; content: string; isLast: boolean }) {
  const messages = chatState.messages;
  const lastMessage = messages[messages.length - 1];

  if (lastMessage && lastMessage.role === 'assistant') {
    // Create a new message object to trigger Lit re-render
    const updatedMessage = {
      ...lastMessage,
      content: lastMessage.content + payload.content,
      isStreaming: !payload.isLast,
    };
    // Create a new messages array
    chatState.messages = [...messages.slice(0, -1), updatedMessage];
    console.log('[ChatController] Updated message content, length:', updatedMessage.content.length);
    notifyUpdate();
  } else {
    console.log('[ChatController] No assistant message found to update');
  }
}

export async function loadSessions() {
  try {
    const sessions = await gateway.request<ChatSession[]>('sessions.list');
    chatState.sessions = sessions;
    notifyUpdate();
  } catch (e) {
    console.error('Failed to load sessions:', e);
  }
}

export async function createSession(title?: string) {
  try {
    const session = await gateway.request<ChatSession>('sessions.create', { title });
    chatState.sessions = [session, ...chatState.sessions];
    chatState.currentSessionId = session.id;
    chatState.messages = [];
    notifyUpdate();
    return session;
  } catch (e) {
    chatState.error = e instanceof Error ? e.message : 'Failed to create session';
    notifyUpdate();
    throw e;
  }
}

export async function loadMessages(sessionId: string) {
  try {
    chatState.currentSessionId = sessionId;
    const messages = await gateway.request<ChatMessage[]>('chat.history', { sessionId });
    chatState.messages = messages;
    notifyUpdate();
  } catch (e) {
    console.error('Failed to load messages:', e);
  }
}

export async function sendMessage(content: string) {
  let sessionId = chatState.currentSessionId;
  if (!sessionId) {
    const session = await createSession();
    sessionId = session.id;
  }

  const userMessage: ChatMessage = {
    id: crypto.randomUUID(),
    role: 'user',
    content,
    timestamp: Date.now(),
  };

  chatState.messages = [...chatState.messages, userMessage];
  chatState.isLoading = true;
  chatState.error = null;
  notifyUpdate();

  try {
    // Add placeholder for assistant response
    const assistantMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      isStreaming: true,
    };
    chatState.messages = [...chatState.messages, assistantMessage];
    notifyUpdate();

    await gateway.request('chat.send', {
      sessionId: chatState.currentSessionId,
      message: content,
    });
  } catch (e) {
    chatState.error = e instanceof Error ? e.message : 'Failed to send message';
    chatState.isLoading = false;
    // Remove the placeholder assistant message
    chatState.messages = chatState.messages.slice(0, -1);
    notifyUpdate();
  }
}

export async function abort() {
  try {
    await gateway.request('chat.abort', { sessionId: chatState.currentSessionId });
  } catch (e) {
    console.error('Failed to abort:', e);
  }
}
