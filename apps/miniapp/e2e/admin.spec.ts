import {test,expect,type Page} from '@playwright/test';
import {createHmac} from 'node:crypto';

// Simulate a separate client behind the trusted localhost Vite proxy so this
// suite does not consume the normal learner suite's per-IP request allowance.
test.use({extraHTTPHeaders:{'X-Forwarded-For':'127.0.0.2'}});

// These signatures use a synthetic local token. No Telegram API request is made.
async function login(page:Page,id:number,name:string){
 const fields={auth_date:String(Math.floor(Date.now()/1000)),user:JSON.stringify({id,first_name:name,username:'test_relative_'+id})};
 const check=Object.entries(fields).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>`${k}=${v}`).join('\n');
 const key=createHmac('sha256','WebAppData').update('123456:synthetic-test-token').digest();
 const hash=createHmac('sha256',key).update(check).digest('hex');
 expect((await page.request.post('/api/auth/telegram',{data:{init_data:new URLSearchParams({...fields,hash}).toString()}})).ok()).toBeTruthy();
 expect((await page.request.patch('/api/users/me/settings',{data:{}})).ok()).toBeTruthy();
 await page.route('https://telegram.org/**',route=>route.fulfill({body:''}));
}

test('owner grants, extends and revokes family access; audit and system controls',async({page,browser},info)=>{
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
 const friendId=5_000_000_000+Math.floor(Math.random()*100_000_000);
 const friendContext=await browser.newContext({baseURL:'http://localhost:5173',viewport:page.viewportSize(),extraHTTPHeaders:{'X-Forwarded-For':'127.0.0.3'}});
 const friend=await friendContext.newPage();
 await login(friend,friendId,'Семья '+info.project.name);
 await login(page,8284379630,'Владелец');
 await page.goto('/?section=admin');
 await expect(page.getByRole('heading',{name:'Панель администратора'})).toBeVisible();
 await expect(page.locator('.admin-metrics .panel')).toHaveCount(6);
 await page.getByRole('navigation',{name:'Разделы админки'}).getByRole('button',{name:'Пользователи',exact:true}).click();
 await page.getByLabel('Поиск пользователя').fill(String(friendId));
 await page.getByRole('button',{name:'Найти',exact:true}).click();
 await page.locator('.admin-member').filter({hasText:String(friendId)}).click();
 await expect(page.locator('.admin-user-detail h2')).toHaveText('Семья '+info.project.name);
 await page.getByLabel('Тариф подарка').selectOption('PRO');
 await page.getByLabel('Срок в днях', {exact:true}).fill('7');
 await page.getByLabel('Причина подарка').fill('Подарок родственнику на неделю');
 page.once('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'Выдать подписку',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('Подарочная подписка выдана');
 const initial=(await (await page.request.get(`/api/admin/users/${friendId}`)).json()).grants[0];
 expect(initial.plan).toBe('PRO');
 expect((await (await page.request.get('/api/admin/payments')).json())).toHaveLength(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.screenshot({path:`test-results/admin-family-${info.project.name}.png`,fullPage:true});
 await friend.goto('/?section=profile');
 await expect(friend.getByText('Подарочная подписка · без списаний',{exact:true})).toBeVisible();
 expect((await friend.request.get('/api/admin/users')).status()).toBe(403);
 expect((await friend.request.post('/api/lessons/life-airport/start')).status()).toBe(200);
 // Cancelling confirmation must not display a false success or extend access.
 page.once('dialog',dialog=>dialog.dismiss());
 await page.getByRole('button',{name:'Продлить',exact:true}).click();
 await expect(page.getByRole('status').filter({hasText:'Подарок продлён'})).toHaveCount(0);
 await page.getByLabel('На сколько дней продлевать').fill('7');
 // The mutation succeeds, then refreshing the profile fails. A retry must keep
 // its UUID and replay the completed extension rather than add seven more days.
 await page.route('**/api/users/me',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Временная ошибка обновления профиля'})}),{times:1});
 page.once('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'Продлить',exact:true}).click();
 await expect(page.locator('.admin-panel [role=alert]')).toContainText('Временная ошибка обновления профиля');
 page.once('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'Продлить',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('Подарок продлён');
 expect((await (await page.request.get(`/api/admin/users/${friendId}`)).json()).grants[0].expires_at).toBe(initial.expires_at+7*86400);
 page.once('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'Отозвать',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('Подарок отозван');
 expect((await (await friend.request.get('/api/users/me')).json()).subscription).toBeNull();
 expect((await friend.request.post('/api/lessons/life-airport/start')).status()).toBe(402);
 const nav=page.getByRole('navigation',{name:'Разделы админки'});
 await nav.getByRole('button',{name:'Журнал',exact:true}).click();
 await page.getByLabel('Тип действия').selectOption('grant_created');
 await expect(page.locator('.admin-audit-entry').filter({hasText:String(friendId)})).toHaveCount(1);
 await nav.getByRole('button',{name:'Платежи и тарифы',exact:true}).click();
 await expect(page.locator('.admin-plan')).toHaveCount(3);
 await expect(page.getByText('Подтверждённых платежей пока нет.',{exact:false})).toBeVisible();
 const download=page.waitForEvent('download');
 await page.getByRole('button',{name:'CSV',exact:true}).click();
 expect((await download).suggestedFilename()).toBe('linguaquest-payments.csv');
 await nav.getByRole('button',{name:'Система',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Состояние системы',exact:true})).toBeVisible();
 page.once('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'Приостановить AI',exact:true}).click();
 await expect(page.getByText('AI приостановлен администратором',{exact:true})).toBeVisible();
 page.once('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'Снять паузу AI',exact:true}).click();
 await expect(page.getByText('Административная пауза снята',{exact:true})).toBeVisible();
 expect(errors).toEqual([]);
 await friendContext.close();
});
