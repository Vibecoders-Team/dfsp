import { toast, type ExternalToast } from 'sonner';

const activeIds = new Set<string>();

type ToastKind = 'success' | 'error' | 'info' | 'warning' | 'message';

type ToastOpts = ExternalToast & { dedupeId?: string };

function mark(id?: string) {
  if (id) activeIds.add(id);
  if (id && typeof window !== 'undefined') {
    window.setTimeout(() => activeIds.delete(id), 5000);
  }
}

function show(kind: ToastKind, message: string, opts?: ToastOpts) {
  const id = opts?.dedupeId;
  if (id && activeIds.has(id)) return id;
  const finalOpts = { ...opts, id, closeButton: true, duration: opts?.duration ?? 3500 };
  let res: string | number;
  switch (kind) {
    case 'success':
      res = toast.success(message, finalOpts);
      break;
    case 'error':
      res = toast.error(message, finalOpts);
      break;
    case 'info':
      res = toast.info(message, finalOpts);
      break;
    case 'warning':
      res = toast.warning(message, finalOpts);
      break;
    case 'message':
    default:
      res = toast(message, finalOpts);
  }
  mark(id);
  return res;
}

export const notify = {
  success: (msg: string, opts?: ToastOpts) => show('success', msg, opts),
  error: (msg: string, opts?: ToastOpts) => show('error', msg, opts),
  info: (msg: string, opts?: ToastOpts) => show('info', msg, opts),
  warning: (msg: string, opts?: ToastOpts) => show('warning', msg, opts),
  message: (msg: string, opts?: ToastOpts) => show('message', msg, opts),
};
