import React from 'react';
import { format } from 'date-fns'; // Make sure you have date-fns installed

interface Alert {
  id: string;
  plateNumber?: string | null;
  message: string;
  type: string;
  timestamp: string; // Assuming this is an ISO string date from backend
}

interface Props {
  alerts: Alert[];
}

const AlertLog: React.FC<Props> = ({ alerts }) => {
  return (
    <div className="card"> {/* Ensure .card class is styled */}
      <h2>Recent Alerts</h2>
      {alerts.length === 0 && <p>No recent alerts.</p>}
      <ul>
        {alerts.map((alert) => (
          <li 
            key={alert.id} 
            className={`alert-item ${alert.type.toLowerCase().includes('unauthorized') || alert.type.toLowerCase().includes('error') ? 'unauthorized' : ''}`}
            // Ensure .alert-item and .alert-item.unauthorized classes are styled
          >
            <strong>Type:</strong> {alert.type} <br />
            {alert.plateNumber && <><strong>Plate:</strong> {alert.plateNumber} <br /></>}
            <strong>Message:</strong> {alert.message} <br />
            <strong>Time:</strong> {format(new Date(alert.timestamp), 'MMM d, yyyy, h:mm:ss a')}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default AlertLog;