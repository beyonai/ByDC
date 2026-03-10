// ui/openclaw/src/app.ts
import { LitElement, html, css } from 'lit';
import { customElement } from 'lit/decorators.js';
import './views/chat-view.js';

@customElement('datacloud-app')
export class DataCloudApp extends LitElement {
  static styles = css`
    :host {
      display: block;
      height: 100vh;
      width: 100vw;
    }
  `;

  render() {
    return html`<chat-view></chat-view>`;
  }
}
