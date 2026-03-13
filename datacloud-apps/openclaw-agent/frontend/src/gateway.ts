// ui/openclaw/src/gateway.ts
export interface GatewayFrame {
  type: "req" | "res" | "event";
  id?: string;
  method?: string;
  params?: unknown;
  ok?: boolean;
  payload?: unknown;
  event?: string;
  error?: string;
}

export interface GatewayEventFrame {
  event: string;
  payload: unknown;
}

export type GatewayEventHandler = (evt: GatewayEventFrame) => void;

export class GatewayBrowserClient {
  private ws: WebSocket | null = null;
  private pending = new Map<string, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  
  onEvent?: GatewayEventHandler;
  onConnect?: () => void;
  onDisconnect?: () => void;

  constructor(private url: string = "ws://localhost:8000/ws") {}

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.url);
        
        this.ws.onopen = () => {
          console.log("[Gateway] Connected");
          this.reconnectAttempts = 0;
          this.onConnect?.();
          resolve();
        };

        this.ws.onmessage = (msg) => {
          try {
            const frame = JSON.parse(msg.data) as GatewayFrame;
            this.handleFrame(frame);
          } catch (e) {
            console.error("[Gateway] Failed to parse message:", e);
          }
        };

        this.ws.onclose = () => {
          console.log("[Gateway] Disconnected");
          this.onDisconnect?.();
          this.attemptReconnect();
        };

        this.ws.onerror = (err) => {
          console.error("[Gateway] WebSocket error:", err);
          reject(err);
        };
      } catch (e) {
        reject(e);
      }
    });
  }

  private attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error("[Gateway] Max reconnection attempts reached");
      return;
    }
    
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    
    console.log(`[Gateway] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    
    setTimeout(() => {
      this.connect().catch(() => {});
    }, delay);
  }

  private handleFrame(frame: GatewayFrame) {
    if (frame.type === "res" && frame.id) {
      const pending = this.pending.get(frame.id);
      if (pending) {
        if (frame.ok) {
          pending.resolve(frame.payload);
        } else {
          pending.reject(new Error(frame.error || "Request failed"));
        }
        this.pending.delete(frame.id);
      }
    } else if (frame.type === "event" && frame.event) {
      this.onEvent?.({ event: frame.event, payload: frame.payload });
    }
  }

  request<T = unknown>(method: string, params?: unknown): Promise<T> {
    return new Promise((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        reject(new Error("WebSocket not connected"));
        return;
      }

      const id = crypto.randomUUID();
      const frame: GatewayFrame = { type: "req", id, method, params };
      
      this.pending.set(id, { resolve: resolve as (v: unknown) => void, reject });
      this.ws.send(JSON.stringify(frame));

      // Timeout after 30 seconds
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error("Request timeout"));
        }
      }, 30000);
    });
  }

  disconnect() {
    this.ws?.close();
    this.ws = null;
  }
}

// Singleton instance
export const gateway = new GatewayBrowserClient();
