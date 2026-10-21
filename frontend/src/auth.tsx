import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { api, post, refreshSession, setToken } from './api';
import type { AuthResponse, User } from './types';
interface AuthState {user:User|null;loading:boolean;mfaRequired:boolean;login:(email:string,password:string,totp?:string)=>Promise<void>;logout:()=>Promise<void>;updateUser:()=>Promise<void>;}
const AuthContext = createContext<AuthState|null>(null);
export function AuthProvider({children}:{children:ReactNode}) {
  const [user,setUser] = useState<User|null>(null);
  const [loading,setLoading] = useState(true);
  const [mfaRequired,setMfaRequired] = useState(false);
  function apply(auth:AuthResponse) { setUser(auth.user); setMfaRequired(auth.mfa_required ?? ((auth.user.role !== 'user') && !auth.user.mfa_enabled)); }
  useEffect(() => {
    let active = true;
    refreshSession().then(auth => { if(active) apply(auth); }).catch(() => { if(active) {setToken(null);setUser(null);} }).finally(() => { if(active) setLoading(false); });
    const expired = () => { setToken(null);setUser(null);setMfaRequired(false); };
    window.addEventListener('vigia:session-expired',expired);
    return () => {active=false; window.removeEventListener('vigia:session-expired',expired);};
  },[]);
  async function login(email:string,password:string,totp?:string) {
    const auth = await post<AuthResponse>('/auth/login',{email,password,totp:totp || undefined,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone});
    setToken(auth.access_token);apply(auth);
  }
  async function logout() { await post('/auth/logout');setToken(null);setUser(null);setMfaRequired(false); }
  async function updateUser() {const me = await api<User>('/auth/me');setUser(me);setMfaRequired(me.role !== 'user' && !me.mfa_enabled);}
  return <AuthContext.Provider value={{user,loading,mfaRequired,login,logout,updateUser}}>{children}</AuthContext.Provider>;
}
export function useAuth() {const value=useContext(AuthContext);if(!value) throw new Error('AuthProvider requerido');return value;}
