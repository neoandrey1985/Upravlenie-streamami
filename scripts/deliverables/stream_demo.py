# -*- coding: utf-8 -*-
"""Демо-оргструктура для снимков, видео и презентации «Управления стримами и командами».

DEMO_JS — асинхронная функция для page.evaluate(): в БРАУЗЕРЕ СБОРКИ (локальный режим, данные пользователя
не трогаются) создаёт 2 стрима и 7 команд с разными показателями, а для «Стрима «Покупки»» — фичи с историями
в бэклогах команд, цели PI, межкомандные зависимости, ROAM, Scrum of Scrums и System Demo.
Текущей остаётся первая команда (демо-данные приложения), поэтому снимки разделов команды не меняются.

Использование:  from stream_demo import DEMO_JS;  page.evaluate(DEMO_JS)
"""

DEMO_JS = r"""async()=>{
 setPerm('admin');applyPerms();updateRoleBtn();
 if(ORG.teams.length>1)return 'already';
 await orgRename('streams','s1','Стрим «Покупки»');await orgRename('teams','t1','Корзина и оплата');
 const mk=async(name,sid,k)=>{const id=await orgAddTeam(name,sid,'copy');const st=JSON.parse(localStorage.getItem(stKey(id)));
  st.team=st.team.slice(0,Math.max(5,st.team.length-2*k));
  st.tasks.forEach((t,i)=>{if((+t.sprint===1||+t.sprint===2)&&t.status==='Готово'&&(i+k)%4===0)t.status='В работе';
   if(+t.sprint===3&&(i+k)%3===0)t.status='Готово';});
  (st.bugs||[]).forEach((b,i)=>{if((i+k)%3===0)b.status='Закрыт';});
  st.params.name=name;localStorage.setItem(stKey(id),JSON.stringify(st));return id;};
 const t2=await mk('Каталог','s1',1),t3=await mk('Личный кабинет','s1',2),t4=await mk('Поиск','s1',3),t5=await mk('Мобильное приложение','s1',1);
 const s2=await orgAddStream('Стрим «Логистика»');await mk('Склад',s2,2);await mk('Доставка',s2,3);
 await sdocLoad(true);const d=SDOC.data,pi=d.pis[0];pi.name='PI 2026.3';
 d.pis.push({id:'PI-2',name:'PI 2026.4',start:'2026-10-12',iters:5});
 const F=(id,name,status,owner,bv,tc,rr,size,p)=>({id,name,status,pi:p||'PI-1',owner,bv,tc,rr,size,links:[]});
 d.features.push(F('F-01','Оплата картой и СБП','В работе','Петрова М.',8,8,5,5),F('F-02','Персональные рекомендации','Анализ','Иванов А.',6,3,3,8),
  F('F-03','Быстрый поиск по каталогу','В работе','Смирнов К.',7,5,2,3),F('F-04','Единый личный кабинет','Бэклог','Кузнецова Е.',5,3,2,5),
  F('F-05','Push-уведомления о заказе','Готово','Орлов Д.',4,5,1,2),F('F-06','Подписка на доставку','Воронка','Петрова М.',6,2,4,13,'PI-2'));
 const states=await streamTeamStates(true);
 const story=async(fi,team,title,est,k,status)=>{const f=d.features.find(x=>x.id===fi),x=states.find(s=>s.team.id===team);
  const id=await teamAddTask(team,{title:'['+fi+'] '+title,assignee:'',role:'',type:'История',est,status,sprint:sprintOfIter(x&&x.st,k,pi),dep:'',started:'',done:'',priority:'Should'});
  f.links.push({team,task:id});};
 await story('F-01','t1','Платёжный шлюз',5,2,'Готово');await story('F-01','t1','Оплата через СБП',3,3,'В работе');await story('F-01',t5,'Экран оплаты в приложении',3,3,'To Do');
 await story('F-03',t4,'Индекс товаров',8,2,'Готово');await story('F-03',t2,'Фильтры каталога',3,3,'В работе');
 await story('F-02',t3,'Блок рекомендаций',5,4,'To Do');await story('F-04',t3,'Профиль и адреса',5,4,'To Do');
 await story('F-05',t5,'Push о статусе заказа',3,1,'Готово');await story('F-05','t1','События заказа для push',2,1,'Готово');
 d.objectives.push({id:'O-01',pi:'PI-1',team:'t1',text:'Запустить оплату картой и СБП',bv:9,actual:8,committed:true},
  {id:'O-02',pi:'PI-1',team:t4,text:'Поиск по каталогу быстрее 300 мс',bv:7,actual:6,committed:true},
  {id:'O-03',pi:'PI-1',team:t2,text:'Фильтры и сортировка каталога',bv:6,actual:5,committed:true},
  {id:'O-04',pi:'PI-1',team:t5,text:'Push-уведомления о заказе',bv:5,actual:5,committed:true},
  {id:'O-05',pi:'PI-1',team:t3,text:'Рекомендации на главной',bv:4,actual:'',committed:false});
 d.deps.push({id:'XD-01',from:t5,to:'t1',feature:'F-01',item:'API платежей для мобильного экрана',need:3,plan:4,status:'Принята'},
  {id:'XD-02',from:t2,to:t4,feature:'F-03',item:'Индекс товаров для фильтров',need:3,plan:2,status:'Выполнена'},
  {id:'XD-03',from:t3,to:t2,feature:'F-04',item:'Справочник категорий',need:4,plan:4,status:'Открыта'},
  {id:'XD-04',from:'t1',to:t5,feature:'F-05',item:'SDK уведомлений',need:2,plan:2,status:'Заблокирована'});
 d.roam.push({id:'R-01',title:'Сертификация PCI DSS может не успеть к релизу',team:'t1',impact:'Высокое',roam:'Owned',owner:'Петрова М.',due:'2026-11-20',note:'Ранний аудит, выделенный инженер по безопасности'},
  {id:'R-02',title:'Нагрузка на поиск в распродажу',team:t4,impact:'Высокое',roam:'Mitigated',owner:'Смирнов К.',due:'2026-10-30',note:'Кэш и нагрузочное тестирование'},
  {id:'R-03',title:'Зависимость мобильной команды от API платежей',team:t5,impact:'Среднее',roam:'Accepted',owner:'Орлов Д.',due:'',note:'Заглушка API до итерации 4'},
  {id:'R-04',title:'Нехватка дизайнера в стриме',team:'',impact:'Среднее',roam:'Resolved',owner:'RTE',due:'',note:'Дизайнер привлечён из «Логистики»'});
 const st2=await streamTeamStates(true);
 d.sos=sosAgenda('2026-09-08',st2);d.sos.forEach((s,i)=>{s.next=['Довести СБП до стенда','Фильтры — в ревью','Макеты кабинета','Индекс — в прод','Экран оплаты на заглушке'][i]||'';});
 d.demos=demoAgenda(st2,1,'2026-08-14').concat(demoAgenda(st2,2,'2026-08-28'));
 d.demos.forEach((m,i)=>{m.status=i===0?'Принято':i===1?'Принято':'Доработать';m.feedback=['Готово к релизу','Скорость устраивает','Нужен экран ошибок оплаты'][i]||'';});
 sdocSave();STC.at=0;views();return 'ok';}"""
