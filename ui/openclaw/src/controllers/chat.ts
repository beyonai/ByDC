// ui/openclaw/src/controllers/chat.ts
import { Signal, signal } from '@lit-labs/signals';
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

export class ChatController {
  messages = signal<ChatMessage[]>([]);
  sessions = signal<ChatSession[]>([]);
  currentSessionId = signal<string | null>(null);
  isLoading = signal(false);
  error = signal<string | null>(null);

  constructor() {
    // Listen for streaming events
    gateway.onEvent = (evt) => {
      if (evt.event === 'chat.chunk') {
        this.handleChunk(evt.payload as { sessionId: string; content: string; isLast: boolean });
      } else if (evt.event === 'chat.complete') {
        this.isLoading.set(false);
      } else if (evt.event === 'chat.error') {
        this.error.set((evt.payload as { message: string }).message);
        this.isLoading.set(false);
      }
    };
  }

  async loadSessions() {
    try {
      const sessions = await gateway.request<ChatSession[]>('sessions.list');
      this.sessions.set(sessions);
    } catch (e) {
      console.error('Failed to load sessions:', e);
    }
  }

  async createSession(title?: string) {
    try {
      const session = await gateway.request<ChatSession>('sessions.create', { title });
      this.sessions.set([session, ...this.sessions.get()]);
      this.currentSessionId.set(session.id);
      this.messages.set([]);
      return session;
    } catch (e) {
      this.error.set(e instanceof Error ? e.message : 'Failed to create session');
      throw e;
    }
  }

  async loadMessages(sessionId: string) {
    try {
      this.currentSessionId.set(sessionId);
      const messages = await gateway.request<ChatMessage[]>('chat.history', { sessionId });
      this.messages.set(messages);
    } catch (e) {
      console.error('Failed to load messages:', e);
    }
  }

  async sendMessage(content: string) {
    const sessionId = this.currentSessionId.get();
    if (!sessionId) {
      await this.createSession();
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      timestamp: Date.now(),
    };

    this.messages.set([...this.messages.get(), userMessage]);
    this.isLoading.set(true);
    this.error.set(null);

    try {
      // Add placeholder for assistant response
      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        isStreaming: true,
      };
      this.messages.set([...this.messages.get(), assistantMessage]);

      await gateway.request('chat.send', {
        sessionId: this.currentSessionId.get(),
        message: content,
      });
    } catch (e) {
      this.error.set(e instanceof Error ? e.message : 'Failed to send message');
      this.isLoading.set(false);
      // Remove the placeholder assistant message
      this.messages.set(this.messages.get().slice(0, -1));
    }
  }

  private handleChunk(payload: { sessionId: string; content: string; isLast: boolean }) {
    const messages = this.messages.get();
    const lastMessage = messages[messages.length - 1];
    
    if (lastMessage && lastMessage.role === 'assistant') {
      lastMessage.content += payload.content;
      lastMessage.isStreaming = !payload.isLast;
      this.messages.set([...messages]);
    }
  }

  async abort() {
    try {
      await gateway.request('chat.abort', { sessionId: this.currentSessionId.get() });
    } catch (e) {
      console.error('Failed to abort:', e);
    }
  }
}

export const chatController = new ChatController();
