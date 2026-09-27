import test from 'node:test';
import assert from 'node:assert/strict';
import {subscribeRealtime} from '../lib/realtime.mjs';

class FakeStream {
  static latest;
  constructor(url){this.url=url;this.handlers={};FakeStream.latest=this}
  addEventListener(name,fn){this.handlers[name]=fn}
  close(){this.closed=true}
  emit(type,payload={}){this.handlers[type]({type,data:JSON.stringify({payload})})}
}
test('purchase and budget events refresh snapshot, notifications arrive, reconnect refetches',async()=>{
  let refreshes=0;const statuses=[];const notices=[];
  const close=subscribeRealtime({refresh:()=>refreshes++,onStatus:v=>statuses.push(v),onNotice:v=>notices.push(v),EventSourceClass:FakeStream,delay:0});
  const stream=FakeStream.latest;
  assert.equal(stream.url,'/api/events');
  stream.onopen();assert.equal(refreshes,1);
  stream.emit('transaction.created');stream.emit('budget.updated');stream.emit('notification.created',{title:'Дневной бюджет превышен'});
  await new Promise(resolve=>setTimeout(resolve,10));
  assert.equal(refreshes,2);assert.deepEqual(notices,['Дневной бюджет превышен']);
  stream.onerror();stream.onopen();
  assert.deepEqual(statuses,[true,false,true]);assert.equal(refreshes,3);
  close();assert.equal(stream.closed,true);
});
test('unmount cancels pending refresh',async()=>{
  let count=0;
  const close=subscribeRealtime({refresh:()=>count++,onStatus:()=>{},onNotice:()=>{},EventSourceClass:FakeStream,delay:0});
  FakeStream.latest.emit('transaction.updated');close();
  await new Promise(resolve=>setTimeout(resolve,10));assert.equal(count,0);
});
