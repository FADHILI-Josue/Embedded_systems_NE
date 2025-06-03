import React, { useState, useEffect, useRef } from 'react';
import './App.css'; // Assuming you have App.css for specific styles
import SummaryStats from './components/SummaryStats';
import EventLog from './components/EventLog';
import AlertLog from './components/AlertLog';

// Access environment variables using import.meta.env
const BACKEND_HTTP_URL = import.meta.env.VITE_BACKEND_HTTP_URL;
const BACKEND_WS_URL = import.meta.env.VITE_BACKEND_WS_URL;

// ... (rest of the SummaryData, ParkingEvent, Alert interfaces remain the same) ...
interface SummaryData {
  totalEntriesToday: number;
  totalExitsToday: number;
  vehiclesCurrentlyIn: number;
  recentAlertsCount: number;
}

interface ParkingEvent {
  id: string;
  plateNumber: string;
  entryTime: string;
  exitTime?: string | null;
  status: string;
  createdAt: string;
}

interface Alert {
  id: string;
  plateNumber?: string | null;
  message: string;
  type: string;
  timestamp: string;
}


function App() {
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [events, setEvents] = useState<ParkingEvent[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const ws = useRef<WebSocket | null>(null);

  const fetchData = async () => {
    try {
      if (!BACKEND_HTTP_URL) {
        console.error("Backend HTTP URL is not defined. Check your .env file and VITE_ prefix.");
        return;
      }
      const [summaryRes, eventsRes, alertsRes] = await Promise.all([
        fetch(`${BACKEND_HTTP_URL}/analytics/summary`),
        fetch(`${BACKEND_HTTP_URL}/analytics/events`),
        fetch(`${BACKEND_HTTP_URL}/analytics/alerts`),
      ]);

      if (!summaryRes.ok || !eventsRes.ok || !alertsRes.ok) {
        console.error("Failed to fetch data from backend", {
            summaryStatus: summaryRes.status,
            eventsStatus: eventsRes.status,
            alertsStatus: alertsRes.status,
        });
        // Optionally set some error state to display in UI
        return;
      }

      setSummary(await summaryRes.json());
      setEvents(await eventsRes.json());
      setAlerts(await alertsRes.json());
    } catch (error) {
      console.error('Failed to fetch initial data:', error);
    }
  };
  
  const connectWebSocket = () => {
    if (!BACKEND_WS_URL) {
        console.error("Backend WebSocket URL is not defined. Check your .env file and VITE_ prefix.");
        return;
    }
    console.log(`Attempting to connect WebSocket to ${BACKEND_WS_URL}...`);
    ws.current = new WebSocket(BACKEND_WS_URL);

    ws.current.onopen = () => {
      console.log('WebSocket Connected');
      setIsConnected(true);
    };

    ws.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data as string);
        console.log('Received WebSocket data:', data);

        if (data.type === 'NEW_ENTRY') {
          setEvents(prev => [data.payload, ...prev.slice(0, 19)]);
          fetchData(); 
        } else if (data.type === 'NEW_EXIT') {
           setEvents(prev => {
              const existingIndex = prev.findIndex(e => e.id === data.payload.id);
              if (existingIndex > -1) {
                  const updatedEvents = [...prev];
                  updatedEvents[existingIndex] = data.payload;
                  return updatedEvents;
              }
              return [data.payload, ...prev.slice(0,19)];
           });
          fetchData(); 
        } else if (data.type === 'NEW_ALERT') {
          setAlerts(prev => [data.payload, ...prev.slice(0, 19)]);
          fetchData();
        } else if (data.type === 'CONNECTION_ACK') {
            console.log('Connection Acknowledged by server:', data.message);
        }

      } catch (error) {
        console.error('Error processing WebSocket message:', error);
      }
    };

    ws.current.onclose = (event) => {
      console.log('WebSocket Disconnected. Code:', event.code, 'Reason:', event.reason);
      setIsConnected(false);
      if (!event.wasClean) { // Attempt to reconnect if not a clean close
        setTimeout(() => {
          console.log('Retrying WebSocket connection...');
          connectWebSocket();
        }, 5000);
      }
    };

    ws.current.onerror = (error) => {
      console.error('WebSocket Error:', error);
      // The onclose event will usually follow an error, triggering reconnection logic
    };
  };

  useEffect(() => {
    fetchData();
    connectWebSocket();

    return () => {
      if (ws.current) {
        console.log("Closing WebSocket connection on component unmount.");
        ws.current.close(1000, "Component unmounting"); // 1000 indicates a normal closure
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="App">
      <header>
        <h1>Parking Management Dashboard</h1>
        <p style={{fontSize: "0.9em", opacity: 0.8}}>WebSocket Status: {isConnected ? 'Connected' : 'Disconnected'}</p>
      </header>
      
      <SummaryStats summary={summary} />

      <div className="dashboard-layout">
        <EventLog events={events} />
        <AlertLog alerts={alerts} />
      </div>
    </div>
  );
}

export default App;