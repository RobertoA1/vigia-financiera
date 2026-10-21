export type Role = 'admin' | 'analyst' | 'user';
export type Risk = 'low' | 'moderate' | 'high' | 'critical';
export interface User {id:string;email:string;name:string;role:Role;active:boolean;mfa_enabled:boolean;timezone:string;email_notifications:boolean;browser_notifications:boolean;}
export interface AuthResponse {access_token:string;token_type:string;user:User;mfa_required:boolean;}
export interface Indicator {code:string;title:string;detail:string;weight:number;group:string;}
export interface Evaluation {id:string;user_id:string;domain:string;url_display:string;score:number;risk:Risk;status:'preliminary'|'complete'|'pending'|'inconclusive';source:string;indicators:Indicator[];sources:Record<string,unknown>[];explanation:string;recommendations:string[];engine_version:string;created_at:string;updated_at:string;ai:Record<string,unknown>|null;reputation:Record<string,unknown>|null;latency_ms:number;}
export interface Dashboard {total_evaluations:number;suspicious_evaluations:number;open_incidents:number;resolved_incidents:number;risk_distribution:Record<Risk,number>;trend:{date:string;total:number;suspicious:number}[];recent:Evaluation[];geography_available:boolean;}
export interface Alert {id:string;evaluation_id:string;user_id:string;title:string;risk:Risk;message:string;read:boolean;created_at:string;}
export interface Incident {id:string;evaluation_id:string;title:string;severity:Risk;status:'open'|'investigating'|'resolved'|'dismissed';assigned_to:string|null;created_at:string;updated_at:string;timeline:{at:string;actor:string;action:string;note:string}[];}
export interface Report {id:string;kind:string;format:string;status:string;created_at:string;filters:Record<string,unknown>;}
export interface List<T> {items:T[];total:number;}
