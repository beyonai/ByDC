// ui/openclaw/src/views/chat-view.ts
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { chatController, ChatMessage } from '../controllers/chat.js';
import { gateway } from '../gateway.js';
import { marked } from 'marked';

@customElement('chat-view')
export class ChatView extends LitElement {
  static styles = css`
    :host {
      display: flex;
      flex-direction: column;
      height: 100vh;
      background: #1a1a2e;
      color: #eee;
    }

    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 1rem 1.5rem;
      border-bottom: 1px solid #333;
      background: #16213e;
    }

    .header h1 {
      margin: 0;
      font-size: 1.25rem;
      color: #e94560;
    }

    .connection-status {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.875rem;
    }

    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #666;
    }

    .status-dot.connected {
      background: #4ade80;
    }

    .messages {
      flex: 1;
      overflow-y: auto;
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }

    .message {
      max-width: 80%;
      padding: 1rem;
      border-radius: 12px;
      line-height: 1.6;
    }

    .message.user {
      align-self: flex-end;
      background: #e94560;
      color: white;
    }

    .message.assistant {
      align-self: flex-start;
      background: #16213e;
      border: 1px solid #333;
    }

    .message.streaming::after {
      content: '▋';
      animation: blink 1s infinite;
    }

    @keyframes blink {
      0%, 50% { opacity: 1; }
      51%, 100% { opacity: 0; }
    }

    .input-area {
      display: flex;
      gap: 0.75rem;
      padding: 1rem 1.5rem;
      border-top: 1px solid #333;
      background: #16213e;
    }

    textarea {
      flex: 1;
      padding: 0.75rem 1rem;
      border: 1px solid #333;
      border-radius: 8px;
      background: #1a1a2e;
      color: #eee;
      font-size: 1rem;
      resize: none;
      min-height: 24px;
      max-height: 200px;
    }

    textarea:focus {
      outline: none;
      border-color: #e94560;
    }

    button {
      padding: 0.75rem 1.5rem;
      border: none;
      border-radius: 8px;
      background: #e94560;
      color: white;
      font-size: 1rem;
      cursor: pointer;
      transition: opacity 0.2s;
    }

    button:hover:not(:disabled) {
      opacity: 0.9;
    }

    button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .error {
      padding: 0.75rem 1.5rem;
      background: #ef4444;
      color: white;
      text-align: center;
    }
  `;

  @state() private connectionStatus = false;
  @state() private inputValue = '';
  @state() private messages: ChatMessage[] = [];
  @state() private isLoading = false;
  @state() private error: string | null = null;

  connectedCallback() {
    super.connectedCallback();

    // Connect to gateway
    gateway.onConnect = () => {
      this.connectionStatus = true;
      chatController.loadSessions();
    };
    
    gateway.onDisconnect = () => {
      this.connectionStatus = false;
    };

    gateway.connect().catch((err) => {
      console.error('Failed to connect:', err);
    });
    
    // Poll for state updates
    this.startPolling();
  }
  
  private pollInterval?: number;
  
  private startPolling() {
    this.pollInterval = window.setInterval(() => {
      this.messages = chatController.messages.get();
      this.isLoading = chatController.isLoading.get();
      this.error = chatController.error.get();
    }, 100);
  }
  
  disconnectedCallback() {
    super.disconnectedCallback();
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
    }
  }

  private scrollToBottom() {
    setTimeout(() => {
      const messagesEl = this.shadowRoot?.querySelector('.messages');
      if (messagesEl) {
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
    }, 0);
  }

  private async handleSend() {
    const content = this.inputValue.trim();
    if (!content || this.isLoading) return;
    
    this.inputValue = '';
    await chatController.sendMessage(content);
    this.scrollToBottom();
  }

  private handleKeyDown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      this.handleSend();
    }
  }

  private renderMarkdown(content: string) {
    return marked.parse(content, { async: false }) as string;
  }

  render() {
    return html`
      <div class="header">
        <h1>DataCloud Agent</h1>
        <div class="connection-status">
          <span class="status-dot ${this.connectionStatus ? 'connected' : ''}"></span>
          <span>${this.connectionStatus ? 'Connected' : 'Disconnected'}</span>
        </div>
      </div>

      ${this.error ? html`<div class="error">${this.error}</div>` : ''}

      <div class="messages">
        ${this.messages.map((msg) => html`
          <div class="message ${msg.role} ${msg.isStreaming ? 'streaming' : ''}">
            ${msg.role === 'assistant' 
              ? html`<div innerHTML="${this.renderMarkdown(msg.content)}"></div>`
              : msg.content
            }
          </div>
        `)}
      </div>

      <div class="input-area">
        <textarea
          .value="${this.inputValue}"
          @input="${(e: InputEvent) => this.inputValue = (e.target as HTMLTextAreaElement).value}"
          @keydown="${this.handleKeyDown}"
          placeholder="Type your message..."
          rows="1"
        ></textarea>
        <button 
          @click="${this.handleSend}" 
          ?disabled="${this.isLoading || !this.inputValue.trim()}"
        >
          ${this.isLoading ? 'Sending...' : 'Send'}
        </button>
      </div>
    `;
  }
}
