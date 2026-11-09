import{useState,useEffect}from'react';
import{api}from'./api';
export function AdminContent(){
 const[lessons,setLessons]=useState<any[]>([]);const[id,setId]=useState('');const[text,setText]=useState('');const[message,setMessage]=useState('');const[busy,setBusy]=useState(false);
 const load=async()=>setLessons(await api('/admin/lessons'));
 useEffect(()=>{load().catch(e=>setMessage(e.message))},[]);
 return <section className="panel history-panel"><h2>Версии учебного контента</h2><p className="note">Изменения сохраняются как новая версия. Уже начатые уроки используют свой снимок. Проверяйте методическую корректность перед публикацией.</p><label className="field">Урок<select value={id} onChange={e=>{setId(e.target.value);setText(JSON.stringify(lessons.find(l=>l.id===e.target.value)?.content,null,2))}}><option value="">Выберите урок</option>{lessons.map(l=><option value={l.id} key={l.id}>{l.content.title} · v{l.version}</option>)}</select></label>{id&&<><label className="field">Содержание JSON<textarea className="content-editor" spellCheck={false} value={text} onChange={e=>setText(e.target.value)}/></label><button className="primary" disabled={busy} onClick={async()=>{setBusy(true);try{const content=JSON.parse(text);const result=await api('/admin/lessons/'+id,'PUT',{content,expected_version:lessons.find(l=>l.id===id).version});await load();setMessage('Сохранена версия '+result.version)}catch(e){setMessage(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}}>Сохранить новую версию</button></>}{message&&<p role="status">{message}</p>}</section>
}
