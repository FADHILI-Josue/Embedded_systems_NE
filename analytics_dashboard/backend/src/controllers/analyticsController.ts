import { Request, Response } from 'express';
import prisma from '../prismaClient';
import { subDays } from 'date-fns';


export const getSummary = async (req: Request, res: Response) => {
  try {
    const today = new Date();
    const startOfToday = new Date(today.setHours(0, 0, 0, 0));
    const endOfToday = new Date(today.setHours(23, 59, 59, 999));

    const totalEntriesToday = await prisma.parkingEvent.count({
      where: {
        entryTime: {
          gte: startOfToday,
          lte: endOfToday,
        },
      },
    });

    const totalExitsToday = await prisma.parkingEvent.count({
      where: {
        exitTime: {
          gte: startOfToday,
          lte: endOfToday,
        },
        status: 'EXITED_PAID', // Only count successful, paid exits
      },
    });

    const vehiclesCurrentlyIn = await prisma.parkingEvent.count({
      where: {
        exitTime: null, // No exit time means they are still in
        status: 'ENTERED',
      },
    });

    const recentAlertsCount = await prisma.alert.count({
        where: {
            timestamp: {
                gte: subDays(new Date(), 1) // Alerts in the last 24 hours
            }
        }
    });

    res.json({
      totalEntriesToday,
      totalExitsToday,
      vehiclesCurrentlyIn,
      recentAlertsCount
    });
  } catch (error: any) {
    console.error('Error fetching summary:', error);
    res.status(500).json({ error: 'Failed to fetch summary', details: error.message });
  }
};

export const getRecentEvents = async (req: Request, res: Response) => {
  try {
    const events = await prisma.parkingEvent.findMany({
      orderBy: { createdAt: 'desc' },
      take: 20, // Get last 20 events
    });
    res.json(events);
  } catch (error: any) {
    console.error('Error fetching recent events:', error);
    res.status(500).json({ error: 'Failed to fetch recent events', details: error.message });
  }
};

export const getRecentAlerts = async (req: Request, res: Response) => {
  try {
    const alerts = await prisma.alert.findMany({
      orderBy: { timestamp: 'desc' },
      take: 20, // Get last 20 alerts
    });
    res.json(alerts);
  } catch (error: any) {
    console.error('Error fetching recent alerts:', error);
    res.status(500).json({ error: 'Failed to fetch recent alerts', details: error.message });
  }
};