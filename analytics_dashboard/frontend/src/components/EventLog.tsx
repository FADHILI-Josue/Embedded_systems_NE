import React from 'react';
import { format } from 'date-fns'; // Make sure you have date-fns installed: npm install date-fns

interface ParkingEvent {
  id: string;
  plateNumber: string;
  entryTime: string; // Assuming these are ISO string dates from backend
  exitTime?: string | null;
  status: string;
  createdAt: string;
}

interface Props {
  events: ParkingEvent[];
}

const EventLog: React.FC<Props> = ({ events }) => {
  return (
    <div className="card"> {/* Ensure .card class is styled */}
      <h2>Recent Parking Events</h2>
      {events.length === 0 && <p>No recent events.</p>}
      <ul>
        {events.map((event) => (
          <li key={event.id}>
            <strong>Plate:</strong> {event.plateNumber} <br />
            <strong>Status:</strong> {event.status} <br />
            <strong>Entry:</strong> {format(new Date(event.entryTime), 'MMM d, yyyy, h:mm:ss a')}
            {event.exitTime && (
              <> <br /><strong>Exit:</strong> {format(new Date(event.exitTime), 'MMM d, yyyy, h:mm:ss a')}</>
            )}
            <br />
            <small>Logged: {format(new Date(event.createdAt), 'MMM d, yyyy, h:mm:ss a')}</small>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default EventLog;