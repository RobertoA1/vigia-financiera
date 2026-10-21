import { lazy, Suspense, useState } from 'react';
import { Navigate, NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { Activity, Bell, BookOpen, ChevronDown, ChevronRight, CircleHelp, FileBarChart2, Globe2, LayoutDashboard, Link2, LogOut, Menu, PanelLeftClose, Settings2, ShieldAlert, SlidersHorizontal, Users, X } from 'lucide-react';
import { SWRConfig } from 'swr';
import { useAuth } from './auth';
import { Brand, ErrorBox, Loading, label } from './ui';
import { AuthPage, MfaEnrollment } from './AuthPages';
import { NotificationDelivery } from './notifications';
import { ORGANIZATION } from './config';
const DashboardPage=lazy(()=>import('./DashboardPage'));
const AnalyzePage=lazy(()=>import('./EvaluationPages').then(m=>({default:m.AnalyzePage})));
const HistoryPage=lazy(()=>import('./EvaluationPages').then(m=>({default:m.HistoryPage})));
const EvaluationDetail=lazy(()=>import('./EvaluationPages').then(m=>({default:m.EvaluationDetail})));
const AlertsPage=lazy(()=>import('./ManagementPages').then(m=>({default:m.AlertsPage})));
const IncidentsPage=lazy(()=>import('./ManagementPages').then(m=>({default:m.IncidentsPage})));
const ReportsPage=lazy(()=>import('./ManagementPages').then(m=>({default:m.ReportsPage})));
const UsersPage=lazy(()=>import('./SettingsPages').then(m=>({default:m.UsersPage})));
const IntegrationsPage=lazy(()=>import('./SettingsPages').then(m=>({default:m.IntegrationsPage})));
const ProfilePage=lazy(()=>import('./SettingsPages').then(m=>({default:m.ProfilePage})));
const PrivacyPage=lazy(()=>import('./SettingsPages').then(m=>({default:m.PrivacyPage})));
const HelpPage=lazy(()=>import('./SettingsPages').then(m=>({default:m.HelpPage})));
const navItems=[{path:'/',title:'Resumen',icon:LayoutDashboard},{path:'/analizar',title:'Analizar enlace',icon:Link2},{path:'/evaluaciones',title:'Evaluaciones',icon:Activity},{path:'/alertas',title:'Alertas',icon:Bell},{path:'/incidentes',title:'Incidentes',icon:ShieldAlert},{path:'/reportes',title:'Reportes',icon:FileBarChart2}];
function Shell() {
  const {user,logout}=useAuth();
  const [navOpen,setNavOpen]=useState(false);
  const [logoutError,setLogoutError]=useState<unknown>(null);
  const location=useLocation();
  const title=[...navItems,{path:'/usuarios',title:'Usuarios y roles'},{path:'/integraciones',title:'Integraciones'},{path:'/cuenta',title:'Mi cuenta'},{path:'/privacidad',title:'Privacidad'},{path:'/ayuda',title:'Guía de uso'}].find(n=>n.path===location.pathname)?.title || 'Detalle de evaluación';
  return <div className="app-shell"><NotificationDelivery/><a className="skip-link" href="#main">Ir al contenido</a>{navOpen&&<button aria-label="Cerrar navegación" className="sidebar-backdrop" onClick={()=>setNavOpen(false)}/>}<aside className={`sidebar ${navOpen?'mobile-open':''}`}><div className="sidebar-brand"><Brand/><button className="icon-button mobile-only" aria-label="Cerrar menú" onClick={()=>setNavOpen(false)}><X size={20}/></button></div><div className="workspace"><span className="workspace-icon"><ShieldAlert size={18}/></span><div><strong>Centro de operaciones</strong><span>{ORGANIZATION}</span></div><ChevronDown size={14}/></div><div className="nav-label">MONITOREO</div><nav aria-label="Navegación principal">{navItems.map(({path,title,icon:Icon})=><NavLink key={path} end={path==='/'} to={path} onClick={()=>setNavOpen(false)} className={({isActive})=>`nav-link ${isActive?'active':''}`}><Icon size={18}/><span>{title}</span>{path==='/analizar'&&<span className="nav-key" aria-hidden="true">↗</span>}</NavLink>)}</nav><div className="nav-label administration">ADMINISTRACIÓN</div><nav aria-label="Configuración">{user?.role==='admin'&&<><NavLink to="/usuarios" className="nav-link" onClick={()=>setNavOpen(false)}><Users size={18}/>Usuarios y roles</NavLink><NavLink to="/integraciones" className="nav-link" onClick={()=>setNavOpen(false)}><SlidersHorizontal size={18}/>Integraciones</NavLink></>}<NavLink to="/cuenta" className="nav-link" onClick={()=>setNavOpen(false)}><Settings2 size={18}/>Mi cuenta</NavLink><NavLink to="/privacidad" className="nav-link" onClick={()=>setNavOpen(false)}><BookOpen size={18}/>Privacidad y datos</NavLink></nav><div className="sidebar-bottom"><div className="scope-card"><span className="live-dot"/><strong>Entorno académico</strong><p>Detección orientativa con evidencia verificable.</p><NavLink to="/ayuda">Conocer los alcances <ChevronRight size={13}/></NavLink></div><NavLink className="nav-link" to="/ayuda"><CircleHelp size={18}/>Centro de ayuda</NavLink><div className="sidebar-version"><span>VIGÍA FINANCIERA</span><span>v1.0</span></div></div></aside><div className="main-shell"><header className="topbar"><div className="breadcrumbs"><button className="icon-button mobile-only" aria-label="Abrir navegación" onClick={()=>setNavOpen(true)}><Menu size={20}/></button><PanelLeftClose className="desktop-icon" size={17}/><span className="breadcrumb-root">Workspace</span><ChevronRight size={13}/><strong>{title}</strong></div><div className="topbar-right"><span className="environment-pill"><span className="live-dot"/>Académico</span><span className="topbar-divider"/><NavLink className="icon-button" to="/alertas" aria-label="Ver alertas"><Bell size={18}/></NavLink><NavLink className="account-chip" to="/cuenta"><span className="avatar">{(user?.name||user?.email||'V').slice(0,2).toUpperCase()}</span><span className="account-name"><strong>{user?.name}</strong><small>{label(user?.role||'user')}</small></span><ChevronDown size={13}/></NavLink><button className="icon-button" aria-label="Cerrar sesión" onClick={()=>{setLogoutError(null);void logout().catch(setLogoutError);}}><LogOut size={17}/></button></div></header><main id="main" className="main-content"><ErrorBox error={logoutError}/><Suspense fallback={<Loading/>}><Outlet/></Suspense></main><footer className="app-footer"><span><ShieldAlert size={12}/> Vigía Financiera · Análisis preventivo de phishing</span><span><Globe2 size={12}/>{user?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone}</span></footer></div></div>;
}
function AdminOnly({children}:{children:React.ReactNode}) {const {user}=useAuth();return user?.role==='admin'?children:<Navigate to="/" replace/>;}
export default function App() {
  const {user,loading,mfaRequired}=useAuth();
  if(loading)return <div className="boot"><Brand/><Loading text="Restableciendo sesión segura…"/></div>;
  if(!user)return <AuthPage/>;
  if(mfaRequired)return <div className="auth-shell"><MfaEnrollment required/></div>;
  return <SWRConfig key={user.id} value={{provider:()=>new Map()}}><Routes><Route element={<Shell/>}><Route index element={<DashboardPage/>}/><Route path="analizar" element={<AnalyzePage/>}/><Route path="evaluaciones" element={<HistoryPage/>}/><Route path="evaluaciones/:id" element={<EvaluationDetail/>}/><Route path="alertas" element={<AlertsPage/>}/><Route path="incidentes" element={<IncidentsPage/>}/><Route path="reportes" element={<ReportsPage/>}/><Route path="usuarios" element={<AdminOnly><UsersPage/></AdminOnly>}/><Route path="integraciones" element={<AdminOnly><IntegrationsPage/></AdminOnly>}/><Route path="cuenta" element={<ProfilePage/>}/><Route path="privacidad" element={<PrivacyPage/>}/><Route path="ayuda" element={<HelpPage/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Route></Routes></SWRConfig>;
}
