import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const root='/run/media/FileDump/DevProjects/Python/AI';
const p=await PresentationFile.importPptx(await FileBlob.load('/home/euphoria/Загрузки/Telegram Desktop/Презентация проекта.pptx'));
const s=[...p.slides.items];
const layouts=await Promise.all(s.map((_,i)=>fs.readFile(`${root}/.finly-deck/layout-${i+1}.json`,'utf8').then(JSON.parse)));
const ink='#121D40',muted='#65789C',green='#08AC90',white='#FFFFFF';
function pos(x,y,w,h){return{left:x,top:y,width:w,height:h};}
function shape(id){return p.resolve(id)}
function edit(id,text,size=22,color=ink,bold=false,frame){let a=shape(id);a.text=text;a.text.style={typeface:'Arial',fontSize:size,color,bold,autoFit:'none',wrap:true,insets:{left:0,right:0,top:0,bottom:0}};if(frame)a.position=pos(...frame);return a;}
function add(sl,text,x,y,w,h,size=24,color=ink,bold=false){const a=sl.shapes.add({geometry:'textbox',position:pos(x,y,w,h),fill:'none',line:{fill:'none',width:0}});a.text=text;a.text.style={typeface:'Arial',fontSize:size,color,bold,autoFit:'none',wrap:true,insets:{left:0,right:0,top:0,bottom:0}};return a;}
function del(...ids){for(const id of ids)shape(id).delete();}
function notes(sl,text){sl.speakerNotes.textFrame.setText(text);}
// Remove instructional strips while retaining the supplied slide design.
for(let i=4;i<=10;i++)for(const e of layouts[i].elements){if(e.kind==='shape'&&e.bbox[1]>=630)shape(e.aid).delete();}
del('sh/036h8but','sh/nqxgjqtk','sh/mpozalcz');
// Reuse the empty user journey slide for a missing competitor slide.
const alternatives=s[8].duplicate();alternatives.moveTo(10);
for(const a of alternatives.shapes.items){if(a.text?.toString()==='Как это работает'){a.text='Альтернативы и фокус finly';a.text.style={typeface:'Arial Black',fontSize:40,color:ink,bold:true};}}
// Cover.
edit('sh/y5wjip0z','Показывает, сколько можно тратить в день до стипендии',28,white,false,[64,366,870,76]);
edit('sh/14fyhgbe','Максим Чепиков   /   Пётр Макаров   /   Павел Тагиров',18,white,false,[426,486,760,58]);
notes(s[0],'Максим, 15 секунд. Представляем finly, финансового помощника для студента. Главный вопрос продукта: сколько можно потратить сегодня, чтобы денег хватило до следующего поступления. Команда «Рыбы дипсика».');
// Team: keep user-provided portraits and repair text overlap.
del('sh/fypcfqdg');
const team=[['sh/d8zit87m','sh/5kfipszu','sh/kj6hgny9','im/ozyh83e1','Чепиков Максим','Продукт и системный анализ'],['sh/et8zmto7','sh/q5ozitov','sh/r6x0rypg','im/p07i18fm','Макаров Пётр','Backend и архитектура'],['sh/zuh0vypc','sh/w3a1wn65','sh/xoji5s7q','im/e9wz29wz','Тагиров Павел','Frontend и дизайн']];
team.forEach((t,i)=>{let x=64+i*392;shape(t[0]).position=pos(x,468,368,116);edit(t[1],t[4],25,ink,true,[x+24,486,320,34]);edit(t[2],t[5],20,muted,false,[x+24,531,320,40]);shape(t[3]).frame=pos(x+45,170,276,280);});
notes(s[1],'Максим, 10 секунд. В команде распределены продукт и системный анализ, серверная архитектура, интерфейс и дизайн.');
// Problem and audience: remove unsupported market estimates and exclusivity claims.
edit('sh/byd032h8','Студенту сложно понять, хватит ли денег до следующего поступления',28,white,true);
edit('sh/4nuhs7uh','Студенты 18–25 лет, которые совмещают учёбу и подработку',23,ink,false,[90,410,310,140]);
edit('sh/cruhwrud','Стипендия приходит по расписанию. Выплаты за смены меняются по сумме и дате.',23,ink,false,[481,410,310,158]);
edit('sh/0ve10ru9','Остаток на карте не показывает, сколько денег останется после обязательных платежей.',23,ink,false,[873,410,310,158]);
notes(s[2],'Максим, 25 секунд. Проблема проекта: распределить имеющиеся деньги до следующего поступления при смешанном доходе. Описываем продуктовую гипотезу, а не результаты проведённых интервью. Источник: предоставленный командой Word-документ.');
edit('sh/yp07atwv','Учится очно и подрабатывает\nДоход от смен меняется\nСам оплачивает повседневные расходы',20,muted,false,[93,461,340,112]);
edit('sh/7a1cn6po','Студенты 18–25 лет, которые самостоятельно управляют личными расходами',24,ink);
edit('sh/velcrqpk','Стипендия плюс подработка: деньги приходят в разные даты и разными суммами',24,ink);
edit('sh/3ilwvqpw','Нужно учесть жильё, связь и резерв, прежде чем решить, сколько тратить сегодня',24,ink);
notes(s[3],'Максим, 20 секунд. Наш стартовый сегмент — студенты со стипендией и подработкой. Проверка востребованности и готовности платить — следующий этап. Оценка 2–2,5 млн из исходных материалов не используется как доказанный размер рынка.');
// Solution, expanding the existing template into the unused right-hand area.
edit('sh/xwn2dszi','Предлагаемое решение',40,ink,true,[64,65,1120,58]);
edit('sh/kjelony9','finly собирает операции и рассчитывает дневной бюджет с учётом платежей, резерва и даты поступления.',29,white,true,[96,190,625,124]);
edit('sh/fid07u98','Непонятно, сколько можно потратить',21,muted,false,[85,480,157,105]);
edit('sh/3md0bu94','Учитываем остаток и будущие платежи',21,muted,false,[328,480,157,105]);
edit('sh/bqx0fe9g','Понятный лимит на каждый день',21,muted,false,[571,480,157,105]);
add(s[4],'НАЧАТЬ МОЖНО С ВЫПИСКИ',800,167,410,28,17,green,true);
add(s[4],'PDF или CSV',800,216,410,55,36,ink,true);
add(s[4],'Пользователь проверяет операции перед сохранением',800,283,410,110,25,muted);
add(s[4],'Для демонстрации автоматизации подключён учебный банк',800,440,410,120,25,ink);
notes(s[4],'Максим, 25 секунд. Начать можно с импорта выписки. CSV разбирает локальный сервер. Для PDF пользователь проверяет очищенный текст и разрешает обработку моделью. До подтверждения строки не попадают в историю операций.');
// Value: clearly labelled illustrative arithmetic, not claimed user impact.
edit('sh/va98j210','Понятный ориентир для ежедневных трат',28,muted,false,[64,139,1140,44]);
add(s[5],'ПРИМЕР РАСЧЁТА',64,227,620,25,17,green,true);
add(s[5],'20 000 ₽',64,273,500,70,54,ink,true);
add(s[5],'известный остаток',64,348,500,38,23,muted);
add(s[5],'3 000 ₽  обязательные платежи\n2 000 ₽  резерв\n10 дней  до поступления',64,409,510,130,27,ink);
add(s[5],'1 500 ₽',704,269,490,90,68,green,true);
add(s[5],'можно тратить в день',704,372,470,50,30,ink,true);
add(s[5],'(20 000 − 3 000 − 2 000) / 10',704,452,485,42,25,muted);
add(s[5],'Условный пример без холдов. Эффект для пользователей проверим на пилоте.',64,607,1150,44,19,muted);
notes(s[5],'Пётр, 25 секунд. Это арифметический пример, а не измеренный результат пользователей. Из остатка вычитаем платежи и резерв, делим на дни. Холды тоже уменьшают доступный бюджет. Пользовательский лимит может ограничить результат. Расчёты в backend/budget.py.');
// Features in a flat two-column layout.
const features=[['Импорт PDF и CSV','Проверка строк до подтверждения'],['Бюджет до поступления','Платежи, резерв и дневной лимит'],['Операции и аналитика','Категории расходов и история'],['Учебный банковский API','Счета, остатки и синхронизация'],['Предупреждения','Крупная покупка и превышение лимита'],['AI-помощник','Объясняет расчётные показатели']];
features.forEach(([t,b],i)=>{let x=64+(i%2)*600,y=176+Math.floor(i/2)*148;add(s[6],t,x,y,535,40,28,ink,true);add(s[6],b,x,y+49,530,65,23,muted);});
add(s[6],'Локальный MVP. Реальные банковские счета и платежи не подключены.',64,647,1150,30,18,green);
notes(s[6],'Павел, 20 секунд. Эти возможности реализованы в локальном MVP. Интерфейс на Next.js и React, backend на FastAPI, база приложения SQLite. Источники: backend/app.py, frontend/finly/App.tsx.');
// Core differentiator.
edit('sh/9w3uds36','Бюджет после каждой покупки',40,ink,true);
edit('sh/07atgnmp','Покупка меняет\nплан на оставшиеся дни',37,white,true);
edit('sh/l8ja9s3a','Новая операция уменьшает доступную сумму. finly пересчитывает дневной бюджет и обновляет открытый экран.',26,white);
edit('sh/b2hs3il8','ПОКАЖЕМ НА ДЕМО',16,green,true);
edit('sh/3u18fepo','Расход 12 000 ₽ изменит остаток и лимит',23,ink,true);
edit('sh/2ts769o3','ФОКУС ПРОДУКТА',17,green,true);
edit('sh/fq1obeps','До следующего поступления',24,ink,true);
edit('sh/up872987','Планирование вокруг даты стипендии и известных обязательств',22,muted);
edit('sh/72ho7upg','Объяснимые суммы',24,ink,true);
edit('sh/6187yp8b','Сервер считает бюджет. AI выбирает объяснения по этим данным.',22,muted);
notes(s[7],'Пётр, 25 секунд. Ключевой сценарий — реакция бюджета на конкретную покупку. SSE доставляет событие в браузер, затем интерфейс запрашивает свежий снимок. Модель выбирает разделы объяснения, а суммы подставляет сервер. Это фокус продукта, без заявления об отсутствии аналогов.');
// User journey, bank details underneath.
const steps=[['1','Загрузка','Выписка или учебный банк'],['2','Проверка','Операции и известный остаток'],['3','План','Платежи, резерв и дата дохода'],['4','Результат','Дневной бюджет и объяснение']];
steps.forEach(([n,t,b],i)=>{const x=64+i*296;add(s[8],n,x,177,200,74,52,green,true);add(s[8],t,x,267,250,47,28,ink,true);add(s[8],b,x,329,250,90,24,muted);});
add(s[8],'КАК ПРИХОДЯТ ДАННЫЕ БАНКА',64,487,1150,26,17,green,true);
add(s[8],'Вход и токен   /   Счета и операции   /   Остатки   /   Пересчёт бюджета',64,534,1150,60,26,ink);
add(s[8],'Опрос банка каждые 15 секунд. События SSE обновляют интерфейс.',64,628,1150,34,21,muted);
notes(s[8],'Пётр, 30 секунд. POST /auth/login получает токен. GET /accounts возвращает счета. По каждому счёту запрашиваются /transactions и /balances. Повторная синхронизация не дублирует историю. Банк опрашиваем по HTTP, браузеру отправляем SSE. Покупки лаборатории создаются в отдельном симуляторе, а не в банке. Источник: backend/bank_in_a_box.py, backend/app.py.');
// Actual screenshot.
del('sh/zyl8vmt0','sh/0zu9ora5','sh/f2h8jitg');
edit('sh/dwjqtcbu','Рабочий прототип',40,ink,true,[64,65,1100,58]);
s[9].images.add({blob:new Uint8Array(await fs.readFile(`${root}/.finly-deck/dashboard.png`)),contentType:'image/png',alt:'Обзор finly на синтетических данных симулятора',fit:'contain',position:pos(75,159,720,405)});
edit('sh/wnyx0fit','Импорт, аналитика, бюджет и обновления',22,white);
edit('sh/ip0f2p0j','Покупку на 12 000 ₽ и изменение лимита',22,white);
edit('sh/kbix4zyp','Две вкладки: лаборатория и обзор',22,white);
add(s[9],'Скриншот работающего приложения на синтетических данных симулятора',64,628,1150,40,20,muted);
notes(s[9],'Павел, 90 секунд на живую демонстрацию. Открыть обзор и лабораторию в двух вкладках с источником «Учебный банк + симулятор». Запомнить остаток, создать проведённый расход 12 000 ₽, показать изменение бюджета без перезагрузки. Уведомления зависят от настроек и порогов. При сбое показать этот скриншот и CSV-импорт. Скриншот: локальный finly, синтетический профиль, 27 сентября 2026.');
// Competitive context, as editable native table.
const table=alternatives.tables.add({rows:4,columns:3,left:64,top:188,width:1152,height:354,columnWidths:[230,440,482],values:[['Решение','Возможности','Наш фокус'],['Дзен-мани','Учёт и планирование бюджета','Студенческий сценарий\nдо следующего поступления'],['CoinKeeper','Учёт расходов и лимиты\nпо категориям','Реакция дневного бюджета\nна новую операцию'],['finly MVP','Выписки, учебный банк\nи расчёт бюджета','Проверяем востребованность\nна студенческой аудитории']]});
table.borders.assign({fill:'#D8E2EF',width:1,style:'solid'});
for(let r=0;r<4;r++)for(let c=0;c<3;c++){const cell=table.getCell(r,c);cell.fill=r===0?ink:r%2?'#F4F8FA':'#FFFFFF';cell.text.style={typeface:'Arial',fontSize:r===0?22:23,bold:r===0||c===0,color:r===0?white:ink};}
add(alternatives,'Гипотеза отличия: удобство сценария для студента со смешанным доходом',64,582,1150,65,27,ink,true);
add(alternatives,'Преимущество и готовность платить ещё предстоит проверить на пилоте.',64,660,1150,30,18,muted);
notes(alternatives,'Максим, 25 секунд. У существующих приложений уже есть планирование. Мы проверяем более узкий сценарий студентов со смешанным доходом. Не заявляем отсутствие аналогов. Источники возможностей: https://support.zenmoney.ru/knowledge-bases/2-baza-znanij/categories/55-planirovanie-byudzheta/articles ; https://about.coinkeeper.me/24674569 . Проверено 27 сентября 2026.');
// Roadmap: distinguish implemented work from hypotheses.
edit('sh/c3mpof6h','Следующие этапы зависят от результатов пилота',20,muted,false,[64,143,1100,35]);
edit('sh/14ze9c3i','01  ХАКАТОН',16,green,true);
edit('sh/ydcfq1kb','Рабочий MVP',29,ink,true);
edit('sh/jylwj6lw','Импорт выписок, учебный банк, бюджет, события и объяснения',24,muted);
edit('sh/5sjah872','02  БЛИЖАЙШИЙ ЭТАП',16,green,true);
edit('sh/4rato36h','Пилот со студентами',29,ink,true);
edit('sh/v2hsbyp0','Проверить понятность лимита, повторное использование и готовность платить за автоматизацию',24,muted);
edit('sh/g3qtkj6l','03  ПОСЛЕ ПРОВЕРКИ',16,green,true);
edit('sh/fy1cnipk','Партнёрства',29,ink,true);
edit('sh/exsbudoz','Обсудить интеграции с банками и вузами. Доработать авторизацию и защиту данных.',24,muted);
add(s[10],'Модель дохода для проверки: Free с импортом, Pro с автоматизацией. Оплата в MVP не подключена.',64,639,1150,51,21,ink);
notes(s[10],'Максим, 25 секунд. Ближайший шаг — пилот со студентами. Смотрим на понятность бюджета и повторное использование, затем проверяем готовность платить. Банковские и вузовские партнёрства — гипотеза развития, а не заключённые соглашения.');
// Closing without invented contact details.
edit('sh/nilsnetc','Покупка в симуляторе\nи пересчёт дневного бюджета',28,white,true);
edit('sh/6dgbqdsv','Студент понимает, сколько может потратить сегодня',28,white,true);
edit('sh/s7epofeh','Локальный MVP',25,white,true);
edit('sh/d8nqxkf2','ПРОТОТИП',15,white,true);
edit('sh/j2lorqxk','АУДИТОРИЯ',15,white,true);
edit('sh/i1c7i5wf','Студенты 18–25 лет',25,white,true);
edit('sh/43upkve5','Рыбы дипсика',25,white,true);
notes(s[11],'Максим, 15 секунд. finly даёт студенту понятный ориентир на каждый день. Готовы показать детали прототипа и ответить на вопросы.');
// Fix numbering after inserting the missing slide.
for(let i=0;i<p.slides.items.length;i++)for(const a of p.slides.items[i].shapes.items){const t=a.text?.toString()??'';if(/^\d{2} \/ 13$/.test(t))a.text=`${String(i+1).padStart(2,'0')} / 13`;}
await (await PresentationFile.exportPptx(p)).save(`${root}/.finly-deck/candidate.pptx`);
console.log('EXPORTED',p.slides.items.length);
