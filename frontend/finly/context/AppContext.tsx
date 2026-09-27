'use client';
import {createContext,useContext,useState,useEffect,useRef,useCallback,ReactNode} from 'react';
import {subscribeRealtime} from '../../lib/realtime.mjs';
export async function api(path:string,body?:unknown,method?:string){const response=await fetch('/api'+path,{method:method||(body===undefined?'GET':'POST'),headers:body instanceof FormData?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:body instanceof FormData?body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Проверьте введённые данные');return data}
export const money=(minor:number|null|undefined,currency='RUB')=>minor==null?'Неизвестно':new Intl.NumberFormat('ru-RU',{style:'currency',currency,maximumFractionDigits:2}).format(minor/(currency==='JPY'?1:100));
export function minor(value:string){const m=value.trim().replace(',','.').match(/^(\d+)(?:\.(\d{1,2}))?$/);if(!m)throw new Error('Укажите положительную сумму с точностью до копеек');const result=BigInt(m[1])*100n+BigInt((m[2]||'').padEnd(2,'0'));if(result>1000000000000n)throw new Error('Слишком большая сумма');return Number(result)}
const Context=createContext<any>(null);
export function AppProvider({children}:{children:ReactNode}){
 const [scope,setScope]=useState('demo'),[data,setData]=useState<any>(null),[transactions,setTransactions]=useState<any[]>([]),[notes,setNotes]=useState<any[]>([]),[connections,setConnections]=useState<any[]>([]),[error,setError]=useState(''),[connected,setConnected]=useState(false),[loading,setLoading]=useState(true);
 const requestId=useRef(0);
 const refresh=useCallback(async()=>{const id=++requestId.current;try{const [d,t,n,c]=await Promise.all([api('/dashboard?scope='+scope),api('/transactions?scope='+scope+'&limit=5000'),api('/notifications?scope='+scope),api('/connections')]);if(id!==requestId.current)return;setData(d);setTransactions(t.items);setNotes(n);setConnections(c);setError('')}catch(e){if(id===requestId.current)setError(e.message)}finally{if(id===requestId.current)setLoading(false)}},[scope]);
 const ref=useRef(refresh);ref.current=refresh;
 useEffect(()=>{setLoading(true);refresh()},[refresh]);
 useEffect(()=>subscribeRealtime({refresh:()=>ref.current(),onStatus:setConnected,onNotice:()=>{}}),[]);
 async function saveSettings(patch:any){const current=await api('/budget/settings?scope='+scope);await api('/budget/settings?scope='+scope,{...current,...patch},'PUT');await refresh()}
 return <Context.Provider value={{scope,setScope,data,transactions,notes,connections,error,setError,connected,loading,refresh,saveSettings}}>{children}</Context.Provider>
}
export const useApp=()=>useContext(Context);
