// Native EventSource automatically reconnects and sends Last-Event-ID.
// Refresh the full snapshot on open: clients recover even if events were missed.
export function subscribeRealtime({refresh,onStatus,onNotice,EventSourceClass=EventSource,delay=180}) {
  const stream=new EventSourceClass('/api/events');
  let timer;
  stream.onopen=()=>{onStatus(true);refresh()};
  stream.onerror=()=>onStatus(false);
  const handle=event=>{
    clearTimeout(timer);
    timer=setTimeout(refresh,delay);
    if(event.type==='notification.created') {
      try {onNotice(JSON.parse(event.data).payload.title)} catch { /* refresh still recovers state */ }
    }
  };
  for(const name of ['transaction.created','transaction.updated','budget.updated','notification.created','notification.updated','sync.completed','sync.failed','import.updated'])stream.addEventListener(name,handle);
  return ()=>{stream.close();clearTimeout(timer)};
}
