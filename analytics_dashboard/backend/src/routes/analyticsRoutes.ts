import { Router } from 'express';
import { getSummary, getRecentEvents, getRecentAlerts } from '../controllers/analyticsController';

const router = Router();

router.get('/summary', getSummary);
router.get('/events', getRecentEvents);
router.get('/alerts', getRecentAlerts);

export default router;