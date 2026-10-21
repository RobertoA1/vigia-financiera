import { useEffect, useRef } from 'react';
import useSWR from 'swr';
import { useAuth } from './auth';
import type { Alert, List } from './types';
export function NotificationDelivery() {
  const {user}=useAuth();const enabled=Boolean(user?.browser_notifications)&&typeof Notification!=='undefined'&&Notification.permission==='granted';
  const {data}=useSWR<List<Alert>>(enabled?'/alerts':null,{refreshInterval:10000});
  const seen=useRef<Set<string>|null>(null);
  useEffect(()=>{if(!enabled){seen.current=null;return;}if(!data)return;if(!seen.current){seen.current=new Set(data.items.map(a=>a.id));return;}for(const alert of data.items){if(!seen.current.has(alert.id)&&!alert.read){try{const notification=new Notification('Vigía Financiera · Nueva alerta',{body:'Se detectó un enlace que requiere atención. Revisa la evidencia en la aplicación.',tag:alert.id,icon:'/favicon.svg'});notification.onclick=()=>{window.focus();notification.close();};}catch{/* Browser policies may block notifications without affecting analysis. */}}seen.current.add(alert.id);}},[enabled,data]);
  return null;
}
