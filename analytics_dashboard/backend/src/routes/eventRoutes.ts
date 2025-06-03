import { Router } from 'express';
import { recordAlert, recordEntry, recordExit } from '../controllers/eventController';

const router = Router();

router.post('/entry', recordEntry);
router.post('/exit', recordExit);
router.post('/alert', recordAlert);

export default router;