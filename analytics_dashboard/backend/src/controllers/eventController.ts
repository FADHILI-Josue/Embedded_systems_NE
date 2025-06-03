// src/controllers/eventController.ts
import { Request, Response, NextFunction } from 'express'; // Add NextFunction
import prisma from '../prismaClient';
import { broadcast } from '../services/webSocketService';

// Define a more specific type for your request body if you want, e.g.
interface EntryRequestBody {
  car_plate: string;
}
interface ExitRequestBody {
  car_plate: string;
  payment_status: 'PAID' | 'UNPAID_ATTEMPT';
}
interface AlertRequestBody {
    plate_number?: string;
    message: string;
    type: string;
}


export const recordEntry = async (req: Request<{}, {}, EntryRequestBody>, res: Response, next: NextFunction): Promise<void> => {
  try {
    const { car_plate } = req.body;
    if (!car_plate) {
      res.status(400).json({ error: 'car_plate is required' });
      return; // Ensure function exits after sending response
    }

    const existingUnpaid = await prisma.parkingEvent.findFirst({
      where: {
        plateNumber: car_plate,
        exitTime: null,
      },
    });

    if (existingUnpaid) {
      console.log(`Plate ${car_plate} already has an active entry. Ignoring duplicate entry attempt.`);
      res.status(200).json({ message: 'Plate already has an active entry', event: existingUnpaid });
      return;
    }

    const event = await prisma.parkingEvent.create({
      data: {
        plateNumber: car_plate,
        status: 'ENTERED',
      },
    });
    broadcast({ type: 'NEW_ENTRY', payload: event });
    res.status(201).json(event);
  } catch (error: any) {
    console.error('Error recording entry:', error);
    // Pass error to an error handling middleware if you have one, or send generic error
    res.status(500).json({ error: 'Failed to record entry', details: error.message });
    // Or use next(error); if you have a global error handler
  }
};

export const recordExit = async (req: Request<{}, {}, ExitRequestBody>, res: Response, next: NextFunction): Promise<void> => {
  try {
    const { car_plate, payment_status } = req.body;
    if (!car_plate || !payment_status) {
      res.status(400).json({ error: 'car_plate and payment_status are required' });
      return;
    }
    if (payment_status !== 'PAID' && payment_status !== 'UNPAID_ATTEMPT') {
        res.status(400).json({ error: "Invalid payment_status. Must be 'PAID' or 'UNPAID_ATTEMPT'." });
        return;
    }


    const event = await prisma.parkingEvent.findFirst({
      where: {
        plateNumber: car_plate,
        exitTime: null,
      },
      orderBy: {
        entryTime: 'desc',
      }
    });

    if (!event) {
      const alert = await prisma.alert.create({
        data: {
          plateNumber: car_plate,
          message: `Exit attempt for plate ${car_plate} with no recorded entry.`,
          type: 'UNAUTHORIZED_EXIT',
        },
      });
      broadcast({ type: 'NEW_ALERT', payload: alert });
      res.status(404).json({ error: 'No active entry found for this car plate to exit.' });
      return;
    }

    let updatedEvent;
    if (payment_status === 'PAID') {
      updatedEvent = await prisma.parkingEvent.update({
        where: { id: event.id },
        data: {
          exitTime: new Date(),
          status: 'EXITED_PAID',
        },
      });
      broadcast({ type: 'NEW_EXIT', payload: updatedEvent });
      res.status(200).json(updatedEvent);
    } else if (payment_status === 'UNPAID_ATTEMPT') {
       // For unpaid attempt, we just log an alert. The event itself isn't 'closed' or 'exited'.
       // The status 'EXITED_UNPAID_ATTEMPT' might be misleading if the car doesn't actually pass.
       // Let's reconsider this: an unpaid *attempt* is an alert. The ParkingEvent status shouldn't change
       // unless the car *actually* exits unpaid (which would be a different kind of alert/event status).

      const alert = await prisma.alert.create({
        data: {
          plateNumber: car_plate,
          message: `Unauthorized exit attempt for plate ${car_plate}. Payment pending.`,
          type: 'UNAUTHORIZED_EXIT',
        },
      });
      broadcast({ type: 'NEW_ALERT', payload: alert });
      // Send a specific response for this case
      res.status(403).json({ message: "Unauthorized exit attempt: Payment pending. Alert logged.", alert });
    }
    // The else for invalid payment_status is handled above.
  } catch (error: any) {
    console.error('Error recording exit:', error);
    res.status(500).json({ error: 'Failed to record exit', details: error.message });
  }
};

export const recordAlert = async (req: Request<{}, {}, AlertRequestBody>, res: Response, next: NextFunction): Promise<void> => {
    try {
        const { plate_number, message, type } = req.body;
        if (!message || !type) {
            res.status(400).json({ error: 'message and type are required for an alert' });
            return;
        }
        const alert = await prisma.alert.create({
            data: {
                plateNumber: plate_number || null, // Ensure it's null if undefined
                message,
                type,
            },
        });
        broadcast({ type: 'NEW_ALERT', payload: alert });
        res.status(201).json(alert);
    } catch (error: any) {
        console.error('Error recording alert:', error);
        res.status(500).json({ error: 'Failed to record alert', details: error.message });
    }
};