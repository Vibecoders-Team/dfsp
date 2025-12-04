import { api } from './api';
import { notify } from './toast';

type QueuedRequest = {
  url: string;
  method: string;
  data?: unknown;
  createdAt: number;
};

const KEY = 'dfsp_offline_queue';

function loadQueue(): QueuedRequest[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    return JSON.parse(raw) as QueuedRequest[];
  } catch {
    return [];
  }
}

function saveQueue(q: QueuedRequest[]) {
  try { localStorage.setItem(KEY, JSON.stringify(q)); } catch { /* ignore */ }
}

export function enqueueRequest(req: QueuedRequest) {
  const q = loadQueue();
  q.push(req);
  saveQueue(q);
  notify.info('Request queued offline', { description: req.url, dedupeId: 'offline-queued' });
}

async function processQueueOnce() {
  const q = loadQueue();
  if (q.length === 0) return;
  const next = q.shift();
  if (!next) return;
  saveQueue(q);
  try {
    const token = localStorage.getItem('ACCESS_TOKEN');
    const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
    await api.request({ url: next.url, method: next.method as any, data: next.data, headers });
    notify.success('Queued request sent', { description: next.url, dedupeId: 'offline-sent' });
  } catch (e) {
    // push back to queue and abort further attempts to avoid hammering
    q.unshift(next);
    saveQueue(q);
    throw e;
  }
}

export async function flushQueue() {
  while (true) {
    try {
      await processQueueOnce();
    } catch {
      break;
    }
    if (loadQueue().length === 0) break;
  }
}

export function initOfflineQueue() {
  const onOnline = () => { flushQueue().catch(()=>{}); };
  if (typeof window !== 'undefined') {
    window.addEventListener('online', onOnline);
  }
  if (typeof navigator !== 'undefined' && navigator.onLine) {
    flushQueue().catch(()=>{});
  }
}
