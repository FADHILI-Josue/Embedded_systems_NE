import express from 'express';
import * as http from 'http'
import cors from 'cors';
import * as dotenv from 'dotenv';
dotenv.config();

import eventRoutes from './routes/eventRoutes';
import analyticsRoutes from './routes/analyticsRoutes';
import { initWebSocketServer } from './services/webSocketService';
import prisma from './prismaClient';


const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors()); // Allow requests from frontend
app.use(express.json()); // Parse JSON bodies

app.use('/api/events', eventRoutes);
app.use('/api/analytics', analyticsRoutes);

app.get('/', (req, res) => {
  res.send('Parking Analytics Backend is running!');
});

const server = http.createServer(app);

initWebSocketServer(server);

server.listen(PORT, async () => {
  try {
    await prisma.$connect();
    console.log('Successfully connected to the database.');
  } catch (error) {
    console.error('Failed to connect to the database:', error);
    process.exit(1);
  }
  console.log(`Backend server running on http://localhost:${PORT}`);
  console.log(`WebSocket server running on ws://localhost:${PORT}`);
});

process.on('SIGINT', async () => {
    console.log('Shutting down server...');
    await prisma.$disconnect();
    server.close(() => {
        console.log('Server shut down.');
        process.exit(0);
    });
});