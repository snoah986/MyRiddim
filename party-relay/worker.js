/**
 * myriddim Party Mode edge relay for Cloudflare Workers.
 *
 * Deploy with Wrangler. Each room is a Durable Object: the Worker itself is
 * stateless, while the object keeps only live WebSocket connections and a
 * bounded room snapshot. Messages are opaque JSON envelopes so the desktop
 * host and mobile guest can share the same protocol over LAN or cloud.
 */
const MAX_MESSAGE_BYTES = 32 * 1024;
const MAX_CONNECTIONS = 64;
const ROOM_CODE = /^[A-Z0-9_-]{4,16}$/;
const ALLOWED_TYPES = new Set([
  'ROOM_JOIN', 'ROOM_LEAVE', 'STATE_SYNC', 'QUEUE_MUTATION', 'SONG_REQUEST',
  'PERMISSION_UPDATE', 'PING', 'PONG'
]);

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const match = url.pathname.match(/^\/room\/([A-Za-z0-9_-]+)$/);
    if (!match) return new Response('myriddim party relay', { status: 200 });
    const code = match[1].toUpperCase();
    if (!ROOM_CODE.test(code)) return new Response('Invalid room code', { status: 400 });
    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response(JSON.stringify({ ok: true, room: code }), {
        headers: { 'content-type': 'application/json' }
      });
    }
    const id = env.PARTY_ROOMS.idFromName(code);
    return env.PARTY_ROOMS.get(id).fetch(request);
  }
};

export class PartyRoom {
  constructor(state) {
    this.state = state;
    this.sockets = new Set();
    this.snapshot = { code: '', host: false, updated_at: 0 };
  }

  async fetch(request) {
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    server.accept();
    if (this.sockets.size >= MAX_CONNECTIONS) {
      server.close(1013, 'Room is full');
      return new Response(null, { status: 101, webSocket: client });
    }

    const url = new URL(request.url);
    const code = url.pathname.split('/').pop().toUpperCase();
    const role = url.searchParams.get('role') === 'host' ? 'host' : 'guest';
    const connection = { socket: server, role, id: crypto.randomUUID() };
    this.sockets.add(connection);
    server.serializeAttachment({ role, id: connection.id, code });

    server.addEventListener('message', event => this.onMessage(connection, event.data));
    server.addEventListener('close', () => this.sockets.delete(connection));
    server.addEventListener('error', () => this.sockets.delete(connection));
    server.send(JSON.stringify({ type: 'ROOM_JOIN', room: code, role, id: connection.id, state: this.snapshot }));
    return new Response(null, { status: 101, webSocket: client });
  }

  onMessage(connection, raw) {
    if (typeof raw !== 'string' || raw.length > MAX_MESSAGE_BYTES) return this.close(connection, 1009, 'Message too large');
    let message;
    try { message = JSON.parse(raw); } catch { return this.close(connection, 1003, 'Invalid JSON'); }
    if (!message || !ALLOWED_TYPES.has(message.type)) return;
    // Only the host may publish authoritative state or permission changes.
    if (connection.role !== 'host' && (message.type === 'STATE_SYNC' || message.type === 'PERMISSION_UPDATE')) return;
    if (message.type === 'STATE_SYNC') {
      this.snapshot = { ...message.state, updated_at: Date.now() };
    }
    const envelope = JSON.stringify({
      ...message,
      room: this.snapshot.code || message.room,
      sender: connection.id,
      sent_at: Date.now()
    });
    for (const peer of this.sockets) {
      if (peer !== connection && peer.socket.readyState === 1) {
        try { peer.socket.send(envelope); } catch { this.sockets.delete(peer); }
      }
    }
  }

  close(connection, code, reason) {
    try { connection.socket.close(code, reason); } catch { /* already closed */ }
    this.sockets.delete(connection);
  }
}
