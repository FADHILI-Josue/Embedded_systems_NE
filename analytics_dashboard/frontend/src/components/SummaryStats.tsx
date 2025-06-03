import React from 'react';

interface SummaryData {
  totalEntriesToday: number;
  totalExitsToday: number;
  vehiclesCurrentlyIn: number;
  recentAlertsCount: number;
}

interface Props {
  summary: SummaryData | null;
}

const SummaryStats: React.FC<Props> = ({ summary }) => {
  if (!summary) {
    return (
        <div className="card">
            <h2>Summary</h2>
            <p>Loading summary...</p>
        </div>
    );
  }

  return (
    <div className="card">
      <h2>Summary</h2>
      <div className="summary-stats">
        <div className="stat-item">
            <h3>{summary.totalEntriesToday}</h3>
            <p>Entries Today</p>
        </div>
        <div className="stat-item">
            <h3>{summary.totalExitsToday}</h3>
            <p>Exits Today (Paid)</p>
        </div>
        <div className="stat-item">
            <h3>{summary.vehiclesCurrentlyIn}</h3>
            <p>Vehicles Currently In</p>
        </div>
        <div className="stat-item">
            <h3>{summary.recentAlertsCount}</h3>
            <p>Alerts (Last 24h)</p>
        </div>
      </div>
    </div>
  );
};

export default SummaryStats;