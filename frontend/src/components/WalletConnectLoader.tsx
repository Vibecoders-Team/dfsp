// Small loader: listens for WalletConnect events and lazily mounts WalletConnectPortal on demand
export function initWalletConnectLoader() {
  if (typeof window === 'undefined') return;
  // avoid double init
  if ((window as any).__dfsp_wc_loader_inited) return;
  (window as any).__dfsp_wc_loader_inited = true;

  const mountPortal = async () => {
    try {
      const mod = await import('./WalletConnectPortal');
      const WalletConnectPortal = mod.default;
      if (!WalletConnectPortal) return;
      // create container only once
      let el = document.getElementById('dfsp-wc-portal');
      if (!el) {
        el = document.createElement('div');
        el.id = 'dfsp-wc-portal';
        document.body.appendChild(el);
      }
      // Only mount once
      if ((window as any).__dfsp_wc_portal_mounted) return;
      (window as any).__dfsp_wc_portal_mounted = true;

      // dynamic import of react-dom/client to avoid adding to initial bundle
      const rd = await import('react-dom/client');
      const React = await import('react');
      const root = rd.createRoot(el as Element);
      root.render(React.createElement(WalletConnectPortal));
    } catch (e) {
      // ignore errors silently
      // console.debug('wc loader error', e);
    }
  };

  const onUri = () => mountPortal();
  // when QR close also ensure portal exists before attempting to mount
  const onClose = () => {
    // ensure mounted for close events as well
    mountPortal();
  };

  window.addEventListener('dfsp:wc-display-uri', onUri as EventListener);
  window.addEventListener('dfsp:wc-close-qr', onClose as EventListener);
}

// auto-init when module is imported
initWalletConnectLoader();
