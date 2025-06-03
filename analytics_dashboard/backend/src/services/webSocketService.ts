import WebSocket, { WebSocketServer } from 'ws';

let wssInstance: WebSocketServer | null = null;

export const initWebSocketServer = (server: any): WebSocketServer => {
  const wss = new WebSocketServer({ server });
  console.log('WebSocket server initialized');

  wss.on('connection', (ws) => {
    console.log('Client connected to WebSocket');
    ws.on('message', (message) => {
      console.log('Received WebSocket message:', message.toString());
    });
    ws.on('close', () => {
      console.log('Client disconnected from WebSocket');
    });
    ws.send(JSON.stringify({ type: 'CONNECTION_ACK', message: 'Successfully connected to WebSocket server!' }));
  });
  wssInstance = wss;
  return wss;
};

export const broadcast = (data: any) => {
  if (!wssInstance) {
    console.error('WebSocket server not initialized. Cannot broadcast.');
    return;
  }
  const jsonData = JSON.stringify(data);
  wssInstance.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(jsonData);
    }
  });
  console.log('Broadcasted message:', jsonData);
};