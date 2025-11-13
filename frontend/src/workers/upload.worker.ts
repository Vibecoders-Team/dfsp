// Simple upload worker using XMLHttpRequest for progress
export type UploadReq = { cmd:'upload'; url:string; headers?:Record<string,string>; body:Blob };

self.addEventListener('message', (ev: MessageEvent<UploadReq>) => {
  const m = ev.data;
  if (m.cmd !== 'upload') return;
  const xhr = new XMLHttpRequest();
  xhr.open('POST', m.url, true);
  if (m.headers) Object.entries(m.headers).forEach(([k,v]) => xhr.setRequestHeader(k, v));
  xhr.upload.onprogress = (e) => {
    self.postMessage({ ok:true, progress: e.lengthComputable ? (e.loaded / e.total) * 100 : null, loaded: e.loaded, total: e.total });
  };
  xhr.onreadystatechange = () => {
    if (xhr.readyState === 4) {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { self.postMessage({ ok:true, done:true, status:xhr.status, response: JSON.parse(xhr.responseText) }); }
        catch { self.postMessage({ ok:true, done:true, status:xhr.status, response: xhr.responseText }); }
      } else {
        self.postMessage({ ok:false, status:xhr.status, error: xhr.statusText || 'upload_failed' });
      }
    }
  };
  xhr.onerror = () => self.postMessage({ ok:false, error:'network_error' });
  xhr.send(m.body);
});

