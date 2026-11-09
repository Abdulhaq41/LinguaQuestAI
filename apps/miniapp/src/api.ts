export class ApiError extends Error{constructor(public status:number,message:string){super(message)}}
export async function api<T=any>(path:string,method='GET',body?:unknown):Promise<T>{
 const response=await fetch('/api'+path,{method,credentials:'same-origin',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
 const result=await response.json().catch(()=>({detail:'Сервер вернул некорректный ответ'}));
 if(!response.ok)throw new ApiError(response.status,typeof result.detail==='string'?result.detail:JSON.stringify(result.detail));
 return result;
}
export type Profile={id:number;name:string;xp:number;coins:number;level:number;settings:Record<string,any>;subscription:null|{plan:string;expires_at:number;auto_renew:boolean};progress:{completed_lessons:number;streak:number;today_xp:number;history:any[];achievements:any[]};route:{level:string;note:string;focus:string}};
export type Lesson={id:string;title:string;description:string;level:string;chapter:string;minutes:number;xp:number;free:boolean;locked:boolean;completed:boolean};
export type AppConfig={development:boolean;dev_auth:boolean;telegram_connected:boolean;ai_connected:boolean;voice_available:boolean;support_contact:string;bot_username:string};
declare global{interface Window{Telegram?:{WebApp:{initData:string;ready:()=>void;expand:()=>void;openInvoice:(url:string,callback:(status:string)=>void)=>void;BackButton:{show:()=>void;hide:()=>void;onClick:(fn:()=>void)=>void;offClick:(fn:()=>void)=>void};HapticFeedback?:{notificationOccurred:(kind:string)=>void}}}}}
